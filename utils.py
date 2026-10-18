import math

from config import ADMIN_IDS


def parse_amount(text: str | None, allow_zero: bool = False) -> float | None:
    """Parses an admin-entered star amount. Rejects nan/inf and negatives
    (float() happily accepts "nan", which would poison a balance)."""
    try:
        value = float((text or "").strip().replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        return None
    return value


def is_admin(telegram_id: int) -> bool:
    return telegram_id in ADMIN_IDS


def fmt_stars(amount: float) -> str:
    return f"{amount:g} ⭐"


def user_display(username: str | None, telegram_id: int) -> str:
    return f"@{username}" if username else f"ID {telegram_id}"
