import logging

from config import TGRASS_TOKEN
from integrations.base import IntegrationError, TaskItem, get_session, is_telegram_target

logger = logging.getLogger("integrations.tgrass")

PROVIDER = "tgrass"
BASE_URL = "https://tgrass.space"


def _headers() -> dict:
    return {"Auth": TGRASS_TOKEN}


async def get_tasks(
    user_id: int,
    is_premium: bool,
    language_code: str | None,
    username: str | None,
    exclude: list[str] | None = None,
) -> list[TaskItem]:
    if not TGRASS_TOKEN:
        return []
    lang = (language_code or "ru")[:2]
    if lang not in ("en", "ru", "uk"):
        lang = "ru"
    payload = {
        "tg_user_id": user_id,
        "is_premium": bool(is_premium),
        "lang": lang,
    }
    if username:
        payload["tg_login"] = username
    if exclude:
        payload["exclude_channels"] = exclude

    session = await get_session()
    try:
        async with session.post(f"{BASE_URL}/offers", json=payload, headers=_headers()) as resp:
            data = await resp.json(content_type=None)
    except Exception as exc:
        raise IntegrationError(f"tgrass get_tasks failed: {exc}") from exc

    if data.get("status") not in ("ok",):
        return []

    offers = data.get("offers") or []
    tasks = []
    for offer in offers:
        if offer.get("subscribed"):
            continue
        if not is_telegram_target(offer.get("type"), offer.get("resource_id") or offer.get("chat_id"), offer.get("link")):
            continue
        tasks.append(
            TaskItem(
                provider=PROVIDER,
                external_id=str(offer.get("offer_id")),
                title=offer.get("name") or "Спонсор",
                link=offer.get("link"),
                extra={"type": offer.get("type")},
            )
        )
    return tasks


async def check_task(user_id: int, task: TaskItem) -> bool:
    if not TGRASS_TOKEN:
        return False
    payload = {"tg_user_id": user_id, "offer_id": int(task.external_id)}
    session = await get_session()
    try:
        async with session.post(f"{BASE_URL}/check", json=payload, headers=_headers()) as resp:
            data = await resp.json(content_type=None)
    except Exception as exc:
        raise IntegrationError(f"tgrass check_task failed: {exc}") from exc

    logger.info("tgrass check %s -> %s", task.external_id, data)
    return data.get("status") in ("subscribed", "ok", "completed")


async def reset_offers(user_id: int) -> None:
    if not TGRASS_TOKEN:
        return
    session = await get_session()
    try:
        await session.post(
            f"{BASE_URL}/reset_offers", json={"tg_user_id": user_id}, headers=_headers()
        )
    except Exception as exc:
        logger.warning("tgrass reset_offers failed: %s", exc)
