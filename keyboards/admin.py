from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import premium_emoji as pe


def _btn(text: str, fallback: str, emoji_id: str, **kwargs) -> InlineKeyboardButton:
    label, extra = pe.label(text, fallback, emoji_id)
    return InlineKeyboardButton(text=label, **extra, **kwargs)


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("Статистика", "📊", pe.CHART, callback_data="admin:stats", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast", style=ButtonStyle.PRIMARY),
            ],
            [
                _btn("Пользователи", "👥", pe.USERS, callback_data="admin:users", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text="🎟 Промокоды", callback_data="admin:promo", style=ButtonStyle.PRIMARY),
            ],
            [
                InlineKeyboardButton(text="📋 Задания", callback_data="admin:tasks", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text="🎮 Игры", callback_data="admin:games", style=ButtonStyle.PRIMARY),
            ],
            [
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin:settings", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text="📰 Медиа и тексты", callback_data="admin:media", style=ButtonStyle.PRIMARY),
            ],
            [
                InlineKeyboardButton(text="📢 Свои спонсоры", callback_data="admin:sponsors", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text="🚫 Блок-лист", callback_data="admin:blocklist", style=ButtonStyle.PRIMARY),
            ],
            [_btn("Отправить подарок", "🎁", pe.GIFT, callback_data="admin:gift", style=ButtonStyle.SUCCESS)],
            [
                InlineKeyboardButton(text="💬 Список чатов", callback_data="admin:chats", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text="📄 Логи", callback_data="admin:logs", style=ButtonStyle.PRIMARY),
            ],
        ]
    )


def back_to_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В админ-меню", callback_data="admin:menu")]
        ]
    )


def withdrawal_actions_kb(withdrawal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("Выплатить", "✅", pe.CHECK, callback_data=f"wda:paid:{withdrawal_id}", style=ButtonStyle.SUCCESS),
                _btn("Отклонить", "❌", pe.CROSS, callback_data=f"wda:reject:{withdrawal_id}", style=ButtonStyle.DANGER),
            ]
        ]
    )
