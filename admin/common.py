from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from utils import is_admin


class AdminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return is_admin(event.from_user.id)
