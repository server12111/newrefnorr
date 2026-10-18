from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database
import premium_emoji
from admin.common import AdminFilter
from keyboards.admin import back_to_admin_kb
from states import AdminUserStates
from utils import fmt_stars, parse_amount, user_display

router = Router(name="admin_users")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


def _user_actions_kb(telegram_id: int, blocked: bool) -> InlineKeyboardMarkup:
    block_btn = (
        InlineKeyboardButton(
            text=premium_emoji.label("Разблокировать", "🔓", premium_emoji.UNLOCK)[0],
            callback_data=f"au:unblock:{telegram_id}", style=ButtonStyle.SUCCESS,
            **premium_emoji.label("Разблокировать", "🔓", premium_emoji.UNLOCK)[1],
        )
        if blocked
        else InlineKeyboardButton(
            text=premium_emoji.label("Заблокировать", "🔒", premium_emoji.LOCK)[0],
            callback_data=f"au:block:{telegram_id}", style=ButtonStyle.DANGER,
            **premium_emoji.label("Заблокировать", "🔒", premium_emoji.LOCK)[1],
        )
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Начислить", callback_data=f"au:credit:{telegram_id}", style=ButtonStyle.SUCCESS),
                InlineKeyboardButton(text="➖ Списать", callback_data=f"au:debit:{telegram_id}", style=ButtonStyle.DANGER),
            ],
            [block_btn],
            [
                InlineKeyboardButton(text="👥 Рефералы", callback_data=f"au:refs:{telegram_id}", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text="📜 Выводы", callback_data=f"au:wds:{telegram_id}", style=ButtonStyle.PRIMARY),
            ],
            [InlineKeyboardButton(text="◀️ В админ-меню", callback_data="admin:menu")],
        ]
    )


async def _user_card_text(telegram_id: int) -> str | None:
    user = await database.get_user(telegram_id)
    if not user:
        return None
    total_refs, confirmed_refs = await database.count_referrals(telegram_id)
    if user["referrer_id"]:
        referrer = await database.get_user(user["referrer_id"])
        inviter = user_display(referrer["username"] if referrer else None, user["referrer_id"])
    else:
        inviter = "отсутствует"

    return (
        "👤 Пользователь\n\n"
        f"ID: {user['telegram_id']}\n"
        f"Username: {'@' + user['username'] if user['username'] else '—'}\n\n"
        f"⭐ Баланс: {fmt_stars(user['balance'])}\n\n"
        f"📋 Заданий: {user['tasks_completed']}\n\n"
        f"👥 Рефералов: {total_refs}\n"
        f"✅ Засчитано: {confirmed_refs}\n\n"
        f"👤 Пригласил: {inviter}\n\n"
        f"📅 Регистрация: {user['registered_at']}\n"
        f"🚫 Заблокирован: {'да' if user['is_blocked'] else 'нет'}"
    )


@router.callback_query(F.data == "admin:users")
async def users_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminUserStates.waiting_search)
    await callback.message.edit_text(
        "👥 Пользователи\n\nОтправьте Telegram ID или username для поиска:",
        reply_markup=back_to_admin_kb(),
    )
    await callback.answer()


@router.message(AdminUserStates.waiting_search)
async def users_search(message: Message, state: FSMContext) -> None:
    user = await database.search_user(message.text or "")
    if not user:
        await message.answer("❌ Пользователь не найден. Попробуйте ещё раз.")
        return
    text = await _user_card_text(user["telegram_id"])
    await message.answer(text, reply_markup=_user_actions_kb(user["telegram_id"], bool(user["is_blocked"])))


@router.callback_query(F.data.startswith("au:block:"))
async def block_user(callback: CallbackQuery) -> None:
    telegram_id = int(callback.data.split(":")[2])
    await database.set_user_blocked(telegram_id, True)
    await database.add_log("user", "blocked", {"target": telegram_id}, admin_id=callback.from_user.id)
    text = await _user_card_text(telegram_id)
    await callback.message.edit_text(text, reply_markup=_user_actions_kb(telegram_id, True))
    await callback.answer("Пользователь заблокирован")


@router.callback_query(F.data.startswith("au:unblock:"))
async def unblock_user(callback: CallbackQuery) -> None:
    telegram_id = int(callback.data.split(":")[2])
    await database.set_user_blocked(telegram_id, False)
    await database.add_log("user", "unblocked", {"target": telegram_id}, admin_id=callback.from_user.id)
    text = await _user_card_text(telegram_id)
    await callback.message.edit_text(text, reply_markup=_user_actions_kb(telegram_id, False))
    await callback.answer("Пользователь разблокирован")


@router.callback_query(F.data.startswith("au:credit:"))
async def credit_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    telegram_id = int(callback.data.split(":")[2])
    await state.update_data(target=telegram_id)
    await state.set_state(AdminUserStates.waiting_credit_amount)
    await callback.message.edit_text(f"➕ Введите сумму для начисления пользователю {telegram_id}:")
    await callback.answer()


@router.message(AdminUserStates.waiting_credit_amount)
async def credit_apply(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    target = data["target"]
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("❌ Введите положительное число.")
        return
    await database.adjust_balance(target, amount)
    await database.add_log(
        "admin", "credit", {"target": target, "amount": amount}, admin_id=message.from_user.id
    )
    await state.clear()
    text = await _user_card_text(target)
    user = await database.get_user(target)
    await message.answer(f"✅ Начислено {amount:g} ⭐ пользователю {target}")
    await message.answer(text, reply_markup=_user_actions_kb(target, bool(user["is_blocked"])))


@router.callback_query(F.data.startswith("au:debit:"))
async def debit_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    telegram_id = int(callback.data.split(":")[2])
    await state.update_data(target=telegram_id)
    await state.set_state(AdminUserStates.waiting_debit_amount)
    await callback.message.edit_text(f"➖ Введите сумму для списания у пользователя {telegram_id}:")
    await callback.answer()


@router.message(AdminUserStates.waiting_debit_amount)
async def debit_apply(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    target = data["target"]
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("❌ Введите положительное число.")
        return
    if not await database.try_debit(target, amount):
        user = await database.get_user(target)
        await message.answer(
            f"❌ У пользователя только {fmt_stars(user['balance'] if user else 0)}. Введите сумму не больше баланса:"
        )
        return
    await database.add_log(
        "admin", "debit", {"target": target, "amount": amount}, admin_id=message.from_user.id
    )
    await state.clear()
    text = await _user_card_text(target)
    user = await database.get_user(target)
    await message.answer(f"✅ Списано {amount:g} ⭐ у пользователя {target}")
    await message.answer(text, reply_markup=_user_actions_kb(target, bool(user["is_blocked"])))


@router.callback_query(F.data.startswith("au:refs:"))
async def user_refs(callback: CallbackQuery) -> None:
    telegram_id = int(callback.data.split(":")[2])
    refs = await database.list_referrals(telegram_id)
    if not refs:
        text = "👥 Рефералы\n\nНет рефералов."
    else:
        lines = ["👥 Рефералы\n"]
        for ref in refs[:30]:
            who = user_display(ref["username"], ref["telegram_id"])
            status = "✅" if ref["referral_confirmed"] else f"⏳ {ref['tasks_completed']}"
            lines.append(f"{who} — {status}")
        text = "\n".join(lines)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ В админ-меню", callback_data="admin:menu")]]
    )
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("au:wds:"))
async def user_withdrawals_view(callback: CallbackQuery) -> None:
    telegram_id = int(callback.data.split(":")[2])
    from services.withdrawal_service import STATUS_LABELS

    wds = await database.user_withdrawals(telegram_id)
    if not wds:
        text = "📜 Выводы\n\nЗаявок нет."
    else:
        lines = ["📜 Выводы\n"]
        for wd in wds:
            status = STATUS_LABELS.get(wd["status"], wd["status"])
            lines.append(f"#{wd['id']} — {wd['amount']:g} ⭐ — {status}")
        text = "\n".join(lines)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ В админ-меню", callback_data="admin:menu")]]
    )
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()
