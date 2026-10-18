from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import database
from admin.common import AdminFilter

router = Router(name="admin_tasks_panel")
router.callback_query.filter(AdminFilter())

PROVIDERS = ["subgram", "flyer", "tgrass", "botohub", "traffy", "axionna"]


async def _provider_stats(provider: str) -> tuple[int, int, int]:
    cur = await database.conn().execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE provider = ?", (provider,)
    )
    task_count = (await cur.fetchone())["c"]

    cur = await database.conn().execute(
        "SELECT COUNT(*) AS c FROM user_tasks ut JOIN tasks t ON t.id = ut.task_id WHERE t.provider = ?",
        (provider,),
    )
    completions = (await cur.fetchone())["c"]

    cur = await database.conn().execute(
        "SELECT COUNT(*) AS c FROM logs WHERE category = 'task' AND action LIKE ?",
        (f"{provider}_%error%",),
    )
    errors = (await cur.fetchone())["c"]
    return task_count, completions, errors


async def _kb() -> InlineKeyboardMarkup:
    rows = []
    for p in PROVIDERS:
        enabled = await database.get_setting_bool(f"integration_{p}_enabled", True)
        style = ButtonStyle.SUCCESS if enabled else ButtonStyle.DANGER
        rows.append([InlineKeyboardButton(text=f"⚙️ {p}", callback_data=f"atp:toggle:{p}", style=style)])
    rows.append([InlineKeyboardButton(text="◀️ В админ-меню", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _text() -> str:
    lines = ["📋 Задания\n"]
    for provider in PROVIDERS:
        enabled = await database.get_setting_bool(f"integration_{provider}_enabled", True)
        icon = "🟢" if enabled else "🔴"
        task_count, completions, errors = await _provider_stats(provider)
        lines.append(
            f"{icon} {provider} — заданий: {task_count}, выполнений: {completions}, ошибок: {errors}"
        )
    lines.append("\nНажмите на провайдера ниже, чтобы включить/выключить его.")
    return "\n".join(lines)


@router.callback_query(F.data == "admin:tasks")
async def tasks_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(await _text(), reply_markup=await _kb())
    await callback.answer()


@router.callback_query(F.data.startswith("atp:toggle:"))
async def tasks_toggle(callback: CallbackQuery) -> None:
    provider = callback.data.split(":")[2]
    key = f"integration_{provider}_enabled"
    current = await database.get_setting_bool(key, True)
    await database.set_setting(key, "0" if current else "1")
    await database.add_log(
        "admin", "integration_toggle", {"provider": provider, "enabled": not current}, admin_id=callback.from_user.id
    )
    await callback.message.edit_text(await _text(), reply_markup=await _kb())
    await callback.answer()
