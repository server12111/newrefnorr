from aiogram import F, Router
from aiogram.types import CallbackQuery

from keyboards.user import leaderboard_kb, leaderboard_kind_kb
from menu_render import edit_screen
from services.leaderboard_service import PERIOD_LABELS, get_daily_invite_prize_tiers, tiers_legend, top_rows
from utils import user_display

router = Router(name="leaderboards")

MEDALS = ["🥇", "🥈", "🥉"]


async def render_leaderboard_text(kind: str, period: str) -> str:
    label = PERIOD_LABELS.get(period, period)
    title = "📢 Топ приглашений" if kind == "invites" else "📋 Топ заданий"
    rows = await top_rows(kind, period, limit=10)

    if not rows:
        text = f"{title} ({label})\n\nПока пусто."
    else:
        lines = [f"{title} ({label})", ""]
        for idx, row in enumerate(rows):
            who = user_display(row["username"], row["user_id"])
            prefix = MEDALS[idx] if idx < 3 else f"{idx + 1}."
            lines.append(f"{prefix} {who} — {row['cnt']}")
        text = "\n".join(lines)

    if kind == "invites" and period == "day":
        tiers = await get_daily_invite_prize_tiers()
        thresholds = "/".join(str(t) for t, _ in tiers)
        legend = tiers_legend(tiers)
        text += f"\n\n🎁 Награда за 1-е место за сутки: {legend} ⭐ (от {thresholds} приглашений)"

    return text


@router.callback_query(F.data == "topkind")
async def choose_leaderboard_kind(callback: CallbackQuery) -> None:
    await edit_screen(callback, "🏆 Топы\n\nВыбери раздел:", leaderboard_kind_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("top:"))
async def show_leaderboard(callback: CallbackQuery) -> None:
    _, kind, period = callback.data.split(":")
    text = await render_leaderboard_text(kind, period)
    await edit_screen(callback, text, leaderboard_kb(kind, period))
    await callback.answer()
