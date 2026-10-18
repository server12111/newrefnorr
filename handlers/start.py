from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import database
from keyboards.user import gate_kb
from menu_render import edit_screen, safe_edit_text, send_main_menu, show_main_menu
from services import gate_service
from services.referral_service import register_user

router = Router(name="start")

GATE_TEXT = (
    "🔒 Чтобы пользоваться ботом, подпишитесь на наших спонсоров:\n\n"
    "После подписки нажмите «✅ Проверить подписку»."
)


async def _show_gate(missing, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    clicked = await gate_service.get_clicked_ids(user_id, missing)
    return GATE_TEXT, gate_kb(missing, clicked)


async def ensure_gate(callback: CallbackQuery) -> bool:
    """Re-checks mandatory sponsors on actions that matter (tasks, withdraw):
    the /start check alone could be skipped via an older menu message, and
    sponsors added later would never be shown to existing users. Shows the
    gate screen and returns False if something is missing."""
    missing = await gate_service.get_unsubscribed(callback.bot, callback.from_user.id)
    if not missing:
        return True
    text, kb = await _show_gate(missing, callback.from_user.id)
    await edit_screen(callback, text, kb)
    await callback.answer("🔒 Сначала подпишитесь на спонсоров.", show_alert=True)
    return False


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    start_arg = args[1].strip() if len(args) > 1 else None

    registration_enabled = await database.get_setting_bool("registration_enabled", True)

    user = await database.get_user(message.from_user.id)
    if not user and not registration_enabled:
        await message.answer("🚫 Регистрация новых пользователей временно отключена.")
        return

    await register_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        start_arg,
        bot=message.bot,
    )

    missing = await gate_service.get_unsubscribed(message.bot, message.from_user.id)
    if missing:
        text, kb = await _show_gate(missing, message.from_user.id)
        await message.answer(text, reply_markup=kb)
        return

    await send_main_menu(message)


@router.callback_query(F.data.startswith("gate:go:"))
async def gate_go(callback: CallbackQuery) -> None:
    sponsor_id = int(callback.data.split(":")[2])
    sponsor = await database.get_sponsor(sponsor_id)
    if not sponsor:
        await callback.answer("Недоступно.", show_alert=True)
        return

    await database.record_sponsor_click(callback.from_user.id, sponsor_id)

    missing = await gate_service.get_unsubscribed(callback.bot, callback.from_user.id)
    if missing:
        clicked = await gate_service.get_clicked_ids(callback.from_user.id, missing)
        try:
            await callback.message.edit_reply_markup(reply_markup=gate_kb(missing, clicked))
        except Exception:
            pass
        await callback.answer(
            "✅ Отмечено!\n\nТеперь нажми появившуюся кнопку «🔗 Открыть», чтобы перейти.",
            show_alert=True,
        )
        return

    # that click satisfied the last remaining sponsor - let them straight in
    all_gate_sponsors = await gate_service.get_gate_sponsors()
    await gate_service.record_pass(callback.from_user.id, all_gate_sponsors)
    await show_main_menu(callback)
    await callback.answer("✅ Подписка подтверждена!")


@router.callback_query(F.data == "gate:check")
async def gate_check(callback: CallbackQuery) -> None:
    missing = await gate_service.get_unsubscribed(callback.bot, callback.from_user.id)
    if missing:
        await callback.answer("❌ Вы выполнили ещё не все условия.", show_alert=True)
        text, kb = await _show_gate(missing, callback.from_user.id)
        await safe_edit_text(callback.message, text, kb)
        return

    all_gate_sponsors = await gate_service.get_gate_sponsors()
    await gate_service.record_pass(callback.from_user.id, all_gate_sponsors)

    await show_main_menu(callback)
    await callback.answer("✅ Подписка подтверждена!")
