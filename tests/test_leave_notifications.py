from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace

from bot.notifications import send_leave_request_to_admins


class DummyBot:
    def __init__(self) -> None:
        self.photos: list[dict[str, object]] = []
        self.messages: list[dict[str, object]] = []

    async def send_photo(self, **kwargs) -> None:
        self.photos.append(kwargs)

    async def send_message(self, **kwargs) -> None:
        self.messages.append(kwargs)


def _make_leave_request(*, leave_type: str, site_group_id: int | None, reason: str = "Clinic visit"):
    return SimpleNamespace(
        id=8,
        leave_type=leave_type,
        day_portion="full",
        start_date=date(2026, 4, 8),
        end_date=date(2026, 4, 8),
        reason=reason,
        telegram_file_id="photo-file-id",
        worker=SimpleNamespace(
            full_name="Worker One",
            site=SimpleNamespace(telegram_group_id=site_group_id),
        ),
    )


def test_send_leave_request_to_admins_also_posts_mc_support_to_site_group(monkeypatch) -> None:
    bot = DummyBot()
    leave_request = _make_leave_request(leave_type="mc", site_group_id=-100222333)

    @asynccontextmanager
    async def _fake_session_scope():
        yield object()

    async def _fake_get_leave_request(*args, **kwargs):
        return leave_request

    monkeypatch.setattr("bot.notifications.get_settings", lambda: SimpleNamespace(admin_ids=(101,), group_id=-100999888))
    monkeypatch.setattr("bot.notifications.session_scope", _fake_session_scope)
    monkeypatch.setattr("bot.notifications.get_leave_request", _fake_get_leave_request)

    asyncio.run(send_leave_request_to_admins(bot, leave_request.id))

    assert len(bot.photos) == 2
    admin_photo = next(item for item in bot.photos if item["chat_id"] == 101)
    group_photo = next(item for item in bot.photos if item["chat_id"] == -100222333)

    assert admin_photo["reply_markup"] is not None
    assert "Makluman Permohonan Cuti" in group_photo["caption"]
    assert "Sebab: Clinic visit" in group_photo["caption"]
    assert "reply_markup" not in group_photo


def test_send_leave_request_to_admins_uses_fallback_group_for_emergency_leave(monkeypatch) -> None:
    bot = DummyBot()
    leave_request = _make_leave_request(leave_type="emergency", site_group_id=None, reason="Family emergency")

    @asynccontextmanager
    async def _fake_session_scope():
        yield object()

    async def _fake_get_leave_request(*args, **kwargs):
        return leave_request

    monkeypatch.setattr("bot.notifications.get_settings", lambda: SimpleNamespace(admin_ids=(101,), group_id=-100444555))
    monkeypatch.setattr("bot.notifications.session_scope", _fake_session_scope)
    monkeypatch.setattr("bot.notifications.get_leave_request", _fake_get_leave_request)

    asyncio.run(send_leave_request_to_admins(bot, leave_request.id))

    assert any(item["chat_id"] == -100444555 for item in bot.photos)
    group_photo = next(item for item in bot.photos if item["chat_id"] == -100444555)
    assert "Family emergency" in group_photo["caption"]
