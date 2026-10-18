from aiogram import F, Router
from aiogram.types import CallbackQuery

import database
from keyboards.user import back_kb, referrals_kb
from menu_render import edit_screen
from utils import user_display

router = Router(name="referrals")


async def _referrals_text(telegram_id: int, bot_username: str) -> str:
    total, confirmed = await database.count_referrals(telegram_id)
    in_progress = total - confirmed
    required = await database.get_setting_int("referral_required_tasks", 8)
    reward = await database.get_setting_float("referral_reward", 5)
    link = f"https://t.me/{bot_username}?start={telegram_id}"
    return (
        "👥 Реферальная система\n\n"
        f"Приглашай друзей и получай ⭐ Stars! Как только твой друг выполнит {required} заданий — "
        f"реферал засчитывается, и тебе начисляется {reward:g} ⭐.\n\n"
        f"🔗 Твоя ссылка:\n{link}\n\n"
        f"👤 Всего приглашено: {total}\n"
        f"✅ Засчитано: {confirmed}\n"
        f"⏳ В процессе: {in_progress}"
    )


@router.callback_query(F.data == "menu:referrals")
async def show_referrals(callback: CallbackQuery) -> None:
    bot_username = (await callback.bot.get_me()).username
    text = await _referrals_text(callback.from_user.id, bot_username)
    await edit_screen(callback, text, referrals_kb())
    await callback.answer()


@router.callback_query(F.data == "ref:reopen")
async def ref_reopen(callback: CallbackQuery) -> None:
    bot_username = (await callback.bot.get_me()).username
    text = await _referrals_text(callback.from_user.id, bot_username)
    await callback.message.edit_text(text, reply_markup=referrals_kb())
    await callback.answer()


@router.callback_query(F.data == "ref:list")
async def ref_list(callback: CallbackQuery) -> None:
    required = await database.get_setting_int("referral_required_tasks", 8)
    referrals = await database.list_referrals(callback.from_user.id)
    if not referrals:
        text = "👥 Мои рефералы\n\nПока никого нет."
    else:
        lines = ["👥 Мои рефералы\n"]
        for idx, ref in enumerate(referrals[:30], start=1):
            who = user_display(ref["username"], ref["telegram_id"])
            if ref["referral_confirmed"]:
                status = "✅ Засчитан"
            else:
                status = f"⏳ {ref['tasks_completed']}/{required}"
            lines.append(f"{idx}. {who} — {status}")
        text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=back_kb("ref:reopen"))
    await callback.answer()


