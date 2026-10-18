import logging

from config import FLYER_TOKEN
from integrations.base import IntegrationError, TaskItem, get_session, is_telegram_target

logger = logging.getLogger("integrations.flyer")

PROVIDER = "flyer"
BASE_URL = "https://api.flyerhubs.com"

# Confirmed from a live /get_tasks response (Flyer's docs don't publish this):
# {'signature', 'task', 'resource_id', 'price', 'links': [...], 'photo',
#  'name', 'is_ios_ban', 'status': 'incomplete'|...}
# check_task's response shape is still unconfirmed (couldn't get a live call
# to succeed against an already-expired signature), so that side stays
# defensive and logs its raw payload the first time to self-correct later.
_LOGGED_TASK_SAMPLE = False
_LOGGED_CHECK_SAMPLE = False


def _pick(item: dict, *keys, default=None):
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return default


async def get_tasks(
    user_id: int, language_code: str | None = None, limit: int = 10
) -> list[TaskItem]:
    global _LOGGED_TASK_SAMPLE
    if not FLYER_TOKEN:
        return []
    payload = {"key": FLYER_TOKEN, "user_id": user_id, "limit": limit}
    if language_code:
        payload["language_code"] = language_code

    session = await get_session()
    try:
        async with session.post(f"{BASE_URL}/get_tasks", json=payload) as resp:
            data = await resp.json(content_type=None)
    except Exception as exc:
        raise IntegrationError(f"flyer get_tasks failed: {exc}") from exc

    if data.get("error"):
        raise IntegrationError(f"flyer error: {data.get('error')}")

    raw_items = data.get("result") or []
    if raw_items and not _LOGGED_TASK_SAMPLE:
        logger.info("flyer sample task item (first seen): %s", raw_items[0])
        _LOGGED_TASK_SAMPLE = True

    tasks = []
    for item in raw_items:
        signature = item.get("signature")
        if not signature:
            continue
        if item.get("status") == "complete":
            continue
        if not is_telegram_target(item.get("task"), item.get("resource_id"), (item.get("links") or [None])[0]):
            continue

        links = item.get("links")
        link = links[0] if isinstance(links, list) and links else _pick(item, "link", "url", "channel_link", "target_link")
        title = _pick(item, "name", "task", "title", "channel_name", "resource_name", default="Спонсор")
        reward = item.get("price") or 0

        tasks.append(
            TaskItem(
                provider=PROVIDER,
                external_id=str(signature),
                title=title,
                link=link,
                reward=float(reward),
                extra={"signature": signature, "raw": item},
            )
        )
    return tasks


async def check_task(task: TaskItem) -> bool:
    global _LOGGED_CHECK_SAMPLE
    if not FLYER_TOKEN:
        return False
    signature = task.extra.get("signature", task.external_id)
    payload = {"key": FLYER_TOKEN, "signature": signature}
    session = await get_session()
    try:
        async with session.post(f"{BASE_URL}/check_task", json=payload) as resp:
            data = await resp.json(content_type=None)
    except Exception as exc:
        raise IntegrationError(f"flyer check_task failed: {exc}") from exc

    if not _LOGGED_CHECK_SAMPLE:
        logger.info("flyer sample check_task response: %s", data)
        _LOGGED_CHECK_SAMPLE = True

    if data.get("error"):
        return False

    result = data.get("result")
    if isinstance(result, dict):
        result = result.get("status") or result.get("result")
    if isinstance(result, bool):
        return result
    if isinstance(result, str):
        return result.lower() in ("ok", "complete", "completed", "success", "true", "done")
    return False
