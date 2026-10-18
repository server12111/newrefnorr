import dataclasses
from collections.abc import Mapping
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

import database


def _key(key: StorageKey) -> str:
    # StorageKey's field set differs between aiogram versions, so take
    # whatever fields this one has instead of naming them.
    return ":".join(str(getattr(key, f.name)) for f in dataclasses.fields(key))


class SQLiteStorage(BaseStorage):
    """FSM state kept in bot.db instead of memory, so a restart doesn't drop
    users' current task pool or a half-finished withdrawal."""

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        await database.fsm_set_state(_key(key), value)

    async def get_state(self, key: StorageKey) -> str | None:
        state, _ = await database.fsm_get(_key(key))
        return state

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        await database.fsm_set_data(_key(key), dict(data))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        _, data = await database.fsm_get(_key(key))
        return data

    async def close(self) -> None:
        pass
