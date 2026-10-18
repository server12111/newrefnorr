from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import premium_emoji as pe
from services.leaderboard_service import PERIODS


def _btn(text: str, fallback: str, emoji_id: str, **kwargs) -> InlineKeyboardButton:
    label, extra = pe.label(text, fallback, emoji_id)
    return InlineKeyboardButton(text=label, **extra, **kwargs)


def main_menu_inline(ad_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("Задания", "📋", pe.PLAY, callback_data="menu:tasks", style=ButtonStyle.SUCCESS)],
            [
                _btn("Профиль", "👤", pe.PROFILE, callback_data="menu:profile", style=ButtonStyle.PRIMARY),
                _btn("Рефералы", "👥", pe.USERS, callback_data="menu:referrals", style=ButtonStyle.PRIMARY),
            ],
            [InlineKeyboardButton(text=f"📢 {ad_text}", callback_data="menu:ad", style=ButtonStyle.PRIMARY)],
            [_btn("Вывод", "💰", pe.STAR, callback_data="menu:withdraw", style=ButtonStyle.DANGER)],
        ]
    )


def task_kb(link: str | None, track_click: bool = False, revealed: bool = False) -> InlineKeyboardMarkup:
    top_row = [InlineKeyboardButton(text="⏭ Пропустить", callback_data="task:skip")]
    if link:
        # answerCallbackQuery's url field only accepts t.me/<this bot>?start=...
        # deep links (or a registered Game) - Telegram rejects any other URL
        # with URL_INVALID, so a callback button can't redirect to an
        # arbitrary external bot/channel link directly. Two-step instead:
        # first tap is a plain callback (real server-side signal we can
        # record), which reveals a genuine url= button for the actual link.
        if track_click and not revealed:
            go_button = _btn("Перейти", "▶️", pe.LINK, callback_data="task:go")
        else:
            go_button = _btn("Открыть ссылку", "🔗", pe.LINK, url=link, style=ButtonStyle.SUCCESS)
        top_row.insert(0, go_button)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            top_row,
            [
                InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back"),
                _btn("Проверить", "🔎", pe.CHECK, callback_data="task:check", style=ButtonStyle.SUCCESS),
            ],
        ]
    )


def no_tasks_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="task:refresh", style=ButtonStyle.PRIMARY)],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back")],
        ]
    )


def profile_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎟 Промокод", callback_data="profile:promo", style=ButtonStyle.PRIMARY)],
            [InlineKeyboardButton(text="📜 История выводов", callback_data="profile:history", style=ButtonStyle.PRIMARY)],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back")],
        ]
    )


def back_kb(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=callback_data)]]
    )


def referrals_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("Топ рефералов", "🏆", pe.TROPHY, callback_data="topkind", style=ButtonStyle.PRIMARY)],
            [_btn("Мои рефералы", "👥", pe.USERS, callback_data="ref:list", style=ButtonStyle.PRIMARY)],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back")],
        ]
    )


def leaderboard_kind_kb(prefix: str = "top", back_cb: str = "menu:referrals") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Приглашения", callback_data=f"{prefix}:invites:day", style=ButtonStyle.PRIMARY)],
            [InlineKeyboardButton(text="📋 Задания", callback_data=f"{prefix}:tasks:day", style=ButtonStyle.PRIMARY)],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=back_cb)],
        ]
    )


def leaderboard_kb(kind: str, period: str, prefix: str = "top", back_cb: str | None = None) -> InlineKeyboardMarkup:
    if back_cb is None:
        back_cb = "topkind" if prefix == "top" else "atopkind"
    period_buttons = [
        InlineKeyboardButton(
            text=("• " if p == period else "") + label,
            callback_data=f"{prefix}:{kind}:{p}",
            style=ButtonStyle.SUCCESS if p == period else ButtonStyle.PRIMARY,
        )
        for p, label in PERIODS
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            period_buttons[:2],
            period_buttons[2:],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=back_cb)],
        ]
    )


def withdraw_amount_kb(amounts: list[int]) -> InlineKeyboardMarkup:
    row = [
        _btn(f"{a}", "⭐", pe.STAR, callback_data=f"wd:amount:{a}", style=ButtonStyle.SUCCESS)
        for a in amounts
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[row, [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back")]]
    )


def withdraw_method_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("Подарком", "🎁", pe.GIFT, callback_data="wd:method:gift", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text="💎 Через Fragment", callback_data="wd:method:fragment", style=ButtonStyle.PRIMARY),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:withdraw")],
        ]
    )


def withdraw_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("Подтвердить", "✅", pe.CHECK, callback_data="wd:confirm", style=ButtonStyle.SUCCESS),
                _btn("Отмена", "❌", pe.CROSS, callback_data="menu:back", style=ButtonStyle.DANGER),
            ]
        ]
    )


def cancel_kb(callback_data: str = "menu:back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn("Отмена", "❌", pe.CROSS, callback_data=callback_data, style=ButtonStyle.DANGER)]]
    )


def gate_kb(sponsors, clicked_bot_ids: set[int] = frozenset()) -> InlineKeyboardMarkup:
    rows = []
    for s in sponsors:
        if s["target_type"] == "bot" and s["id"] not in clicked_bot_ids:
            # Same two-step reveal as task_kb: a plain url button never
            # notifies the bot, so the first tap has to be a callback that
            # records the click before we can show the real link.
            rows.append([InlineKeyboardButton(text=f"▶️ {s['name']}", callback_data=f"gate:go:{s['id']}")])
        elif s["target_type"] == "bot":
            rows.append([InlineKeyboardButton(text=f"🔗 Открыть: {s['name']}", url=s["url"], style=ButtonStyle.SUCCESS)])
        else:
            rows.append([InlineKeyboardButton(text=f"📢 {s['name']}", url=s["url"])])
    rows.append([_btn("Проверить подписку", "🔎", pe.CHECK, callback_data="gate:check", style=ButtonStyle.SUCCESS)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
