import html
import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import database
from keyboards.user import main_menu_inline

logger = logging.getLogger("menu_render")


async def main_menu_content(first_name: str | None) -> tuple[str, InlineKeyboardMarkup]:
    ad_text = await database.get_setting("ad_block_text", "Тут могла быть ваша реклама")
    welcome_template = await database.get_setting("text_welcome", "😀 Привет, {name}!")
    # names are user-controlled and the bot sends HTML - "<3" or "&" would
    # otherwise make Telegram reject the whole message
    text = welcome_template.replace("{name}", html.escape(first_name or "друг"))
    return text, main_menu_inline(ad_text)


async def safe_edit_text(message: Message, text: str, kb: InlineKeyboardMarkup | None) -> None:
    """edit_text raises if the new content is byte-identical to the current
    message (e.g. tapping an already-selected tab twice) - that's not a real
    error, just nothing to do."""
    try:
        await message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


async def edit_screen(callback: CallbackQuery, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    """Replace the current screen with text + keyboard. edit_text can't touch a
    photo message (the main menu becomes one when a welcome photo is set), so
    fall back to delete + resend in that case."""
    message = callback.message
    if message.photo:
        await message.delete()
        await message.bot.send_message(message.chat.id, text, reply_markup=kb)
    else:
        await safe_edit_text(message, text, kb)


async def send_main_menu(message: Message) -> None:
    """Used from a fresh Message context (e.g. /start) - always sends a new message."""
    text, kb = await main_menu_content(message.from_user.first_name)
    photo_id = await database.get_photo("text_welcome")
    if photo_id:
        try:
            await message.answer_photo(photo_id, caption=text, reply_markup=kb)
            return
        except TelegramBadRequest as exc:
            # e.g. a file_id from another bot - fall back to text rather than
            # leaving /start with no menu at all.
            logger.warning("welcome photo failed: %s", exc)
    await message.answer(text, reply_markup=kb)


async def show_main_menu(callback: CallbackQuery) -> None:
    """Used from a CallbackQuery context (e.g. 'menu:back') - edits the existing
    message in place when possible, since a plain edit_text can't turn a text
    message into a photo message (or vice versa), falls back to delete+resend."""
    text, kb = await main_menu_content(callback.from_user.first_name)
    photo_id = await database.get_photo("text_welcome")
    message = callback.message

    if photo_id:
        if message.photo:
            try:
                await message.edit_caption(caption=text, reply_markup=kb)
                return
            except TelegramBadRequest as exc:
                if "message is not modified" in str(exc):
                    return
        await message.delete()
        try:
            await message.bot.send_photo(message.chat.id, photo_id, caption=text, reply_markup=kb)
        except TelegramBadRequest as exc:
            logger.warning("welcome photo failed: %s", exc)
            await message.bot.send_message(message.chat.id, text, reply_markup=kb)
        return

    if message.photo:
        await message.delete()
        await message.bot.send_message(message.chat.id, text, reply_markup=kb)
        return
    await safe_edit_text(message, text, kb)
