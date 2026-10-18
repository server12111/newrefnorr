import asyncio
import logging

import database
from integrations import axionna, botohub, flyer, subgram, tgrass, traffy
from integrations.base import TaskItem

logger = logging.getLogger("task_manager")

# Order in which providers are tried. Own sponsors are prioritized since they
# are typically higher-value / directly managed by the admin.
PROVIDER_ORDER = ["own", "subgram", "flyer", "tgrass", "botohub", "traffy", "axionna"]


async def _own_sponsor_tasks(user_row, completed_ids: set[str], exclude: set[str]) -> list[TaskItem]:
    tasks = []
    default_reward = await database.get_setting_float("task_reward", 1)
    for sponsor in await database.list_sponsors(active_only=True, kind="task"):
        sid = str(sponsor["id"])
        if sid in completed_ids or sid in exclude:
            continue
        if sponsor["external_id"] and await database.is_sponsor_blocked("own", sponsor["external_id"]):
            continue
        reward = sponsor["reward"] if sponsor["reward"] and sponsor["reward"] > 0 else default_reward
        tasks.append(
            TaskItem(
                provider="own",
                external_id=sid,
                title=sponsor["name"],
                link=sponsor["url"],
                reward=reward,
                extra={"target_type": sponsor["target_type"], "has_chat_id": bool(sponsor["external_id"])},
            )
        )
    return tasks


async def _provider_tasks(provider: str, user_row, exclude: set[str]) -> list[TaskItem]:
    enabled = await database.get_setting_bool(f"integration_{provider}_enabled", True)
    if not enabled:
        return []

    completed_ids = await database.completed_task_external_ids(user_row["telegram_id"], provider)
    all_exclude = list(completed_ids | exclude)

    try:
        if provider == "subgram":
            raw = await subgram.get_tasks(
                user_row["telegram_id"],
                user_row["telegram_id"],
                user_row["first_name"],
                user_row["username"],
                None,
                exclude=all_exclude,
            )
        elif provider == "flyer":
            raw = await flyer.get_tasks(user_row["telegram_id"])
        elif provider == "tgrass":
            raw = await tgrass.get_tasks(
                user_row["telegram_id"], False, None, user_row["username"], exclude=all_exclude
            )
        elif provider == "botohub":
            raw = await botohub.get_tasks(user_row["telegram_id"], exclude=all_exclude)
        elif provider == "traffy":
            raw = await traffy.get_tasks(
                user_row["telegram_id"],
                user_row["first_name"],
                user_row["username"],
                None,
                exclude=all_exclude,
            )
        elif provider == "axionna":
            raw = await axionna.get_tasks(user_row["telegram_id"])
        else:
            raw = []
    except Exception as exc:
        # Any failure (not just IntegrationError - e.g. an unexpected response
        # shape raising AttributeError) must only drop this provider, not
        # take down the whole task list via asyncio.gather.
        logger.warning("provider %s failed: %r", provider, exc)
        await database.add_log("task", f"{provider}_error", {"error": repr(exc)})
        return []

    default_reward = await database.get_setting_float("task_reward", 1)
    tasks = []
    for item in raw:
        if item.external_id in completed_ids or item.external_id in exclude:
            continue
        if await database.is_sponsor_blocked(provider, item.external_id):
            continue
        # Networks send their own price (Flyer 1.5, Axiona 0.8, ...) - we pay
        # every task the same task_reward from settings, so their number is
        # only bookkeeping on their side.
        item.reward = default_reward
        tasks.append(item)
    return tasks


async def fetch_tasks(user_row, exclude: dict[str, set[str]] | None = None, pool_size: int = 40) -> list[TaskItem]:
    exclude = exclude or {}
    completed_own = await database.completed_task_external_ids(user_row["telegram_id"], "own")

    async def _fetch(provider: str) -> list[TaskItem]:
        prov_exclude = exclude.get(provider, set())
        if provider == "own":
            return await _own_sponsor_tasks(user_row, completed_own, prov_exclude)
        return await _provider_tasks(provider, user_row, prov_exclude)

    # Query every provider concurrently (not one at a time, and not stopping
    # once the pool looks full) then interleave round-robin, so a provider
    # that alone can fill pool_size (e.g. subgram requesting 5 sponsors)
    # can't crowd out every other provider before they're even asked.
    results = await asyncio.gather(*[_fetch(p) for p in PROVIDER_ORDER])

    pool: list[TaskItem] = []
    seen_links: set[str] = set()
    for r in results:
        r[:] = [t for t in r if not (t.link and t.link in seen_links) and not (t.link and seen_links.add(t.link))]
    iterators = [iter(r) for r in results]
    while len(pool) < pool_size and iterators:
        for it in list(iterators):
            try:
                pool.append(next(it))
            except StopIteration:
                iterators.remove(it)
                continue
            if len(pool) >= pool_size:
                break
    return pool


async def check_own_sponsor(bot, user_id: int, task: TaskItem) -> bool:
    sponsor_id = int(task.external_id)
    sponsor = await database.get_sponsor(sponsor_id)
    if not sponsor:
        return False

    if sponsor["target_type"] == "bot":
        # Telegram gives bots no way to verify whether a user has started
        # another bot, so the best we can do is require that they actually
        # pressed "Перейти" (tracked via answerCallbackQuery(url=...) in
        # handlers/tasks.py) before letting the check pass.
        return await database.has_clicked_sponsor(user_id, sponsor_id)

    if not sponsor["external_id"]:
        # No channel id configured for a membership check - same as a bot
        # target, the "Перейти" press is the only signal we have.
        return await database.has_clicked_sponsor(user_id, sponsor_id)
    try:
        member = await bot.get_chat_member(chat_id=sponsor["external_id"], user_id=user_id)
    except Exception as exc:
        logger.warning("own sponsor check failed for %s: %s", sponsor["external_id"], exc)
        return False
    return member.status not in ("left", "kicked")


async def check_task(user_row, task: TaskItem, bot=None, silent: bool = False) -> bool:
    """silent=True is the background pre-check ("did they already do this?"):
    only checks that can't false-positive are allowed."""
    try:
        if task.provider == "own":
            if bot is None:
                return False
            if silent:
                sponsor = await database.get_sponsor(int(task.external_id))
                if not sponsor or sponsor["target_type"] == "bot" or not sponsor["external_id"]:
                    return False
            return await check_own_sponsor(bot, user_row["telegram_id"], task)
        if task.provider == "subgram":
            return await subgram.check_task(user_row["telegram_id"], task)
        if task.provider == "flyer":
            return await flyer.check_task(task)
        if task.provider == "tgrass":
            return await tgrass.check_task(user_row["telegram_id"], task)
        if task.provider == "botohub":
            return await botohub.check_task(user_row["telegram_id"], task)
        if task.provider == "traffy":
            return await traffy.check_task(user_row["telegram_id"], task)
        if task.provider == "axionna":
            return await axionna.check_task(user_row["telegram_id"], task)
    except Exception as exc:
        # same reasoning as _provider_tasks: an unexpected response must give
        # "not done yet", not a crashed handler with a forever-spinning button
        logger.warning("check_task provider %s failed: %r", task.provider, exc)
        await database.add_log("task", f"{task.provider}_check_error", {"error": repr(exc)})
        return False
    return False


async def complete_task(telegram_id: int, task: TaskItem) -> bool:
    """Records completion in DB. Returns True if this was a first-time completion."""
    task_db_id = await database.upsert_task(
        task.provider, task.external_id, task.title, "", task.link, task.reward
    )
    is_new = await database.mark_task_completed(telegram_id, task_db_id)
    if is_new:
        if task.reward:
            await database.adjust_balance(telegram_id, task.reward)
        if task.provider == "own":
            await database.increment_sponsor_clicks(int(task.external_id))
    return is_new
