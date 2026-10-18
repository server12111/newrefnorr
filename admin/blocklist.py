from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database
from admin.common import AdminFilter
from states import AdminBlocklistStates

router = Router(name="admin_blocklist")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

PROVIDERS = ["own", "subgram", "flyer", "tgrass", "botohub", "traffy", "axionna"]


def _blocklist_kb(entries) -> InlineKeyboardMarkup:
    rows = []
    for entry in entries[:20]:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"❌ {entry['provider']}: {entry['external_id']}",
                    callback_data=f"abl:remove:{entry['id']}",
                    style=ButtonStyle.DANGER,
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Добавить в блок-лист", callback_data="abl:create", style=ButtonStyle.SUCCESS)])
    rows.append([InlineKeyboardButton(text="◀️ В админ-меню", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _provider_choice_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=p, callback_data=f"abl:provider:{p}", style=ButtonStyle.PRIMARY)]
        for p in PROVIDERS
    ]
    rows.append([InlineKeyboardButton(text="◀️ В админ-меню", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "admin:blocklist")
async def blocklist_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    entries = await database.list_blocked_sponsors()
    text = "🚫 Блок-лист спонсоров\n\n" + (f"Всего: {len(entries)}" if entries else "Список пуст.")
    await callback.message.edit_text(text, reply_markup=_blocklist_kb(entries))
    await callback.answer()


@router.callback_query(F.data.startswith("abl:remove:"))
async def blocklist_remove(callback: CallbackQuery) -> None:
    block_id = int(callback.data.split(":")[2])
    await database.unblock_sponsor(block_id)
    await database.add_log("admin", "sponsor_unblocked", {"block_id": block_id}, admin_id=callback.from_user.id)
    await callback.answer("Удалён")
    entries = await database.list_blocked_sponsors()
    text = "🚫 Блок-лист спонсоров\n\n" + (f"Всего: {len(entries)}" if entries else "Список пуст.")
    await callback.message.edit_text(text, reply_markup=_blocklist_kb(entries))


@router.callback_query(F.data == "abl:create")
async def blocklist_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "Выберите провайдера, чьего спонсора нужно заблокировать:", reply_markup=_provider_choice_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("abl:provider:"))
async def blocklist_provider_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    provider = callback.data.split(":")[2]
    await state.update_data(provider=provider)
    await state.set_state(AdminBlocklistStates.waiting_entry)
    label = "ID/ссылку спонсора" if provider != "own" else "ID спонсора (из списка «Свои спонсоры»)"
    await callback.message.edit_text(f"Введите {label} для блокировки:")
    await callback.answer()


@router.message(AdminBlocklistStates.waiting_entry)
async def blocklist_entry_received(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    provider = data["provider"]
    external_id = (message.text or "").strip()
    if not external_id:
        await message.answer("❌ Отправьте ID текстом:")
        return
    await database.block_sponsor(provider, external_id, None)
    await database.add_log(
        "admin", "sponsor_blocked", {"provider": provider, "external_id": external_id}, admin_id=message.from_user.id
    )
    await state.clear()
    await message.answer(f"✅ Спонсор {provider}:{external_id} добавлен в блок-лист.")
