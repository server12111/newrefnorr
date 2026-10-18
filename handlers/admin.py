from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from admin.common import AdminFilter
from keyboards.admin import admin_menu

router = Router(name="admin_root")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


@router.message(Command("admin"))
async def open_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🔐 Админ-панель\n\nВыбери раздел:", reply_markup=admin_menu())


@router.callback_query(F.data == "admin:menu")
async def back_to_admin(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("🔐 Админ-панель\n\nВыбери раздел:", reply_markup=admin_menu())
    await callback.answer()
