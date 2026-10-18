from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import database
from utils import is_admin

BLOCKED_TEXT = "🚫 Вы заблокированы администратором."


class BlockedUserMiddleware(BaseMiddleware):
    """Drops every update from users an admin has blocked (users.is_blocked)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None or is_admin(user.id):
            return await handler(event, data)

        row = await database.get_user(user.id)
        if not row or not row["is_blocked"]:
            return await handler(event, data)

        try:
            if isinstance(event, CallbackQuery):
                await event.answer(BLOCKED_TEXT, show_alert=True)
            elif isinstance(event, Message) and event.chat.type == "private":
                await event.answer(BLOCKED_TEXT)
        except Exception:
            pass
        return None
