import database

PERIODS = [("day", "Сутки"), ("week", "Неделя"), ("month", "Месяц"), ("all", "Всё время")]
PERIOD_LABELS = {"day": "за сутки", "week": "за неделю", "month": "за месяц", "all": "за всё время"}


def parse_prize_tiers(raw: str) -> list[tuple[int, float]]:
    tiers = []
    for part in raw.split(","):
        if ":" not in part:
            continue
        count_s, reward_s = part.split(":", 1)
        try:
            tiers.append((int(count_s), float(reward_s)))
        except ValueError:
            continue
    return sorted(tiers, key=lambda t: t[0])


def compute_prize(count: int, tiers: list[tuple[int, float]]) -> float:
    prize = 0.0
    for threshold, reward in tiers:
        if count >= threshold:
            prize = reward
    return prize


async def get_daily_invite_prize_tiers() -> list[tuple[int, float]]:
    raw = await database.get_setting("daily_invite_prize_tiers", "10:15,50:25,130:50")
    return parse_prize_tiers(raw)


def tiers_legend(tiers: list[tuple[int, float]]) -> str:
    return "/".join(f"{int(r) if r == int(r) else r:g}" for _, r in tiers)


async def top_rows(kind: str, period: str, limit: int = 10):
    if kind == "invites":
        return await database.top_inviters_period(period, limit)
    return await database.top_task_completers_period(period, limit)
