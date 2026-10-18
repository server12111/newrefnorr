from aiogram import F, Router
from aiogram.types import CallbackQuery

from admin.common import AdminFilter
from keyboards.admin import back_to_admin_kb

router = Router(name="admin_chats")
router.callback_query.filter(AdminFilter())


@router.callback_query(F.data == "admin:chats")
async def chats_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "💬 Список чатов\n\n"
        "Модуль учёта чатов ещё не реализован в этой версии бота.",
        reply_markup=back_to_admin_kb(),
    )
    await callback.answer()
