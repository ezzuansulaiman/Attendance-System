import asyncio

import pytest
from aiogram.fsm.storage.base import StorageKey

from bot.db_storage import DatabaseStorage
from bot.states import LeaveApplicationStates


def _make_key() -> StorageKey:
    return StorageKey(bot_id=1, chat_id=-100001, user_id=99999)


@pytest.fixture()
def storage(tmp_path):
    """In-memory SQLite DatabaseStorage for unit tests."""
    import asyncio as _asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from models.database import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    _asyncio.run(_setup())
    return DatabaseStorage(factory)


def test_set_state_stores_plain_state_string(storage):
    """set_state must store the plain state string, not the State object repr.

    In aiogram 3.7+, str(State) returns "<State 'Group:name'>" but
    storage must persist "Group:name" (i.e. State.state) so that
    comparisons in handlers work correctly.
    """
    key = _make_key()

    async def _run():
        await storage.set_state(key, LeaveApplicationStates.start_date)
        return await storage.get_state(key)

    result = asyncio.run(_run())
    assert result == LeaveApplicationStates.start_date.state
    assert result == "LeaveApplicationStates:start_date"
    assert not result.startswith("<State")


def test_set_state_none_clears_state(storage):
    key = _make_key()

    async def _run():
        await storage.set_state(key, LeaveApplicationStates.start_date)
        await storage.set_state(key, None)
        return await storage.get_state(key)

    result = asyncio.run(_run())
    assert result is None


def test_set_state_accepts_plain_string(storage):
    key = _make_key()

    async def _run():
        await storage.set_state(key, "LeaveApplicationStates:start_date")
        return await storage.get_state(key)

    result = asyncio.run(_run())
    assert result == "LeaveApplicationStates:start_date"
