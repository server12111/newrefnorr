from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import database
from admin.common import AdminFilter
from handlers.leaderboards import render_leaderboard_text
from keyboards.admin import back_to_admin_kb
from keyboards.user import leaderboard_kb, leaderboard_kind_kb
from menu_render import safe_edit_text
from services.leaderboard_service import compute_prize, get_daily_invite_prize_tiers, top_rows
from utils import fmt_stars, user_display

router = Router(name="admin_statistics")
router.callback_query.filter(AdminFilter())


def _stats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏆 Топы", callback_data="atopkind", style=ButtonStyle.PRIMARY)],
            [InlineKeyboardButton(text="◀️ В админ-меню", callback_data="admin:menu")],
        ]
    )


@router.callback_query(F.data == "atopkind")
async def admin_choose_kind(callback: CallbackQuery) -> None:
    kb = leaderboard_kind_kb(prefix="atop", back_cb="admin:stats")
    await safe_edit_text(callback.message, "🏆 Топы\n\nВыбери раздел:", kb)
    await callback.answer()


@router.callback_query(F.data == "admin:stats")
async def show_stats(callback: CallbackQuery) -> None:
    total_users = await database.count_users()
    new_today = await database.count_active_users(1)
    new_week = await database.count_active_users(7)
    new_month = await database.count_active_users(30)

    tasks_completed = await database.count_completed_tasks()
    balances = await database.sum_balances()
    withdrawals_count, withdrawals_sum = await database.withdrawal_stats()

    cur = await database.conn().execute("SELECT COUNT(*) AS c, COALESCE(SUM(referral_confirmed),0) AS s FROM users")
    row = await cur.fetchone()
    total_refs_rows = await database.conn().execute("SELECT COUNT(*) AS c FROM users WHERE referrer_id IS NOT NULL")
    total_refs = (await total_refs_rows.fetchone())["c"]
    confirmed_refs = row["s"]

    text = (
        "📊 Статистика\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"🆕 Новых сегодня: {new_today}\n"
        f"🆕 За 7 дней: {new_week}\n"
        f"🆕 За 30 дней: {new_month}\n\n"
        f"📋 Выполнено заданий: {tasks_completed}\n\n"
        f"👥 Всего рефералов: {total_refs}\n"
        f"✅ Засчитанных: {confirmed_refs}\n\n"
        f"⭐ Баланс пользователей: {fmt_stars(balances)}\n\n"
        f"📤 Выводов (выплачено): {withdrawals_count}\n"
        f"💰 Выведено: {fmt_stars(withdrawals_sum)}"
    )
    await safe_edit_text(callback.message, text, _stats_kb())
    await callback.answer()


def _admin_leaderboard_kb(kind: str, period: str, prize_target: int | None) -> InlineKeyboardMarkup:
    kb = leaderboard_kb(kind, period, prefix="atop")
    rows = list(kb.inline_keyboard)
    if prize_target is not None:
        rows.insert(
            -1,
            [
                InlineKeyboardButton(
                    text="➕ Начислить приз победителю",
                    callback_data=f"atopprize:{prize_target}",
                    style=ButtonStyle.SUCCESS,
                )
            ],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("atop:"))
async def admin_leaderboard(callback: CallbackQuery) -> None:
    _, kind, period = callback.data.split(":")
    text = await render_leaderboard_text(kind, period)

    prize_target = None
    if kind == "invites" and period == "day":
        rows = await top_rows("invites", "day", limit=1)
        tiers = await get_daily_invite_prize_tiers()
        already_awarded = await database.has_log_today("admin", "daily_invite_prize")
        if rows and not already_awarded:
            winner = rows[0]
            prize = compute_prize(winner["cnt"], tiers)
            if prize:
                prize_target = winner["user_id"]
        if already_awarded:
            text += "\n✅ Приз за сегодня уже выдан."

    await safe_edit_text(callback.message, text, _admin_leaderboard_kb(kind, period, prize_target))
    await callback.answer()


@router.callback_query(F.data.startswith("atopprize:"))
async def admin_award_prize(callback: CallbackQuery) -> None:
    target_id = int(callback.data.split(":")[1])
    if await database.has_log_today("admin", "daily_invite_prize"):
        await callback.answer("Приз за сегодня уже выдан.", show_alert=True)
        return

    rows = await top_rows("invites", "day", limit=1)
    if not rows or rows[0]["user_id"] != target_id:
        await callback.answer("Лидер за сутки изменился, обновите экран.", show_alert=True)
        return

    tiers = await get_daily_invite_prize_tiers()
    prize = compute_prize(rows[0]["cnt"], tiers)
    if not prize:
        await callback.answer("Приз не положен - порог не достигнут.", show_alert=True)
        return

    # has_log_today above is a read; this is the atomic claim that stops two
    # admins pressing at once from both paying out
    if not await database.claim_daily_prize(target_id, prize):
        await callback.answer("Приз за сегодня уже выдан.", show_alert=True)
        return
    await database.adjust_balance(target_id, prize)
    await database.add_log(
        "admin",
        "daily_invite_prize",
        {"target": target_id, "invites": rows[0]["cnt"], "prize": prize},
        admin_id=callback.from_user.id,
    )

    who = user_display(rows[0]["username"], target_id)
    await callback.answer(f"Начислено {prize:g} ⭐ пользователю {who}", show_alert=True)

    text = await render_leaderboard_text("invites", "day")
    text += f"\n✅ Уже начислено {prize:g} ⭐ ({who})"
    await safe_edit_text(callback.message, text, _admin_leaderboard_kb("invites", "day", None))
