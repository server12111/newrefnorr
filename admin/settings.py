from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database
import premium_emoji
from admin.common import AdminFilter
from states import AdminSettingsStates

router = Router(name="admin_settings")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

TEXT_SETTINGS = [
    ("referral_required_tasks", "Заданий для реферала"),
    ("referral_reward", "Награда за реферала (⭐)"),
    ("task_reward", "Награда за задание (⭐)"),
    ("min_withdraw", "Минимальный вывод (⭐)"),
    ("gift_bear_price", "Цена подарка «Мишка» (⭐)"),
    ("ad_block_text", "Текст рекламного блока"),
    ("ad_block_url", "Ссылка рекламного блока"),
    ("withdraw_amounts", "Суммы вывода (через запятую)"),
    ("withdraw_method_min_amount", "От какой суммы спрашивать способ (⭐)"),
    ("withdraw_admin_channel", "Канал админов (заявки)"),
    ("withdraw_public_channel", "Публичный канал (статусы)"),
    ("daily_invite_prize_tiers", "Призы за топ-1 приглашений/сутки (порог:награда,...)"),
]

BOOL_SETTINGS = [
    ("premium_emoji_enabled", "Премиум-эмодзи на кнопках"),
    ("registration_enabled", "Регистрация"),
    ("withdraw_enabled", "Вывод Stars"),
    ("integration_subgram_enabled", "Subgram"),
    ("integration_flyer_enabled", "Flyer"),
    ("integration_tgrass_enabled", "Tgrass"),
    ("integration_botohub_enabled", "Botohub"),
    ("integration_traffy_enabled", "Traffy"),
    ("integration_axionna_enabled", "Axiona"),
]


async def _settings_kb() -> InlineKeyboardMarkup:
    rows = []
    for key, label in TEXT_SETTINGS:
        value = await database.get_setting(key, "")
        rows.append(
            [InlineKeyboardButton(text=f"{label}: {value}", callback_data=f"as:edit:{key}", style=ButtonStyle.PRIMARY)]
        )
    for key, label in BOOL_SETTINGS:
        enabled = await database.get_setting_bool(key, True)
        style = ButtonStyle.SUCCESS if enabled else ButtonStyle.DANGER
        text, extra = premium_emoji.label(
            label,
            "🟢" if enabled else "🔴",
            premium_emoji.CHECK if enabled else premium_emoji.CROSS,
        )
        rows.append([InlineKeyboardButton(text=text, callback_data=f"as:toggle:{key}", style=style, **extra)])
    rows.append([InlineKeyboardButton(text="◀️ В админ-меню", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "admin:settings")
async def settings_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("⚙️ Настройки", reply_markup=await _settings_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("as:toggle:"))
async def settings_toggle(callback: CallbackQuery) -> None:
    key = callback.data.split(":", 2)[2]
    current = await database.get_setting_bool(key, True)
    await database.set_setting(key, "0" if current else "1")
    if key == "premium_emoji_enabled":
        premium_emoji.set_enabled(not current)
    await database.add_log(
        "admin", "setting_toggle", {"key": key, "value": not current}, admin_id=callback.from_user.id
    )
    await callback.message.edit_text("⚙️ Настройки", reply_markup=await _settings_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("as:edit:"))
async def settings_edit_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":", 2)[2]
    await state.update_data(key=key)
    await state.set_state(AdminSettingsStates.waiting_value)
    label = dict(TEXT_SETTINGS).get(key, key)
    await callback.message.edit_text(f"Введите новое значение для «{label}»:")
    await callback.answer()


@router.message(AdminSettingsStates.waiting_value)
async def settings_edit_apply(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    key = data["key"]
    value = (message.text or "").strip()
    await database.set_setting(key, value)
    await database.add_log(
        "admin", "setting_changed", {"key": key, "value": value}, admin_id=message.from_user.id
    )
    await state.clear()
    await message.answer("✅ Значение обновлено.", reply_markup=await _settings_kb())
