import logging

from config import TRAFFY_TOKEN
from integrations.base import IntegrationError, TaskItem, get_session, is_telegram_target

logger = logging.getLogger("integrations.traffy")

PROVIDER = "traffy"
BASE_URL = "https://api.traffy.ai/publisher"


def _headers() -> dict:
    return {"x-publisher-api-key": TRAFFY_TOKEN}


async def get_tasks(
    telegram_id: int,
    first_name: str | None,
    username: str | None,
    language_code: str | None,
    exclude: list[str] | None = None,
) -> list[TaskItem]:
    if not TRAFFY_TOKEN:
        return []
    payload = {"telegram_id": telegram_id, "limit": 10}
    if first_name:
        payload["first_name"] = first_name
    if username:
        payload["username"] = username
    if language_code:
        payload["language_code"] = language_code
    # exclude holds our own assignment ids, which are not resource ids -
    # sending them made Traffy return nothing on repeat calls. Filtering is
    # done locally instead.

    session = await get_session()
    try:
        async with session.post(f"{BASE_URL}/tasks", json=payload, headers=_headers()) as resp:
            data = await resp.json(content_type=None)
    except Exception as exc:
        raise IntegrationError(f"traffy get_tasks failed: {exc}") from exc

    if not data.get("ok"):
        return []

    tasks = []
    for item in data.get("tasks") or []:
        if not is_telegram_target(item.get("type"), item.get("target_resource_telegram_id"), item.get("target_link")):
            continue
        tasks.append(
            TaskItem(
                provider=PROVIDER,
                external_id=str(item.get("assignment_id")),
                title=item.get("title") or "Спонсор",
                link=item.get("target_link"),
                extra={
                    "button_text": item.get("button_text"),
                    "resource_id": item.get("target_resource_telegram_id"),
                },
            )
        )
    return tasks


async def check_task(telegram_id: int, task: TaskItem) -> bool:
    if not TRAFFY_TOKEN:
        return False
    payload = {"telegram_id": telegram_id, "assignment_id": task.external_id}
    session = await get_session()
    try:
        async with session.post(f"{BASE_URL}/tasks/check", json=payload, headers=_headers()) as resp:
            data = await resp.json(content_type=None)
    except Exception as exc:
        raise IntegrationError(f"traffy check_task failed: {exc}") from exc

    if not data.get("ok"):
        return False
    logger.info("traffy check %s -> %s", task.external_id, data.get("results"))
    for result in data.get("results") or []:
        if str(result.get("assignment_id")) == task.external_id:
            return result.get("status") in ("completed", "complete", "done", "success")
    return False
