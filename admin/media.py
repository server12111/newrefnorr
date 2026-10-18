import html

from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database
from admin.common import AdminFilter
from config import DEFAULT_SETTINGS
from states import AdminMediaStates

router = Router(name="admin_media")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

# Each entry: (settings key, admin-panel label, hint about available placeholders).
# NOTE: photo only actually renders for keys sent as a fresh message
# (text_welcome on /start, text_review_request after a payout). The others are
# edited into text+caption fed through the single-message nav flow (edit_text),
# which can't attach a photo without turning every "Назад" into a
# delete+resend; wire that up in menu_render.py/each handler before expecting
# a photo on those to show anywhere.
TEXT_KEYS = [
    ("text_welcome", "👋 Приветствие", "{name}"),
    ("text_tasks_intro", "📋 Задания (шапка)", "{tasks_reward}"),
    ("text_profile_footer", "👤 Профиль (подпись)", "—"),
    ("text_withdraw_intro", "⭐ Вывод (шапка)", "{balance}, {min}"),
    ("text_withdraw_created", "📤 Заявка создана", "{amount}, {recipient}, {id}"),
    ("text_withdraw_accepted", "✅ Заявка принята", "{amount}, {id}"),
    ("text_review_request", "😋 Просьба оставить отзыв", "—"),
    ("ad_block_text", "📢 Рекламный блок", "—"),
]


def _media_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"am:view:{key}", style=ButtonStyle.PRIMARY)]
        for key, label, _ in TEXT_KEYS
    ]
    rows.append([InlineKeyboardButton(text="◀️ В админ-меню", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _detail_kb(key: str, has_photo: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="✏️ Изменить текст", callback_data=f"am:edittext:{key}", style=ButtonStyle.PRIMARY),
            InlineKeyboardButton(text="🖼 Изменить фото", callback_data=f"am:editphoto:{key}", style=ButtonStyle.PRIMARY),
        ]
    ]
    if has_photo:
        rows.append([InlineKeyboardButton(text="🗑 Удалить фото", callback_data=f"am:delphoto:{key}", style=ButtonStyle.DANGER)])
    rows.append([InlineKeyboardButton(text="🔄 Сбросить текст на дефолт", callback_data=f"am:reset:{key}", style=ButtonStyle.DANGER)])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin:media")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_detail(callback: CallbackQuery, key: str) -> None:
    label, placeholders = next(((l, p) for k, l, p in TEXT_KEYS if k == key), (key, "—"))
    current = await database.get_setting(key, "")
    has_photo = bool(await database.get_photo(key))
    photo_line = "✅ есть" if has_photo else "❌ нет"
    text = (
        f"{label}\n\n"
        f"Текст:\n{html.escape(current)}\n\n"
        f"Фото: {photo_line}\n"
        f"Доступные плейсхолдеры: {placeholders}"
    )
    await callback.message.edit_text(text, reply_markup=_detail_kb(key, has_photo))


@router.callback_query(F.data == "admin:media")
async def media_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "📰 Медиа и тексты\n\nВыберите раздел для редактирования:", reply_markup=_media_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("am:view:"))
async def media_view(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    key = callback.data.split(":", 2)[2]
    await _show_detail(callback, key)
    await callback.answer()


@router.callback_query(F.data.startswith("am:edittext:"))
async def media_edittext_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":", 2)[2]
    await state.update_data(key=key)
    await state.set_state(AdminMediaStates.waiting_value)
    await callback.message.edit_text("Отправьте новый текст:")
    await callback.answer()


@router.callback_query(F.data.startswith("am:editphoto:"))
async def media_editphoto_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":", 2)[2]
    await state.update_data(key=key)
    await state.set_state(AdminMediaStates.waiting_photo)
    await callback.message.edit_text("Отправьте фото:")
    await callback.answer()


@router.callback_query(F.data.startswith("am:delphoto:"))
async def media_delphoto(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":", 2)[2]
    await database.delete_photo(key)
    await database.add_log("admin", "photo_deleted", {"key": key}, admin_id=callback.from_user.id)
    await _show_detail(callback, key)
    await callback.answer("Фото удалено")


@router.callback_query(F.data.startswith("am:reset:"))
async def media_reset(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":", 2)[2]
    default = DEFAULT_SETTINGS.get(key, "")
    await database.set_setting(key, default)
    await database.add_log("admin", "text_reset", {"key": key}, admin_id=callback.from_user.id)
    await state.clear()
    await _show_detail(callback, key)
    await callback.answer("Текст сброшен на дефолт")


@router.message(AdminMediaStates.waiting_value)
async def media_edit_apply(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    key = data.get("key")
    if not key:
        return
    if not message.text:
        await message.answer("❌ Отправьте текст.")
        return
    # Texts are sent with parse_mode=HTML: html_text keeps the admin's
    # bold/italic/links and escapes a bare "<" or "&" that would otherwise make
    # Telegram reject every message using this text. ad_block_text is also a
    # button label (no markup there), so it stays plain and is escaped where
    # it's shown in a message.
    value = message.text if key == "ad_block_text" else message.html_text
    await database.set_setting(key, value)
    await database.add_log("admin", "text_changed", {"key": key}, admin_id=message.from_user.id)
    await state.clear()
    label = next((l for k, l, _ in TEXT_KEYS if k == key), key)
    await message.answer(f"✅ Текст «{label}» обновлён.", reply_markup=_media_kb())


@router.message(AdminMediaStates.waiting_photo)
async def media_photo_apply(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    key = data.get("key")
    if not key:
        return
    if not message.photo:
        await message.answer("❌ Отправьте именно фото (изображение).")
        return
    file_id = message.photo[-1].file_id
    await database.set_photo(key, file_id)
    await database.add_log("admin", "photo_changed", {"key": key}, admin_id=message.from_user.id)
    await state.clear()
    label = next((l for k, l, _ in TEXT_KEYS if k == key), key)
    await message.answer(f"✅ Фото для «{label}» обновлено.", reply_markup=_media_kb())
