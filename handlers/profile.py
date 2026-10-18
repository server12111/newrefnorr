import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

import database
from keyboards.user import back_kb, profile_kb
from menu_render import edit_screen
from services.withdrawal_service import STATUS_LABELS
from utils import fmt_stars, user_display

router = Router(name="profile")


async def _profile_text(telegram_id: int) -> str:
    user = await database.get_user(telegram_id)
    total_refs, confirmed_refs = await database.count_referrals(telegram_id)

    if user["referrer_id"]:
        referrer = await database.get_user(user["referrer_id"])
        inviter = user_display(referrer["username"] if referrer else None, user["referrer_id"])
    else:
        inviter = "отсутствует"

    footer = await database.get_setting("text_profile_footer", "")
    return (
        "👤 Твой профиль\n\n"
        f"👤 Имя: {html.escape(user['first_name'] or '—')}\n"
        f"🆔 ID: {user['telegram_id']}\n"
        f"💬 Username: {'@' + user['username'] if user['username'] else '—'}\n\n"
        f"⭐ Баланс: {fmt_stars(user['balance'])}\n"
        f"📋 Выполнено заданий: {user['tasks_completed']}\n\n"
        f"👥 Пригласил: {inviter}\n"
        f"👥 Рефералов: {total_refs} (✅ {confirmed_refs} засчитано)\n\n"
        f"{footer}"
    )


@router.callback_query(F.data == "menu:profile")
async def show_profile(callback: CallbackQuery) -> None:
    text = await _profile_text(callback.from_user.id)
    await edit_screen(callback, text, profile_kb())
    await callback.answer()


@router.callback_query(F.data == "profile:history")
async def profile_history(callback: CallbackQuery) -> None:
    withdrawals = await database.user_withdrawals(callback.from_user.id)
    if not withdrawals:
        text = "📜 История выводов\n\nЗаявок пока нет."
    else:
        lines = ["📜 История выводов\n"]
        for wd in withdrawals:
            status = STATUS_LABELS.get(wd["status"], wd["status"])
            lines.append(f"#{wd['id']} — {wd['amount']:g} ⭐ — {status}")
        text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=back_kb("profile:reopen"))
    await callback.answer()


@router.callback_query(F.data == "profile:reopen")
async def profile_reopen(callback: CallbackQuery, state: FSMContext) -> None:
    # also the promo prompt's "Отмена" - leave the promo input mode
    await state.set_state(None)
    text = await _profile_text(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=profile_kb())
    await callback.answer()
