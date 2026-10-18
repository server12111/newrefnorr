import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database
from config import ADMIN_IDS
from handlers.start import ensure_gate
from keyboards.admin import withdrawal_actions_kb
from keyboards.user import cancel_kb, withdraw_amount_kb, withdraw_confirm_kb, withdraw_method_kb
from menu_render import edit_screen
from services.withdrawal_service import (
    WithdrawalError,
    admin_channel_text,
    channel_url,
    method_label,
    public_channel_text,
    request_withdrawal,
)
from states import WithdrawStates
from utils import fmt_stars

router = Router(name="withdrawals")

# Telegram usernames: 4-32 chars (4 only for Fragment ones), starting with a letter.
USERNAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{3,31}")


async def _amounts() -> list[int]:
    raw = await database.get_setting("withdraw_amounts", "25,50,100")
    return [int(x) for x in raw.split(",") if x.strip().isdigit()]


@router.callback_query(F.data == "menu:withdraw")
async def show_withdraw(callback: CallbackQuery, state: FSMContext) -> None:
    if not await database.get_setting_bool("withdraw_enabled", True):
        await callback.answer("🚫 Вывод Stars временно отключён.", show_alert=True)
        return
    if not await ensure_gate(callback):
        return

    await state.clear()
    user = await database.get_user(callback.from_user.id)
    min_withdraw = await database.get_setting_float("min_withdraw", 15)
    amounts = [a for a in await _amounts() if a >= min_withdraw]
    # The displayed minimum must match the smallest button actually offered -
    # a separately configured min_withdraw below the smallest preset would
    # otherwise show a minimum no button can satisfy.
    shown_min = min(amounts) if amounts else min_withdraw

    intro_template = await database.get_setting("text_withdraw_intro", "")
    intro = intro_template.replace("{balance}", fmt_stars(user["balance"])).replace("{min}", f"{shown_min:g}")

    await edit_screen(
        callback,
        f"💰 Вывод Stars\n\n{intro}\n\nВыберите сумму для вывода:",
        withdraw_amount_kb(amounts),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wd:amount:"))
async def withdraw_amount_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    amount = int(callback.data.split(":")[2])
    user = await database.get_user(callback.from_user.id)
    if amount > round(user["balance"], 6):
        await callback.answer(f"Недостаточно средств. Баланс: {fmt_stars(user['balance'])}", show_alert=True)
        return

    await state.update_data(amount=amount, method=None)

    method_min = await database.get_setting_float("withdraw_method_min_amount", 50)
    if amount >= method_min:
        await callback.message.edit_text(
            f"📤 Сумма: {amount:g} ⭐\n\nВыберите способ получения:",
            reply_markup=withdraw_method_kb(),
        )
        await callback.answer()
        return

    await state.set_state(WithdrawStates.waiting_username)
    await state.update_data(prompt_chat_id=callback.message.chat.id, prompt_message_id=callback.message.message_id)
    await callback.message.edit_text(
        f"📤 Вывод\n\nСумма: {amount:g} ⭐\n\nВведите username получателя:",
        reply_markup=cancel_kb("menu:withdraw"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wd:method:"))
async def withdraw_method_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    method = callback.data.split(":")[2]
    data = await state.get_data()
    amount = data.get("amount")
    if amount is None:
        await callback.answer("Сессия истекла, начните заново.", show_alert=True)
        return

    await state.update_data(method=method)
    await state.set_state(WithdrawStates.waiting_username)
    await state.update_data(prompt_chat_id=callback.message.chat.id, prompt_message_id=callback.message.message_id)
    await callback.message.edit_text(
        f"📤 Вывод\n\nСумма: {amount:g} ⭐\n\nВведите username получателя:",
        reply_markup=cancel_kb("menu:withdraw"),
    )
    await callback.answer()


@router.message(WithdrawStates.waiting_username)
async def withdraw_username(message: Message, state: FSMContext) -> None:
    username = (message.text or "").strip().lstrip("@")
    if not USERNAME_RE.fullmatch(username):
        await message.answer("❌ Введите корректный username (латиница, цифры и _, например @durov).")
        return

    data = await state.get_data()
    amount = data.get("amount")
    if amount is None:
        await state.clear()
        await message.answer("Сессия истекла, начните заново.")
        return
    method = data.get("method")
    await state.update_data(recipient=username)
    await state.set_state(WithdrawStates.confirming)

    summary = f"📤 Проверьте данные\n\n⭐ Сумма: {amount:g} ⭐\n👤 Получатель: @{username}"
    if method:
        summary += f"\n💳 Способ: {method_label(method)}"

    try:
        await message.delete()
    except Exception:
        pass

    prompt_chat_id = data.get("prompt_chat_id")
    prompt_message_id = data.get("prompt_message_id")
    if prompt_chat_id and prompt_message_id:
        try:
            await message.bot.edit_message_text(
                summary,
                chat_id=prompt_chat_id,
                message_id=prompt_message_id,
                reply_markup=withdraw_confirm_kb(),
            )
            return
        except Exception:
            pass
    await message.answer(summary, reply_markup=withdraw_confirm_kb())


@router.callback_query(WithdrawStates.confirming, F.data == "wd:confirm")
async def withdraw_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    amount = data.get("amount")
    recipient = data.get("recipient")
    method = data.get("method")
    if amount is None or recipient is None:
        await callback.answer("Сессия истекла, начните заново.", show_alert=True)
        return
    # checked again here: they may have unsubscribed after opening the screen
    if not await ensure_gate(callback):
        return

    try:
        withdrawal_id = await request_withdrawal(
            callback.from_user.id, callback.from_user.username, amount, recipient, method
        )
    except WithdrawalError as exc:
        await callback.message.edit_text(f"❌ {exc}")
        await callback.answer()
        return

    template = await database.get_setting("text_withdraw_created", "")
    text = (
        template.replace("{amount}", f"{amount:g}")
        .replace("{recipient}", recipient)
        .replace("{id}", str(withdrawal_id))
    )
    public_channel = await database.get_setting("withdraw_public_channel")
    url = channel_url(public_channel)
    kb = (
        InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Канал с заявками", url=url)]])
        if url
        else None
    )
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

    await _post_to_channels(callback.bot, withdrawal_id, callback.from_user, amount, recipient, method)


async def _post_to_channels(bot, withdrawal_id, from_user, amount, recipient, method) -> None:
    admin_channel = await database.get_setting("withdraw_admin_channel")
    public_channel = await database.get_setting("withdraw_public_channel")

    admin_text = admin_channel_text(withdrawal_id, from_user.id, from_user.username, recipient, amount, method)
    public_text = public_channel_text(withdrawal_id, from_user.id, recipient, amount, "pending")

    admin_msg_id = None
    public_msg_id = None

    if admin_channel:
        try:
            msg = await bot.send_message(admin_channel, admin_text, reply_markup=withdrawal_actions_kb(withdrawal_id))
            admin_msg_id = msg.message_id
        except Exception as exc:
            await database.add_log("withdrawal", "admin_channel_post_failed", {"error": str(exc)})
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, admin_text, reply_markup=withdrawal_actions_kb(withdrawal_id))
                except Exception:
                    pass

    if public_channel:
        try:
            msg = await bot.send_message(public_channel, public_text)
            public_msg_id = msg.message_id
        except Exception as exc:
            await database.add_log("withdrawal", "public_channel_post_failed", {"error": str(exc)})

    await database.set_withdrawal_channel_messages(withdrawal_id, admin_msg_id, public_msg_id)
