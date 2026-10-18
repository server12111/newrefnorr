import logging

from config import BOTOHUB_TOKEN
from integrations.base import IntegrationError, TaskItem, get_session, is_telegram_target

logger = logging.getLogger("integrations.botohub")

PROVIDER = "botohub"
BASE_URL = "https://botohub.me"


def _headers() -> dict:
    return {"Auth": BOTOHUB_TOKEN}


async def _fetch(chat_id: int, exclude: list[str] | None = None) -> dict:
    payload = {"chat_id": chat_id, "only_has_check": False}
    if exclude:
        payload["excluded_ids"] = exclude
    session = await get_session()
    async with session.post(f"{BASE_URL}/get-tasks-extended", json=payload, headers=_headers()) as resp:
        return await resp.json(content_type=None)


async def get_tasks(chat_id: int, exclude: list[str] | None = None) -> list[TaskItem]:
    if not BOTOHUB_TOKEN:
        return []
    try:
        data = await _fetch(chat_id, exclude)
    except Exception as exc:
        raise IntegrationError(f"botohub get_tasks failed: {exc}") from exc

    if "error" in data:
        raise IntegrationError(f"botohub error: {data.get('error')}")

    tasks = []
    for item in data.get("tasks") or []:
        if item.get("completed"):
            continue
        if not is_telegram_target(None, item.get("resource_id"), item.get("url")):
            continue
        tasks.append(
            TaskItem(
                provider=PROVIDER,
                external_id=str(item.get("resource_id")),
                title="Спонсор",
                link=item.get("url"),
            )
        )
    return tasks


async def check_task(chat_id: int, task: TaskItem) -> bool:
    if not BOTOHUB_TOKEN:
        return False
    try:
        data = await _fetch(chat_id)
    except Exception as exc:
        raise IntegrationError(f"botohub check_task failed: {exc}") from exc

    logger.info("botohub check %s -> %s", task.external_id, data)
    if data.get("completed"):
        return True
    for item in data.get("tasks") or []:
        if str(item.get("resource_id")) == task.external_id:
            return bool(item.get("completed"))
    # Not in the list anymore - could be completed, could just be rotated out
    # of the network. Paying on absence let users collect rewards for tasks
    # they never did, so only an explicit "completed" counts.
    return False
