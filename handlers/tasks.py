import asyncio
import html
import time

from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database
from integrations.base import TaskItem
from keyboards.user import no_tasks_kb, task_kb
from handlers.start import ensure_gate
from menu_render import edit_screen, safe_edit_text
from services import task_manager
from services.referral_service import process_referral_progress

router = Router(name="tasks")

REFRESH_SECONDS = 300
SEEN_TTL_HOURS = 24


def _all_done_text(minutes: int) -> str:
    return (
        "✅ Все доступные задания выполнены!\n\n"
        "Новые задания подгружаются каждые 5 минут — "
        f"загляни снова через ~{minutes} мин."
    )


def _task_to_dict(task: TaskItem) -> dict:
    # The pool lives in the FSM table, so drop the provider's raw payload
    # (only its resource_id is ever used - see _stable_key) to keep rows small.
    extra = dict(task.extra)
    raw = extra.pop("raw", None) or {}
    if not extra.get("resource_id") and raw.get("resource_id"):
        extra["resource_id"] = raw["resource_id"]
    return {
        "provider": task.provider,
        "external_id": task.external_id,
        "title": task.title,
        "link": task.link,
        "reward": task.reward,
        "extra": extra,
    }


def _dict_to_task(d: dict) -> TaskItem:
    return TaskItem(
        provider=d["provider"],
        external_id=d["external_id"],
        title=d["title"],
        link=d["link"],
        reward=d["reward"],
        extra=d.get("extra") or {},
    )


def _next_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Следующее задание", callback_data="task:next", style=ButtonStyle.SUCCESS)],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="menu:back")],
        ]
    )


async def _task_text(task: TaskItem, number: int) -> str:
    default_reward = await database.get_setting_float("task_reward", 1)
    intro = await database.get_setting("text_tasks_intro", "")
    intro = intro.replace("{tasks_reward}", f"{default_reward:g}")
    return (
        f"{intro}\n\n"
        f"📋 Задание №{number}\n\n"
        f"{html.escape(task.title or '')}\n\n"
        "Нажми «Перейти», выполни действие, затем вернись сюда и нажми «Проверить».\n\n"
        f"🎁 Награда: {task.reward:g} ⭐"
    )


def _needs_click_tracking(task: TaskItem) -> bool:
    # Telegram gives bots no way to verify whether a user started another
    # bot, so for bot-type own sponsors the only signal we get is whether
    # they actually pressed "Перейти" - tracked via a callback button instead
    # of a plain url button (see task:go below). Same for own sponsors with no
    # channel id to check membership against.
    if task.provider != "own":
        return False
    return task.extra.get("target_type") == "bot" or not task.extra.get("has_chat_id", True)


def _stable_key(task: TaskItem) -> str:
    """Identity of the underlying sponsor. Flyer signatures and Traffy
    assignment ids change on every request, so external_id alone can't tell
    that two fetches returned the same channel."""
    raw = task.extra.get("raw") or {}
    rid = task.extra.get("resource_id") or raw.get("resource_id")
    if rid:
        return f"{task.provider}:{rid}"
    if task.provider in ("flyer", "traffy"):
        return f"{task.provider}:{task.title}"
    return f"{task.provider}:{task.external_id}"


async def _refill_pool(state: FSMContext, telegram_id: int) -> list[dict]:
    data = await state.get_data()
    shown = data.get("shown", {})
    user = await database.get_user(telegram_id)
    exclude = {k: set(v) for k, v in shown.items()}
    shown_links = set(data.get("shown_links", []))
    shown_keys = set(data.get("shown_keys", []))
    # Persisted across restarts and the 5-minute reset: a sponsor that was
    # already shown (e.g. a join-request channel that can never auto-verify)
    # must not keep coming back.
    seen_before = await database.recently_seen_task_keys(telegram_id, SEEN_TTL_HOURS)
    tasks = []
    for t in await task_manager.fetch_tasks(user, exclude=exclude):
        key = _stable_key(t)
        if (t.link and t.link in shown_links) or key in shown_keys or key in seen_before:
            continue
        tasks.append(t)
        shown.setdefault(t.provider, []).append(t.external_id)
        shown_keys.add(key)
        if t.link:
            shown_links.add(t.link)
    await state.update_data(shown_links=list(shown_links), shown_keys=list(shown_keys))
    pool = [_task_to_dict(t) for t in tasks]
    await state.update_data(pool=pool, idx=0, shown=shown)
    return pool


SEARCH_TEXT = "🔍 Ищем подходящее для вас задание…\n\nЭто займёт пару секунд."
PRECHECK_WINDOW = 1
MAX_PRECHECK_ROUNDS = 40


async def _show_search(callback: CallbackQuery) -> Message:
    """Shows the 'searching' stub and returns the message to keep editing
    (a photo message can't be edited into text, so it is replaced)."""
    message = callback.message
    if message.photo:
        await message.delete()
        return await message.bot.send_message(message.chat.id, SEARCH_TEXT)
    await safe_edit_text(message, SEARCH_TEXT, None)
    return message


async def _precheck(bot, user, entry: dict) -> bool:
    """True if the user has already done this task (so it should be skipped).
    Unverifiable tasks are never treated as done."""
    if entry.get("checked"):
        return False
    try:
        return await task_manager.check_task(user, _dict_to_task(entry), bot=bot, silent=True)
    except Exception:
        return False


async def _advance(state: FSMContext, telegram_id: int, bot) -> None:
    """Moves idx to the first task that isn't already completed, silently
    checking candidates and pulling in a fresh pool when this one runs out."""
    user = await database.get_user(telegram_id)
    for _ in range(MAX_PRECHECK_ROUNDS):
        data = await state.get_data()
        pool = data.get("pool", [])
        idx = data.get("idx", 0)

        if idx >= len(pool):
            exhausted_at = data.get("exhausted_at")
            if exhausted_at:
                if REFRESH_SECONDS - (time.time() - exhausted_at) > 0:
                    return
                # cooldown over: forget what was shown/skipped and ask again
                await state.update_data(exhausted_at=None, shown={}, shown_links=[], shown_keys=[])
            pool = await _refill_pool(state, telegram_id)
            idx = 0
            if not pool:
                await state.update_data(exhausted_at=time.time())
                return

        window = pool[idx : idx + PRECHECK_WINDOW]
        done = await asyncio.gather(*[_precheck(bot, user, e) for e in window])
        for offset, is_done in enumerate(done):
            if not is_done:
                pool[idx + offset]["checked"] = True
                await state.update_data(pool=pool, idx=idx + offset)
                return
        await state.update_data(idx=idx + len(window))


async def _render_current(state: FSMContext, telegram_id: int, bot=None) -> tuple[str, InlineKeyboardMarkup]:
    await _advance(state, telegram_id, bot)
    data = await state.get_data()
    pool = data.get("pool", [])
    idx = data.get("idx", 0)
    shown_count = data.get("shown_count", 0)

    if idx >= len(pool):
        exhausted_at = data.get("exhausted_at")
        left = REFRESH_SECONDS - (time.time() - exhausted_at) if exhausted_at else REFRESH_SECONDS
        return _all_done_text(max(1, int(left // 60) + 1)), no_tasks_kb()

    shown_count += 1
    await state.update_data(shown_count=shown_count)
    task = _dict_to_task(pool[idx])
    await database.mark_tasks_seen(telegram_id, [_stable_key(task)])
    text = await _task_text(task, shown_count)
    return text, task_kb(task.link, track_click=_needs_click_tracking(task))


async def _show_next(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    pool, idx = data.get("pool", []), data.get("idx", 0)
    if idx < len(pool) and pool[idx].get("checked"):
        message = callback.message
        if message.photo:
            message = await _show_search(callback)
    else:
        message = await _show_search(callback)
    text, kb = await _render_current(state, callback.from_user.id, callback.bot)
    await safe_edit_text(message, text, kb)


@router.callback_query(F.data == "menu:tasks")
async def open_tasks(callback: CallbackQuery, state: FSMContext) -> None:
    if not await ensure_gate(callback):
        return
    await state.update_data(shown_count=0)
    await _show_next(callback, state)


@router.callback_query(F.data == "task:refresh")
async def refresh_tasks(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(pool=[], idx=0)
    await _show_next(callback, state)


@router.callback_query(F.data == "task:skip")
async def task_skip(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.update_data(idx=data.get("idx", 0) + 1)
    await _show_next(callback, state)


@router.callback_query(F.data == "task:next")
async def task_next(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.update_data(idx=data.get("idx", 0) + 1)
    await _show_next(callback, state)


@router.callback_query(F.data == "task:go")
async def task_go(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    pool = data.get("pool", [])
    idx = data.get("idx", 0)
    if idx >= len(pool):
        await callback.answer("Задание больше не доступно.", show_alert=True)
        return

    task = _dict_to_task(pool[idx])
    if task.provider == "own":
        await database.record_sponsor_click(callback.from_user.id, int(task.external_id))

    # Telegram rejects answerCallbackQuery(url=...) for anything but this
    # bot's own t.me/<bot>?start=... deep link (URL_INVALID otherwise), so we
    # can't redirect straight to an external sponsor link from here. Reveal a
    # real url= button instead - this tap was the click signal we needed.
    kb = task_kb(task.link, track_click=_needs_click_tracking(task), revealed=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await callback.answer(
        "✅ Отмечено!\n\nТеперь нажми появившуюся кнопку «🔗 Открыть ссылку», чтобы перейти.",
        show_alert=True,
    )


@router.callback_query(F.data == "task:check")
async def task_check(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    pool = data.get("pool", [])
    idx = data.get("idx", 0)
    if idx >= len(pool):
        await callback.answer("Задание больше не доступно.", show_alert=True)
        return

    task = _dict_to_task(pool[idx])
    user = await database.get_user(callback.from_user.id)

    ok = await task_manager.check_task(user, task, bot=callback.bot)
    if not ok:
        await callback.answer("❌ Задание ещё не выполнено. Попробуйте ещё раз.", show_alert=True)
        return

    is_new = await task_manager.complete_task(callback.from_user.id, task)
    if is_new:
        await database.increment_tasks_completed(callback.from_user.id)
        await process_referral_progress(callback.bot, callback.from_user.id)
        reward_line = f"🎁 +{task.reward:g} ⭐"
    else:
        reward_line = "(уже было засчитано ранее)"

    await safe_edit_text(
        callback.message,
        f"✅ Задание выполнено!\n\nЗадание засчитано.\n{reward_line}",
        _next_kb(),
    )
    await callback.answer()
