import logging

from config import AXIONNA_TOKEN
from integrations.base import IntegrationError, TaskItem, get_session, is_telegram_target

logger = logging.getLogger("integrations.axionna")

PROVIDER = "axionna"
BASE_URL = "https://axionna.org/api"


def _headers() -> dict:
    return {"Authorization": f"Bearer {AXIONNA_TOKEN}"}


async def get_tasks(user_id: int, limit: int = 10) -> list[TaskItem]:
    if not AXIONNA_TOKEN:
        return []
    # chat_id is required even for a private-chat user: without it the API
    # answers E-0003.
    payload = {"user_id": user_id, "chat_id": user_id, "max_sponsors": min(max(limit, 1), 20)}

    session = await get_session()
    try:
        async with session.post(f"{BASE_URL}/sponsors", json=payload, headers=_headers()) as resp:
            data = await resp.json(content_type=None)
    except Exception as exc:
        raise IntegrationError(f"axionna get_tasks failed: {exc}") from exc

    if data.get("error_code"):
        raise IntegrationError(f"axionna error: {data.get('error_code')}")

    tasks = []
    for item in data.get("sponsors") or []:
        link = item.get("target_url") or item.get("link")
        if not is_telegram_target(item.get("target_kind"), None, link):
            continue
        reward = item.get("reward") or item.get("price") or 0
        try:
            reward = float(reward)
        except (TypeError, ValueError):
            reward = 0.0
        tasks.append(
            TaskItem(
                provider=PROVIDER,
                external_id=str(item.get("id")),
                title=item.get("title") or "Спонсор",
                link=link,
                reward=reward,
                extra={
                    "target_kind": item.get("target_kind"),
                    "source": item.get("source"),
                    "verification_mode": item.get("verification_mode"),
                },
            )
        )
    return tasks


async def check_task(user_id: int, task: TaskItem) -> bool:
    if not AXIONNA_TOKEN:
        return False
    payload = {"user_id": user_id, "task_ids": [task.external_id]}
    session = await get_session()
    try:
        async with session.post(f"{BASE_URL}/check", json=payload, headers=_headers()) as resp:
            data = await resp.json(content_type=None)
    except Exception as exc:
        raise IntegrationError(f"axionna check_task failed: {exc}") from exc

    logger.info("axionna check %s -> %s", task.external_id, data.get("results"))
    for result in data.get("results") or []:
        if str(result.get("id")) == task.external_id:
            # not_allowed = counted on their side as anti-fraud/targeting
            # rejection - the docs are explicit that we must not pay for it.
            return result.get("status") == "ok"
    return False
