import logging

import aiohttp

import database
from config import BOT_TOKEN

logger = logging.getLogger("gift_service")

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


class GiftError(Exception):
    pass


async def _call(method: str, payload: dict) -> dict:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.post(f"{API_URL}/{method}", json=payload) as resp:
            data = await resp.json()
    if not data.get("ok"):
        raise GiftError(data.get("description", "unknown Telegram API error"))
    return data["result"]


async def get_star_balance() -> int:
    result = await _call("getMyStarBalance", {})
    return result.get("amount", 0)


async def get_available_gifts() -> list[dict]:
    result = await _call("getAvailableGifts", {})
    return result.get("gifts", [])


async def send_gift(user_id: int, gift_id: str, text: str | None = None) -> dict:
    payload = {"user_id": user_id, "gift_id": gift_id}
    if text:
        payload["text"] = text
    return await _call("sendGift", payload)


async def send_picked_gift(
    admin_id: int, target_user_id: int, gift_id: str, star_count: int, emoji: str, text: str | None
) -> tuple[bool, str]:
    try:
        balance = await get_star_balance()
    except GiftError as exc:
        return False, f"❌ Не удалось получить баланс Stars: {exc}"

    if balance < star_count:
        return False, f"❌ Недостаточно Stars\n\n💫 Баланс: {balance} ⭐\n🎁 Нужно: {star_count} ⭐"

    try:
        await send_gift(target_user_id, gift_id, text)
    except GiftError as exc:
        await database.log_gift(target_user_id, gift_id, emoji, star_count, "failed", admin_id, str(exc))
        await database.add_log(
            "gift", "send_failed", {"target": target_user_id, "gift_id": gift_id, "error": str(exc)}, admin_id=admin_id
        )
        return False, f"❌ Ошибка отправки подарка\n\n{exc}"

    await database.log_gift(target_user_id, gift_id, emoji, star_count, "sent", admin_id)
    await database.add_log(
        "gift", "sent", {"target": target_user_id, "gift_id": gift_id, "price": star_count}, admin_id=admin_id
    )
    return True, f"{emoji} Подарок отправлен!\n\n👤 Получатель: {target_user_id}\n💫 Стоимость: {star_count} ⭐"
