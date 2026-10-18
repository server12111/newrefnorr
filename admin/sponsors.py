import html

from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database
import premium_emoji
from utils import parse_amount
from admin.common import AdminFilter
from states import AdminSponsorStates

router = Router(name="admin_sponsors")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


def _sponsors_list_kb(sponsors) -> InlineKeyboardMarkup:
    rows = []
    for sponsor in sponsors[:30]:
        kind_icon = "🔒" if sponsor["kind"] == "gate" else "📋"
        style = ButtonStyle.SUCCESS if sponsor["is_active"] else ButtonStyle.DANGER
        text, extra = premium_emoji.label(
            f"{kind_icon} {sponsor['name']}",
            "🟢" if sponsor["is_active"] else "🔴",
            premium_emoji.CHECK if sponsor["is_active"] else premium_emoji.CROSS,
        )
        rows.append([InlineKeyboardButton(text=text, callback_data=f"asp:view:{sponsor['id']}", style=style, **extra)])
    rows.append([InlineKeyboardButton(text="➕ Добавить спонсора", callback_data="asp:create", style=ButtonStyle.SUCCESS)])
    rows.append([InlineKeyboardButton(text="◀️ В админ-меню", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _sponsor_actions_kb(sponsor_id: int, active: bool) -> InlineKeyboardMarkup:
    if active:
        text, extra = premium_emoji.label("Выключить", "🔴", premium_emoji.CROSS)
        toggle = InlineKeyboardButton(text=text, callback_data=f"asp:toggle:{sponsor_id}", style=ButtonStyle.DANGER, **extra)
    else:
        text, extra = premium_emoji.label("Включить", "🟢", premium_emoji.CHECK)
        toggle = InlineKeyboardButton(text=text, callback_data=f"asp:toggle:{sponsor_id}", style=ButtonStyle.SUCCESS, **extra)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [toggle],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"asp:delete:{sponsor_id}", style=ButtonStyle.DANGER)],
            [InlineKeyboardButton(text="◀️ К спонсорам", callback_data="admin:sponsors")],
        ]
    )


def _type_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📢 Канал/чат", callback_data="asp:type:channel", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text="🤖 Бот", callback_data="asp:type:bot", style=ButtonStyle.PRIMARY),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin:sponsors", style=ButtonStyle.DANGER)],
        ]
    )


def _kind_choice_kb(target_type: str = "channel") -> InlineKeyboardMarkup:
    action = "нажатие" if target_type == "bot" else "подписка"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"📋 Задания (за {action} — награда)", callback_data="asp:kind:task", style=ButtonStyle.PRIMARY),
            ],
            [
                InlineKeyboardButton(text=f"🔒 Спонсоры (обязательн{'ое' if target_type == 'bot' else 'ая'} {action})", callback_data="asp:kind:gate", style=ButtonStyle.PRIMARY),
            ],
        ]
    )


async def _sponsor_text(sponsor) -> str:
    action = "нажатие" if sponsor["target_type"] == "bot" else "подписка"
    if sponsor["kind"] == "gate":
        kind_label = f"🔒 Спонсор (обязательн{'ое' if sponsor['target_type'] == 'bot' else 'ая'} {action})"
    else:
        kind_label = f"📋 Задание (за {action} — награда)"
    type_label = "📢 Канал/чат" if sponsor["target_type"] == "channel" else "🤖 Бот"
    lines = [
        f"{'🔒' if sponsor['kind'] == 'gate' else '📢'} {html.escape(sponsor['name'])}",
        "",
        f"Тип: {kind_label}",
        f"Цель: {type_label}",
        f"Ссылка: {html.escape(sponsor['url'])}",
    ]
    if sponsor["target_type"] == "channel":
        lines.append(f"ID канала: {html.escape(sponsor['external_id'] or '—')}")
    if sponsor["kind"] == "task":
        lines.append(f"Награда: {sponsor['reward']:g} ⭐ (0 = награда по умолчанию)")
    if sponsor["click_goal"]:
        lines.append(f"Переходов: {sponsor['click_count']}/{sponsor['click_goal']} (авто-отключение по цели)")
    else:
        lines.append(f"Переходов: {sponsor['click_count']} (без лимита)")
    lines.append(f"Статус: {'включён' if sponsor['is_active'] else 'выключен'}")
    return "\n".join(lines)


@router.callback_query(F.data == "admin:sponsors")
async def sponsors_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    sponsors = await database.list_sponsors()
    text = "📢 Свои спонсоры\n\n" + (
        f"Всего: {len(sponsors)}\n📋 = задание (награда), 🔒 = обязательная подписка"
        if sponsors
        else "Спонсоров пока нет."
    )
    await callback.message.edit_text(text, reply_markup=_sponsors_list_kb(sponsors))
    await callback.answer()


@router.callback_query(F.data.startswith("asp:view:"))
async def sponsor_view(callback: CallbackQuery) -> None:
    sponsor_id = int(callback.data.split(":")[2])
    sponsor = await database.get_sponsor(sponsor_id)
    if not sponsor:
        await callback.answer("Не найден", show_alert=True)
        return
    text = await _sponsor_text(sponsor)
    await callback.message.edit_text(text, reply_markup=_sponsor_actions_kb(sponsor_id, bool(sponsor["is_active"])))
    await callback.answer()


@router.callback_query(F.data.startswith("asp:toggle:"))
async def sponsor_toggle(callback: CallbackQuery) -> None:
    sponsor_id = int(callback.data.split(":")[2])
    sponsor = await database.get_sponsor(sponsor_id)
    if not sponsor:
        await callback.answer("Не найден", show_alert=True)
        return
    new_state = not bool(sponsor["is_active"])
    await database.set_sponsor_active(sponsor_id, new_state)
    await database.add_log(
        "admin", "sponsor_toggle", {"sponsor_id": sponsor_id, "active": new_state}, admin_id=callback.from_user.id
    )
    await sponsor_view(callback)


@router.callback_query(F.data.startswith("asp:delete:"))
async def sponsor_delete(callback: CallbackQuery) -> None:
    sponsor_id = int(callback.data.split(":")[2])
    await database.delete_sponsor(sponsor_id)
    await database.add_log("admin", "sponsor_deleted", {"sponsor_id": sponsor_id}, admin_id=callback.from_user.id)
    await callback.answer("Удалён")
    sponsors = await database.list_sponsors()
    text = "📢 Свои спонсоры\n\n" + (f"Всего: {len(sponsors)}" if sponsors else "Спонсоров пока нет.")
    await callback.message.edit_text(text, reply_markup=_sponsors_list_kb(sponsors))


@router.callback_query(F.data == "asp:create")
async def sponsor_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Новый спонсор\n\nВыбери тип:", reply_markup=_type_choice_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("asp:type:"))
async def sponsor_type_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    target_type = callback.data.split(":")[2]
    await state.update_data(target_type=target_type)
    await state.set_state(AdminSponsorStates.waiting_name)
    await callback.message.edit_text("Название спонсора (для админ-списка):")
    await callback.answer()


@router.message(AdminSponsorStates.waiting_name)
async def sponsor_create_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("❌ Отправьте название текстом:")
        return
    await state.update_data(name=name)
    await state.set_state(AdminSponsorStates.waiting_url)
    await message.answer("Ссылка (URL канала/чата/бота):")


@router.message(AdminSponsorStates.waiting_url)
async def sponsor_create_url(message: Message, state: FSMContext) -> None:
    url = (message.text or "").strip()
    if not url:
        await message.answer("❌ Отправьте ссылку текстом:")
        return
    await state.update_data(url=url)
    data = await state.get_data()
    if data["target_type"] == "bot":
        # Telegram gives bots no way to verify channel-style subscription to
        # another bot, so a bot-type sponsor's "Спонсоры" (gate) check is
        # click-based instead - see task:go/gate:go for how the click gets
        # recorded server-side despite Telegram not letting a callback button
        # redirect straight to an external bot.
        await state.update_data(channel_id=None)
        await message.answer(
            "Для бота проверка будет по факту нажатия «Перейти» (Telegram не даёт проверить подписку на бота).\n\n"
            "Куда добавить спонсора?",
            reply_markup=_kind_choice_kb("bot"),
        )
        return

    await state.set_state(AdminSponsorStates.waiting_channel_id)
    await message.answer(
        "ID канала для проверки подписки (например -1001234567890 или @username).\n"
        "Если проверка не нужна — отправьте «-» (тогда спонсор может быть только заданием, не обязательной подпиской, "
        "и засчитывается по факту нажатия «Перейти»):"
    )


@router.message(AdminSponsorStates.waiting_channel_id)
async def sponsor_create_channel(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    channel_id = None if value == "-" else value
    await state.update_data(channel_id=channel_id)

    if not channel_id:
        await state.update_data(kind="task")
        await state.set_state(AdminSponsorStates.waiting_reward)
        await message.answer("Награда в ⭐ (0 — использовать значение по умолчанию):")
        return

    await message.answer("Куда добавить спонсора?", reply_markup=_kind_choice_kb())


@router.callback_query(F.data.startswith("asp:kind:"))
async def sponsor_kind_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    kind = callback.data.split(":")[2]
    await state.update_data(kind=kind)
    if kind == "gate":
        await state.update_data(reward=0.0)
        await state.set_state(AdminSponsorStates.waiting_click_goal)
        await callback.message.edit_text("Сколько переходов набрать перед автоотключением? (0 — без лимита):")
    else:
        await state.set_state(AdminSponsorStates.waiting_reward)
        await callback.message.edit_text("Награда в ⭐ (0 — использовать значение по умолчанию):")
    await callback.answer()


@router.message(AdminSponsorStates.waiting_reward)
async def sponsor_create_reward(message: Message, state: FSMContext) -> None:
    reward = parse_amount(message.text, allow_zero=True)
    if reward is None:
        await message.answer("❌ Введите число (0 или больше).")
        return
    await state.update_data(reward=reward)
    await state.set_state(AdminSponsorStates.waiting_click_goal)
    await message.answer("Сколько переходов набрать перед автоотключением? (0 — без лимита):")


@router.message(AdminSponsorStates.waiting_click_goal)
async def sponsor_create_click_goal(message: Message, state: FSMContext) -> None:
    try:
        click_goal = int((message.text or "").strip())
        if click_goal < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите целое число (0 — без лимита).")
        return

    data = await state.get_data()
    await database.add_sponsor(
        data["name"],
        data["url"],
        data.get("channel_id"),
        data.get("reward", 0.0),
        kind=data.get("kind", "task"),
        target_type=data["target_type"],
        click_goal=click_goal,
    )
    await database.add_log(
        "admin",
        "sponsor_created",
        {"name": data["name"], "url": data["url"], "kind": data.get("kind"), "target_type": data["target_type"]},
        admin_id=message.from_user.id,
    )
    await state.clear()
    await message.answer(f"✅ Спонсор «{html.escape(data['name'])}» добавлен!")
