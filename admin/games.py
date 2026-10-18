from aiogram import F, Router
from aiogram.types import CallbackQuery

from admin.common import AdminFilter
from keyboards.admin import back_to_admin_kb

router = Router(name="admin_games")
router.callback_query.filter(AdminFilter())


@router.callback_query(F.data == "admin:games")
async def games_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🎮 Игры\n\n"
        "Модуль игр ещё не реализован в этой версии бота. "
        "Архитектура (services/, admin/) уже готова для подключения игр отдельными модулями "
        "без изменения остальной части бота.",
        reply_markup=back_to_admin_kb(),
    )
    await callback.answer()
