import logging

import database

logger = logging.getLogger("referral_service")


def format_user_mention(username: str | None, telegram_id: int) -> str:
    return f"@{username}" if username else f"ID {telegram_id}"


async def register_user(
    telegram_id: int, username: str | None, first_name: str | None, start_arg: str | None, bot=None
):
    existing = await database.get_user(telegram_id)
    if existing:
        await database.update_user_profile(telegram_id, username, first_name)
        return existing, False

    referrer_id = None
    if start_arg and start_arg.isdigit():
        candidate = int(start_arg)
        if candidate != telegram_id:
            referrer = await database.get_user(candidate)
            if referrer:
                referrer_id = candidate

    user = await database.create_user(telegram_id, username, first_name, referrer_id)
    await database.add_log(
        "user", "registered", {"telegram_id": telegram_id, "referrer_id": referrer_id}
    )

    if referrer_id and bot is not None:
        mention = format_user_mention(username, telegram_id)
        required = await database.get_setting_int("referral_required_tasks", 8)
        try:
            await bot.send_message(
                referrer_id,
                f"⚡ Пользователь {mention} присоединился по вашей ссылке!\n"
                f"Вы получите награду когда он выполнит {required} заданий.",
            )
        except Exception as exc:
            logger.info("could not notify referrer %s: %s", referrer_id, exc)

    return user, True


async def process_referral_progress(bot, telegram_id: int) -> None:
    user = await database.get_user(telegram_id)
    if not user or not user["referrer_id"] or user["referral_confirmed"]:
        return

    required = await database.get_setting_int("referral_required_tasks", 8)
    if user["tasks_completed"] < required:
        return

    if not await database.confirm_referral(telegram_id):
        return  # a concurrent call already confirmed and paid
    reward = await database.get_setting_float("referral_reward", 5)
    if reward:
        await database.adjust_balance(user["referrer_id"], reward)
    await database.add_log(
        "user",
        "referral_confirmed",
        {"referrer_id": user["referrer_id"], "referral_id": telegram_id, "reward": reward},
    )

    mention = format_user_mention(user["username"], telegram_id)
    try:
        await bot.send_message(
            user["referrer_id"],
            f"👤 Пользователь {mention} выполнил {required} заданий, вы получили {reward:g} ⭐",
        )
    except Exception as exc:
        logger.info("could not notify referrer %s: %s", user["referrer_id"], exc)
