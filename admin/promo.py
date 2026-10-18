import html

from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database
import premium_emoji
from utils import parse_amount
from admin.common import AdminFilter
from keyboards.admin import back_to_admin_kb
from states import AdminPromoStates

router = Router(name="admin_promo")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


def _promo_list_kb(promos) -> InlineKeyboardMarkup:
    rows = []
    for promo in promos[:15]:
        style = ButtonStyle.SUCCESS if promo["is_active"] else ButtonStyle.DANGER
        text, extra = premium_emoji.label(
            f"{promo['code']} ({promo['activations']}/{promo['max_activations']})",
            "🟢" if promo["is_active"] else "🔴",
            premium_emoji.CHECK if promo["is_active"] else premium_emoji.CROSS,
        )
        rows.append([InlineKeyboardButton(text=text, callback_data=f"ap:view:{promo['id']}", style=style, **extra)])
    rows.append([InlineKeyboardButton(text="➕ Создать промокод", callback_data="ap:create", style=ButtonStyle.PRIMARY)])
    rows.append([InlineKeyboardButton(text="◀️ В админ-меню", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _promo_actions_kb(promo_id: int, active: bool) -> InlineKeyboardMarkup:
    if active:
        text, extra = premium_emoji.label("Отключить", "🔴", premium_emoji.CROSS)
        toggle = InlineKeyboardButton(text=text, callback_data=f"ap:toggle:{promo_id}", style=ButtonStyle.DANGER, **extra)
    else:
        text, extra = premium_emoji.label("Включить", "🟢", premium_emoji.CHECK)
        toggle = InlineKeyboardButton(text=text, callback_data=f"ap:toggle:{promo_id}", style=ButtonStyle.SUCCESS, **extra)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [toggle],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"ap:delete:{promo_id}", style=ButtonStyle.DANGER)],
            [InlineKeyboardButton(text="◀️ К промокодам", callback_data="admin:promo")],
        ]
    )


@router.callback_query(F.data == "admin:promo")
async def promo_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    promos = await database.list_promos()
    text = "🎟 Промокоды\n\n" + (f"Всего: {len(promos)}" if promos else "Промокодов пока нет.")
    await callback.message.edit_text(text, reply_markup=_promo_list_kb(promos))
    await callback.answer()


@router.callback_query(F.data.startswith("ap:view:"))
async def promo_view(callback: CallbackQuery) -> None:
    promo_id = int(callback.data.split(":")[2])
    promos = await database.list_promos()
    promo = next((p for p in promos if p["id"] == promo_id), None)
    if not promo:
        await callback.answer("Не найден", show_alert=True)
        return
    required_line = (
        f"Требуется заданий: {promo['required_tasks']}\n" if promo["required_tasks"] else ""
    )
    text = (
        f"🎟 {html.escape(promo['code'])}\n\n"
        f"Награда: {promo['reward']:g} ⭐\n"
        f"Активаций: {promo['activations']}/{promo['max_activations']}\n"
        f"{required_line}"
        f"Статус: {'включён' if promo['is_active'] else 'выключен'}\n"
        f"Создан: {promo['created_at']}"
    )
    await callback.message.edit_text(text, reply_markup=_promo_actions_kb(promo_id, bool(promo["is_active"])))
    await callback.answer()


@router.callback_query(F.data.startswith("ap:toggle:"))
async def promo_toggle(callback: CallbackQuery) -> None:
    promo_id = int(callback.data.split(":")[2])
    promos = await database.list_promos()
    promo = next((p for p in promos if p["id"] == promo_id), None)
    if not promo:
        await callback.answer("Не найден", show_alert=True)
        return
    new_state = not bool(promo["is_active"])
    await database.set_promo_active(promo_id, new_state)
    await database.add_log(
        "promo", "toggled", {"promo_id": promo_id, "active": new_state}, admin_id=callback.from_user.id
    )
    await promo_view(callback)


@router.callback_query(F.data.startswith("ap:delete:"))
async def promo_delete(callback: CallbackQuery) -> None:
    promo_id = int(callback.data.split(":")[2])
    await database.delete_promo(promo_id)
    await database.add_log("promo", "deleted", {"promo_id": promo_id}, admin_id=callback.from_user.id)
    await callback.answer("Удалён")
    promos = await database.list_promos()
    text = "🎟 Промокоды\n\n" + (f"Всего: {len(promos)}" if promos else "Промокодов пока нет.")
    await callback.message.edit_text(text, reply_markup=_promo_list_kb(promos))


@router.callback_query(F.data == "ap:create")
async def promo_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminPromoStates.waiting_code)
    await callback.message.edit_text("Название промокода:", reply_markup=back_to_admin_kb())
    await callback.answer()


@router.message(AdminPromoStates.waiting_code)
async def promo_create_code(message: Message, state: FSMContext) -> None:
    code = (message.text or "").strip().upper()
    if not code:
        await message.answer("❌ Отправьте название промокода текстом:")
        return
    if await database.get_promo(code):
        await message.answer("❌ Такой промокод уже существует. Введите другой:")
        return
    await state.update_data(code=code)
    await state.set_state(AdminPromoStates.waiting_reward)
    await message.answer("Награда (в ⭐):")


@router.message(AdminPromoStates.waiting_reward)
async def promo_create_reward(message: Message, state: FSMContext) -> None:
    reward = parse_amount(message.text)
    if reward is None:
        await message.answer("❌ Введите положительное число.")
        return
    await state.update_data(reward=reward)
    await state.set_state(AdminPromoStates.waiting_limit)
    await message.answer("Лимит активаций:")


@router.message(AdminPromoStates.waiting_limit)
async def promo_create_limit(message: Message, state: FSMContext) -> None:
    try:
        limit = int((message.text or "").strip())
        if limit <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите целое число больше 0.")
        return
    await state.update_data(limit=limit)
    await state.set_state(AdminPromoStates.waiting_required_tasks)
    await message.answer(
        "Сколько заданий нужно выполнить пользователю, чтобы активировать промокод?\n"
        "Отправьте 0, если ограничения нет:"
    )


@router.message(AdminPromoStates.waiting_required_tasks)
async def promo_create_required_tasks(message: Message, state: FSMContext) -> None:
    try:
        required_tasks = int((message.text or "").strip())
        if required_tasks < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите целое число (0 — без ограничения).")
        return
    data = await state.get_data()
    await database.create_promo(data["code"], data["reward"], data["limit"], required_tasks)
    await database.add_log(
        "promo",
        "created",
        {"code": data["code"], "reward": data["reward"], "limit": data["limit"], "required_tasks": required_tasks},
        admin_id=message.from_user.id,
    )
    await state.clear()
    required_line = f"\nТребуется заданий: {required_tasks}" if required_tasks else ""
    await message.answer(
        f"✅ Промокод {data['code']} создан!\n\nНаграда: {data['reward']:g} ⭐\nЛимит: {data['limit']}{required_line}"
    )
