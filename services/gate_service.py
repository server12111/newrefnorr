import logging

import database

logger = logging.getLogger("gate_service")


async def get_gate_sponsors():
    """Active mandatory sponsors. Channel/chat targets are verified via
    get_chat_member; bot targets can't be (Telegram gives bots no way to
    check whether a user started another bot), so those are verified by
    whether the user pressed "Перейти" instead - see get_unsubscribed."""
    sponsors = await database.list_sponsors(active_only=True, kind="gate")
    return [
        s
        for s in sponsors
        if (s["target_type"] == "channel" and s["external_id"]) or s["target_type"] == "bot"
    ]


async def get_unsubscribed(bot, user_id: int) -> list:
    sponsors = await get_gate_sponsors()
    missing = []
    for sponsor in sponsors:
        if sponsor["target_type"] == "bot":
            passed = await database.has_clicked_sponsor(user_id, sponsor["id"])
        else:
            try:
                member = await bot.get_chat_member(chat_id=sponsor["external_id"], user_id=user_id)
                passed = member.status not in ("left", "kicked")
            except Exception as exc:
                # The bot can't check this channel (removed from it, lost
                # admin rights, channel deleted...). Failing closed would lock
                # every user out of the whole bot, so skip this sponsor.
                logger.warning("gate check failed for sponsor %s, skipping it: %s", sponsor["id"], exc)
                passed = True
        if not passed:
            missing.append(sponsor)
    return missing


async def get_clicked_ids(user_id: int, sponsors) -> set[int]:
    """Which of these bot-type sponsors this user has already pressed
    "Перейти" for - used to decide whether the gate button shows the initial
    callback (records the click) or the revealed real link."""
    ids = set()
    for sponsor in sponsors:
        if sponsor["target_type"] == "bot" and await database.has_clicked_sponsor(user_id, sponsor["id"]):
            ids.add(sponsor["id"])
    return ids


async def record_pass(telegram_id: int, sponsors) -> None:
    # Kept apart from user_tasks: a gate pass isn't a completed task and must
    # not count towards task stats or the tasks leaderboard. Only the first
    # pass per user counts towards the sponsor's click goal.
    for sponsor in sponsors:
        if await database.record_gate_pass(telegram_id, sponsor["id"]):
            await database.increment_sponsor_clicks(sponsor["id"])
