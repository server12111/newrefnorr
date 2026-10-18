import database
from utils import user_display


class WithdrawalError(Exception):
    pass


STATUS_ICON = {"pending": "⏳", "paid": "✅", "rejected": "❌"}
STATUS_TEXT = {"pending": "На рассмотрении", "paid": "Принято", "rejected": "Отклонено"}


def method_label(method: str | None) -> str | None:
    if method == "gift":
        return "🎁 Подарком"
    if method == "fragment":
        return "💎 Через Fragment"
    return None


def channel_url(setting_value: str | None) -> str | None:
    """Normalizes a settings value (which may be @username, a raw username,
    or already a full t.me link) into a clickable https://t.me/... URL."""
    if not setting_value:
        return None
    value = setting_value.strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://t.me/{value.lstrip('@')}"


def admin_channel_text(
    withdrawal_id: int,
    user_id: int,
    username: str | None,
    recipient_username: str,
    amount: float,
    method: str | None = None,
) -> str:
    who = user_display(username, user_id)
    lines = [
        f"📌 Новая заявка на вывод #{withdrawal_id}",
        "",
        f"👤 Пользователь: {who} | ID: {user_id}",
        f"🎁 Получатель: @{recipient_username}",
        f"💫 Получит: {amount:g} Telegram ⭐",
    ]
    label = method_label(method)
    if label:
        lines.append(f"💳 Способ: {label}")
    lines.append("⏳ Статус: На рассмотрении")
    return "\n".join(lines)


def public_channel_text(withdrawal_id: int, user_id: int, recipient_username: str, amount: float, status: str = "pending") -> str:
    icon = STATUS_ICON.get(status, "⏳")
    label = STATUS_TEXT.get(status, status)
    return (
        f"📌 Запрос на вывод #{withdrawal_id}\n\n"
        f"👤 Получатель: @{recipient_username} | ID: {user_id}\n"
        f"💫 Получит: {amount:g} Telegram ⭐\n"
        f"{icon} Статус: {label}"
    )


async def request_withdrawal(
    telegram_id: int,
    username: str | None,
    amount: float,
    recipient_username: str,
    payout_method: str | None = None,
) -> int:
    if not await database.get_setting_bool("withdraw_enabled", True):
        raise WithdrawalError("Вывод временно отключён администратором.")

    min_withdraw = await database.get_setting_float("min_withdraw", 15)
    if amount < min_withdraw:
        raise WithdrawalError(f"Минимальная сумма вывода: {min_withdraw:g} ⭐")

    # Reserve funds immediately so the same balance can't be requested twice
    # while the withdrawal is pending manual admin processing. The check and
    # the debit are one UPDATE so concurrent requests can't both pass.
    if not await database.try_debit(telegram_id, amount):
        raise WithdrawalError("Недостаточно средств на балансе.")
    withdrawal_id = await database.create_withdrawal(
        telegram_id, username, amount, recipient_username, payout_method
    )
    await database.add_log(
        "withdrawal",
        "requested",
        {"withdrawal_id": withdrawal_id, "user_id": telegram_id, "amount": amount, "method": payout_method},
    )
    return withdrawal_id


async def approve_withdrawal(withdrawal_id: int, admin_id: int, comment: str | None = None) -> bool:
    if not await database.finish_withdrawal(withdrawal_id, "paid", comment):
        return False
    await database.add_log(
        "withdrawal", "approved", {"withdrawal_id": withdrawal_id}, admin_id=admin_id
    )
    return True


async def reject_withdrawal(withdrawal_id: int, admin_id: int, comment: str | None = None) -> bool:
    if not await database.finish_withdrawal(withdrawal_id, "rejected", comment):
        return False
    withdrawal = await database.get_withdrawal(withdrawal_id)
    await database.adjust_balance(withdrawal["user_id"], withdrawal["amount"])
    await database.add_log(
        "withdrawal", "rejected", {"withdrawal_id": withdrawal_id}, admin_id=admin_id
    )
    return True


STATUS_LABELS = {
    "pending": "⏳ Обработка",
    "paid": "✅ Выплачено",
    "rejected": "❌ Отклонено",
}
