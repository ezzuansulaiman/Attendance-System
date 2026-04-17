from __future__ import annotations

import json
from datetime import date
from typing import Any, Optional

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.models import BotFsmState


def _serialize(data: dict[str, Any]) -> str:
    def _encode(obj: Any) -> Any:
        if isinstance(obj, date):
            return {"__type__": "date", "value": obj.isoformat()}
        raise TypeError(f"Cannot serialize {type(obj)!r}")

    return json.dumps(data, default=_encode)


def _deserialize(raw: str) -> dict[str, Any]:
    def _decode(obj: dict) -> Any:
        if obj.get("__type__") == "date":
            return date.fromisoformat(obj["value"])
        return obj

    return json.loads(raw, object_hook=_decode)


class DatabaseStorage(BaseStorage):
    """Persistent FSM storage backed by the application database.

    Replaces MemoryStorage so in-progress leave flows survive bot restarts.
    """

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def _get_row(self, session, key: StorageKey) -> Optional[BotFsmState]:
        return await session.get(BotFsmState, (key.bot_id, key.chat_id, key.user_id))

    async def _get_or_create_row(self, session, key: StorageKey) -> BotFsmState:
        row = await self._get_row(session, key)
        if row is None:
            row = BotFsmState(bot_id=key.bot_id, chat_id=key.chat_id, user_id=key.user_id)
            session.add(row)
        return row

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        async with self._session_factory() as session:
            row = await self._get_or_create_row(session, key)
            if state is None:
                row.state = None
            elif isinstance(state, State):
                row.state = state.state
            else:
                row.state = str(state)
            await session.commit()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        async with self._session_factory() as session:
            row = await self._get_row(session, key)
            return row.state if row else None

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        async with self._session_factory() as session:
            row = await self._get_or_create_row(session, key)
            row.data_json = _serialize(data) if data else None
            await session.commit()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with self._session_factory() as session:
            row = await self._get_row(session, key)
            if row is None or not row.data_json:
                return {}
            return _deserialize(row.data_json)

    async def close(self) -> None:
        pass
