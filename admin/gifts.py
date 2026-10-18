import html

from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database
from admin.common import AdminFilter
from keyboards.admin import back_to_admin_kb
from services.gift_service import GiftError, get_available_gifts, send_picked_gift
from states import AdminGiftStates

router = Router(name="admin_gifts")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


def _catalog_kb(gifts: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for g in gifts:
        emoji = g.get("sticker", {}).get("emoji", "🎁")
        row.append(
            InlineKeyboardButton(
                text=f"{emoji} {g['star_count']}",
                callback_data=f"gift:pick:{g['id']}",
                style=ButtonStyle.PRIMARY,
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="◀️ В админ-меню", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="gift:confirm", style=ButtonStyle.SUCCESS),
                InlineKeyboardButton(text="❌ Отклонить", callback_data="gift:cancel", style=ButtonStyle.DANGER),
            ]
        ]
    )


@router.callback_query(F.data == "admin:gift")
async def gift_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        gifts = await get_available_gifts()
    except GiftError as exc:
        await callback.message.edit_text(f"❌ Не удалось загрузить каталог подарков: {exc}", reply_markup=back_to_admin_kb())
        await callback.answer()
        return

    if not gifts:
        await callback.message.edit_text("🎁 Каталог подарков сейчас пуст.", reply_markup=back_to_admin_kb())
        await callback.answer()
        return

    await callback.message.edit_text("🎁 Отправить подарок\n\nВыбери подарок:", reply_markup=_catalog_kb(gifts))
    await callback.answer()


@router.callback_query(F.data.startswith("gift:pick:"))
async def gift_picked(callback: CallbackQuery, state: FSMContext) -> None:
    gift_id = callback.data.split(":", 2)[2]
    gifts = await get_available_gifts()
    gift = next((g for g in gifts if str(g["id"]) == gift_id), None)
    if not gift:
        await callback.answer("Подарок больше не доступен.", show_alert=True)
        return

    emoji = gift.get("sticker", {}).get("emoji", "🎁")
    await state.update_data(gift_id=gift_id, star_count=gift["star_count"], emoji=emoji)
    await state.set_state(AdminGiftStates.waiting_text)
    await callback.message.edit_text(
        f"Подарок: {emoji} {gift['star_count']} ⭐\n\n"
        "Введи текст, который получатель увидит вместе с подарком (до 128 символов), "
        "или отправь «-», чтобы отправить без текста:"
    )
    await callback.answer()


@router.message(AdminGiftStates.waiting_text)
async def gift_text_received(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip() if message.text else ""
    if raw == "-":
        text = None
    else:
        if len(raw) > 128:
            await message.answer("❌ Слишком длинный текст (максимум 128 символов). Попробуйте ещё раз:")
            return
        text = raw

    await state.update_data(text=text)
    await state.set_state(AdminGiftStates.waiting_target)
    await message.answer("Введи @username или numeric ID получателя:")


@router.message(AdminGiftStates.waiting_target)
async def gift_target_received(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().lstrip("@")
    user = await database.search_user(raw)
    if not user:
        await message.answer("❌ Пользователь не найден в базе бота. Введите @username или ID ещё раз:")
        return

    data = await state.get_data()
    await state.update_data(target_id=user["telegram_id"], target_username=user["username"])
    await state.set_state(AdminGiftStates.confirming)

    who = f"@{user['username']}" if user["username"] else f"ID {user['telegram_id']}"
    text_line = html.escape(data.get("text") or "без текста")
    await message.answer(
        "📤 Проверьте подарок\n\n"
        f"🎁 {data['emoji']} — {data['star_count']} ⭐\n"
        f"✍️ Текст: {text_line}\n"
        f"👤 Получатель: {who}",
        reply_markup=_confirm_kb(),
    )


@router.callback_query(AdminGiftStates.confirming, F.data == "gift:confirm")
async def gift_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()

    ok, text = await send_picked_gift(
        callback.from_user.id,
        data["target_id"],
        data["gift_id"],
        data["star_count"],
        data["emoji"],
        data.get("text"),
    )
    await callback.message.edit_text(text)
    await callback.answer()


@router.callback_query(AdminGiftStates.confirming, F.data == "gift:cancel")
async def gift_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Отправка подарка отменена.", reply_markup=back_to_admin_kb())
    await callback.answer()


def _is_bear_command(message: Message) -> bool:
    return bool(message.text) and (message.text or "").strip().lower() == "+мишка"


@router.message(F.func(_is_bear_command))
async def send_bear(message: Message) -> None:
    if not message.reply_to_message:
        await message.answer("❌ Ответьте (Reply) этой командой на сообщение пользователя.")
        return

    target = message.reply_to_message.from_user
    if target.is_bot:
        await message.answer("❌ Нельзя отправить подарок боту.")
        return

    price = await database.get_setting_float("gift_bear_price", 15)
    gift_id = await database.get_setting("gift_bear_id", "5170233102089322756")
    ok, text = await send_picked_gift(message.from_user.id, target.id, gift_id, int(price), "🧸", None)
    await message.answer(text)
