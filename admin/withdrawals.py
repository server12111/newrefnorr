from aiogram import F, Router
from aiogram.types import CallbackQuery

import database
from admin.common import AdminFilter
from services.withdrawal_service import approve_withdrawal, public_channel_text, reject_withdrawal

router = Router(name="admin_withdrawals")
router.callback_query.filter(AdminFilter())


async def _sync_public_channel(bot, withdrawal, status: str) -> None:
    if not withdrawal["public_channel_message_id"]:
        return
    public_channel = await database.get_setting("withdraw_public_channel")
    if not public_channel:
        return
    text = public_channel_text(
        withdrawal["id"], withdrawal["user_id"], withdrawal["recipient_username"], withdrawal["amount"], status
    )
    try:
        await bot.edit_message_text(text, chat_id=public_channel, message_id=withdrawal["public_channel_message_id"])
    except Exception as exc:
        await database.add_log("withdrawal", "public_channel_sync_failed", {"error": str(exc)})


async def _sync_admin_message(callback: CallbackQuery, withdrawal, suffix: str) -> None:
    # The message the button was clicked on is always the admin-channel post
    # itself, so we can append directly to its current text.
    base_text = callback.message.text or ""
    try:
        await callback.message.edit_text(base_text + suffix, reply_markup=None)
    except Exception:
        pass


async def _notify_user_accepted(bot, withdrawal_id: int, withdrawal) -> None:
    accepted_template = await database.get_setting("text_withdraw_accepted", "")
    accepted_text = accepted_template.replace("{amount}", f"{withdrawal['amount']:g}").replace(
        "{id}", str(withdrawal_id)
    )
    try:
        await bot.send_message(withdrawal["user_id"], accepted_text)
    except Exception:
        return  # user blocked the bot or similar - no point sending the follow-up either

    review_text = await database.get_setting("text_review_request", "")
    if not review_text:
        return
    photo_id = await database.get_photo("text_review_request")
    try:
        if photo_id:
            await bot.send_photo(withdrawal["user_id"], photo_id, caption=review_text)
        else:
            await bot.send_message(withdrawal["user_id"], review_text)
    except Exception:
        pass


@router.callback_query(F.data.startswith("wda:paid:"))
async def withdrawal_approve(callback: CallbackQuery) -> None:
    withdrawal_id = int(callback.data.split(":")[2])
    withdrawal = await database.get_withdrawal(withdrawal_id)
    if not withdrawal or withdrawal["status"] != "pending":
        await callback.answer("Заявка уже обработана.", show_alert=True)
        return

    if not await approve_withdrawal(withdrawal_id, callback.from_user.id):
        await callback.answer("Заявка уже обработана.", show_alert=True)
        return
    withdrawal = await database.get_withdrawal(withdrawal_id)

    await _sync_admin_message(callback, withdrawal, "\n\n✔️ Принято")
    await _sync_public_channel(callback.bot, withdrawal, "paid")
    await callback.answer("Отмечено как выплаченное")
    await _notify_user_accepted(callback.bot, withdrawal_id, withdrawal)


@router.callback_query(F.data.startswith("wda:reject:"))
async def withdrawal_reject(callback: CallbackQuery) -> None:
    withdrawal_id = int(callback.data.split(":")[2])
    withdrawal = await database.get_withdrawal(withdrawal_id)
    if not withdrawal or withdrawal["status"] != "pending":
        await callback.answer("Заявка уже обработана.", show_alert=True)
        return

    if not await reject_withdrawal(withdrawal_id, callback.from_user.id):
        await callback.answer("Заявка уже обработана.", show_alert=True)
        return
    withdrawal = await database.get_withdrawal(withdrawal_id)

    await _sync_admin_message(callback, withdrawal, "\n\n❌ Отклонено (сумма возвращена на баланс)")
    await _sync_public_channel(callback.bot, withdrawal, "rejected")
    await callback.answer("Отклонено")

    try:
        await callback.bot.send_message(
            withdrawal["user_id"],
            f"❌ Ваша заявка #{withdrawal_id} на {withdrawal['amount']:g} ⭐ отклонена. Средства возвращены на баланс.",
        )
    except Exception:
        pass
