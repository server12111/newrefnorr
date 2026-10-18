import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

import database
from keyboards.user import back_kb
from menu_render import show_main_menu

router = Router(name="menu")


@router.callback_query(F.data == "menu:ad")
async def ad_block(callback: CallbackQuery) -> None:
    url = await database.get_setting("ad_block_url", "")
    text = await database.get_setting("ad_block_text", "Тут могла быть ваша реклама")
    # ad_block_text is also a button label (plain text), so it's stored
    # unescaped and escaped here for the HTML message
    body = f"📢 {html.escape(text)}"
    if url:
        body += f"\n\n{html.escape(url)}"
    else:
        body += "\n\nРазмещение рекламы: обратитесь к администратору."

    if callback.message.photo:
        await callback.message.delete()
        await callback.bot.send_message(callback.message.chat.id, body, reply_markup=back_kb("menu:back"))
    else:
        await callback.message.edit_text(body, reply_markup=back_kb("menu:back"))
    await callback.answer()


@router.callback_query(F.data == "menu:back")
async def back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    # leave any input mode (withdraw username, promo...) so the next text the
    # user sends isn't swallowed by it; data (task pool) is kept
    await state.set_state(None)
    await show_main_menu(callback)
    await callback.answer()
