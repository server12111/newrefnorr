import logging

from config import SUBGRAM_TOKEN
from integrations.base import IntegrationError, TaskItem, get_session, is_telegram_target

logger = logging.getLogger("integrations.subgram")

PROVIDER = "subgram"
BASE_URL = "https://api.subgram.org"


def _headers() -> dict:
    return {"Auth": SUBGRAM_TOKEN}


async def get_tasks(
    user_id: int,
    chat_id: int,
    first_name: str | None,
    username: str | None,
    language_code: str | None,
    exclude: list[str] | None = None,
) -> list[TaskItem]:
    if not SUBGRAM_TOKEN:
        return []
    payload = {
        "user_id": user_id,
        "chat_id": chat_id,
        "action": "newtask",
        "max_sponsors": 10,
        "get_links": 1,
    }
    if first_name:
        payload["first_name"] = first_name
    if username:
        payload["username"] = username
    if language_code:
        payload["language_code"] = language_code
    if exclude:
        payload["exclude_resource_ids"] = exclude

    session = await get_session()
    try:
        async with session.post(f"{BASE_URL}/get-sponsors", json=payload, headers=_headers()) as resp:
            data = await resp.json(content_type=None)
    except Exception as exc:
        raise IntegrationError(f"subgram get_tasks failed: {exc}") from exc

    if data.get("status") == "error":
        raise IntegrationError(f"subgram error: {data.get('message')}")

    sponsors = (data.get("additional") or {}).get("sponsors") or []
    tasks = []
    for sponsor in sponsors:
        if not sponsor.get("available_now", True):
            continue
        # already subscribed (now or from before the task) - can't earn a
        # reward for it, so don't offer it as a task
        if sponsor.get("status") in ("subscribed", "notgetted"):
            continue
        if not is_telegram_target(sponsor.get("type"), sponsor.get("resource_id"), sponsor.get("link")):
            continue
        tasks.append(
            TaskItem(
                provider=PROVIDER,
                external_id=str(sponsor.get("resource_id")),
                title=sponsor.get("resource_name") or "Спонсор",
                link=sponsor.get("link"),
                extra={"type": sponsor.get("type")},
            )
        )
    return tasks


async def check_task(user_id: int, task: TaskItem) -> bool:
    if not SUBGRAM_TOKEN:
        return False
    payload = {"user_id": user_id, "links": [task.link]}
    session = await get_session()
    try:
        async with session.post(
            f"{BASE_URL}/get-user-subscriptions", json=payload, headers=_headers()
        ) as resp:
            data = await resp.json(content_type=None)
    except Exception as exc:
        raise IntegrationError(f"subgram check_task failed: {exc}") from exc

    if data.get("status") == "error":
        return False

    sponsors = (data.get("additional") or {}).get("sponsors") or []
    logger.info("subgram check %s -> %s", task.external_id, [(s.get("resource_id"), s.get("status")) for s in sponsors])
    # "notgetted" = user was already subscribed before the task, so Subgram
    # doesn't count (or pay for) it - neither do we.
    ok = ("subscribed", "subpin")
    for sponsor in sponsors:
        if str(sponsor.get("resource_id")) == task.external_id:
            return sponsor.get("status") in ok
    # resource_id can differ in format; fall back to matching by link
    for sponsor in sponsors:
        if sponsor.get("link") and sponsor.get("link") == task.link:
            return sponsor.get("status") in ok
    return len(sponsors) == 1 and sponsors[0].get("status") in ok
