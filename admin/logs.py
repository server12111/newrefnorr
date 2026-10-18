import os

from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

import database
from admin.common import AdminFilter
from config import LOG_FILE_PATH

router = Router(name="admin_logs")
router.callback_query.filter(AdminFilter())

CATEGORIES = [
    ("all", "📄 Все"),
    ("task", "❌ Ошибки заданий"),
    ("withdrawal", "💰 Выводы"),
    ("gift", "🎁 Подарки"),
    ("user", "👤 Пользователи"),
    ("admin", "🛠 Админ"),
    ("promo", "🎟 Промокоды"),
]


def _logs_kb(current: str) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for cat, label in CATEGORIES:
        marker = "• " if cat == current else ""
        style = ButtonStyle.SUCCESS if cat == current else ButtonStyle.PRIMARY
        row.append(InlineKeyboardButton(text=f"{marker}{label}", callback_data=f"al:cat:{cat}", style=style))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(text="📄 Последние 300 строк", callback_data="al:tail", style=ButtonStyle.PRIMARY),
            InlineKeyboardButton(text="📎 Весь файл", callback_data="al:file", style=ButtonStyle.PRIMARY),
        ]
    )
    rows.append([InlineKeyboardButton(text="◀️ В админ-меню", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _logs_text(category: str) -> str:
    logs = await database.list_logs(category, limit=15)
    if not logs:
        return "📄 Логи\n\nЗаписей нет."
    lines = ["📄 Логи\n"]
    for log in logs:
        admin_part = f" (admin {log['admin_id']})" if log["admin_id"] else ""
        lines.append(f"[{log['created_at']}] {log['category']}: {log['action']}{admin_part}")
    return "\n".join(lines)


@router.callback_query(F.data == "admin:logs")
async def logs_menu(callback: CallbackQuery) -> None:
    text = await _logs_text("all")
    await callback.message.edit_text(text, reply_markup=_logs_kb("all"))
    await callback.answer()


@router.callback_query(F.data.startswith("al:cat:"))
async def logs_filter(callback: CallbackQuery) -> None:
    category = callback.data.split(":")[2]
    text = await _logs_text(category)
    await callback.message.edit_text(text, reply_markup=_logs_kb(category))
    await callback.answer()


@router.callback_query(F.data == "al:tail")
async def logs_tail(callback: CallbackQuery) -> None:
    if not os.path.exists(LOG_FILE_PATH):
        await callback.answer("Файл логов пока не создан.", show_alert=True)
        return
    with open(LOG_FILE_PATH, "rb") as f:
        lines = f.read().decode("utf-8", errors="replace").splitlines()
    tail = "\n".join(lines[-300:]).encode("utf-8")
    await callback.message.answer_document(
        BufferedInputFile(tail, filename="last_300_lines.log"),
        caption=f"📄 Последние {min(300, len(lines))} строк",
    )
    await callback.answer()


@router.callback_query(F.data == "al:file")
async def logs_full_file(callback: CallbackQuery) -> None:
    if not os.path.exists(LOG_FILE_PATH):
        await callback.answer("Файл логов пока не создан.", show_alert=True)
        return
    await callback.message.answer_document(FSInputFile(LOG_FILE_PATH), caption="📎 Полный лог-файл")
    await callback.answer()
