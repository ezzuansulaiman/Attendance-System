import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace

from bot.admin_handlers import (
    PDF_EXPORT_FAILURE_MESSAGE,
    choose_custom_report_month,
    choose_custom_report_site,
    run_custom_report,
    send_current_month_report,
    send_current_month_summary,
    send_previous_month_report,
    send_today_summary,
    start_custom_report_flow,
)
from services.pdf_generator import PdfExportError


class DummyMessage:
    def __init__(self) -> None:
        self.answers: list[str] = []
        self.answer_payloads: list[dict[str, object]] = []
        self.documents: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answers.append(text)
        self.answer_payloads.append({"text": text, **kwargs})

    async def answer_document(self, *args, **kwargs) -> None:
        self.documents.append((args, kwargs))


class DummyCallback:
    def __init__(self, data: str = "") -> None:
        self.from_user = SimpleNamespace(id=123456)
        self.message = DummyMessage()
        self.answer_calls = 0
        self.data = data

    async def answer(self) -> None:
        self.answer_calls += 1


def test_send_current_month_report_notifies_admin_when_pdf_generation_fails(monkeypatch) -> None:
    callback = DummyCallback()

    @asynccontextmanager
    async def _fake_session_scope():
        yield object()

    async def _fake_generate_monthly_attendance_pdf(*args, **kwargs):
        raise PdfExportError("boom")

    monkeypatch.setattr("bot.admin_handlers.is_admin", lambda user_id: True)
    monkeypatch.setattr("bot.admin_handlers.session_scope", _fake_session_scope)
    monkeypatch.setattr("bot.admin_handlers.generate_monthly_attendance_pdf", _fake_generate_monthly_attendance_pdf)

    asyncio.run(send_current_month_report(callback))

    assert callback.answer_calls == 1
    assert callback.message.answers == [PDF_EXPORT_FAILURE_MESSAGE]
    assert callback.message.documents == []


def test_send_previous_month_report_rolls_back_to_previous_year_in_january(monkeypatch) -> None:
    callback = DummyCallback()
    captured: dict[str, int] = {}

    @asynccontextmanager
    async def _fake_session_scope():
        yield object()

    class _FakeDateTime:
        @classmethod
        def now(cls, tz):
            return datetime(2026, 1, 15, 9, 30)

    async def _fake_generate_monthly_attendance_pdf(*args, **kwargs):
        captured["year"] = kwargs["year"]
        captured["month"] = kwargs["month"]
        return b"%PDF-1.7"

    monkeypatch.setattr("bot.admin_handlers.is_admin", lambda user_id: True)
    monkeypatch.setattr("bot.admin_handlers.session_scope", _fake_session_scope)
    monkeypatch.setattr("bot.admin_handlers.datetime", _FakeDateTime)
    monkeypatch.setattr("bot.admin_handlers.generate_monthly_attendance_pdf", _fake_generate_monthly_attendance_pdf)

    asyncio.run(send_previous_month_report(callback))

    assert callback.answer_calls == 1
    assert captured == {"year": 2025, "month": 12}
    assert len(callback.message.documents) == 1


def test_send_today_summary_sends_telegram_friendly_counts(monkeypatch) -> None:
    callback = DummyCallback()

    @asynccontextmanager
    async def _fake_session_scope():
        yield object()

    class _FakeDateTime:
        @classmethod
        def now(cls, tz):
            return datetime(2026, 4, 8, 8, 45)

    async def _fake_get_dashboard_summary(*args, **kwargs):
        return {
            "total_workers": 10,
            "checked_in": 8,
            "checked_out": 6,
            "pending_leaves": 2,
        }

    monkeypatch.setattr("bot.admin_handlers.is_admin", lambda user_id: True)
    monkeypatch.setattr("bot.admin_handlers.session_scope", _fake_session_scope)
    monkeypatch.setattr("bot.admin_handlers.datetime", _FakeDateTime)
    monkeypatch.setattr("bot.admin_handlers.get_dashboard_summary", _fake_get_dashboard_summary)

    asyncio.run(send_today_summary(callback))

    assert callback.answer_calls == 1
    assert len(callback.message.answers) == 1
    assert "Ringkasan Hari Ini" in callback.message.answers[0]
    assert "Belum rekod masuk: 2" in callback.message.answers[0]
    assert "Belum rekod keluar: 2" in callback.message.answers[0]


def test_send_current_month_summary_uses_report_summary_values(monkeypatch) -> None:
    callback = DummyCallback()

    @asynccontextmanager
    async def _fake_session_scope():
        yield object()

    class _FakeDateTime:
        @classmethod
        def now(cls, tz):
            return datetime(2026, 4, 8, 8, 45)

    async def _fake_build_monthly_attendance_report(*args, **kwargs):
        assert kwargs["year"] == 2026
        assert kwargs["month"] == 4
        return {
            "period_label": "April 2026",
            "site_name": "Sepang Region",
            "summary": {
                "total_workers": 12,
                "total_present_days": 140,
                "total_completed_days": 133,
                "average_present_days": 11.7,
                "completion_rate": 95.0,
            },
        }

    monkeypatch.setattr("bot.admin_handlers.is_admin", lambda user_id: True)
    monkeypatch.setattr("bot.admin_handlers.session_scope", _fake_session_scope)
    monkeypatch.setattr("bot.admin_handlers.datetime", _FakeDateTime)
    monkeypatch.setattr("bot.admin_handlers.build_monthly_attendance_report", _fake_build_monthly_attendance_report)

    asyncio.run(send_current_month_summary(callback))

    assert callback.answer_calls == 1
    assert len(callback.message.answers) == 1
    assert "Ringkasan Laporan Bulanan" in callback.message.answers[0]
    assert "Tempoh: April 2026" in callback.message.answers[0]
    assert "Kadar lengkap: 95%" in callback.message.answers[0]


def test_start_custom_report_flow_lists_active_sites(monkeypatch) -> None:
    callback = DummyCallback("admin:report:custom")

    @asynccontextmanager
    async def _fake_session_scope():
        yield object()

    async def _fake_list_sites(*args, **kwargs):
        return [
            SimpleNamespace(id=1, name="Sepang", code="SEP", is_active=True),
            SimpleNamespace(id=2, name="Klang", code=None, is_active=True),
        ]

    monkeypatch.setattr("bot.admin_handlers.is_admin", lambda user_id: True)
    monkeypatch.setattr("bot.admin_handlers.session_scope", _fake_session_scope)
    monkeypatch.setattr("bot.admin_handlers.list_sites", _fake_list_sites)

    asyncio.run(start_custom_report_flow(callback))

    assert callback.answer_calls == 1
    assert "Laporan Ikut Site/Bulan" in callback.message.answers[0]
    reply_markup = callback.message.answer_payloads[0]["reply_markup"]
    button_text = [button.text for row in reply_markup.inline_keyboard for button in row]
    assert "SEP - Sepang" in button_text
    assert "Klang" in button_text
    assert "Menu Admin" in button_text


def test_choose_custom_report_site_shows_month_picker(monkeypatch) -> None:
    callback = DummyCallback("admin:report:custom:site:7")

    @asynccontextmanager
    async def _fake_session_scope():
        yield object()

    async def _fake_get_site_by_id(*args, **kwargs):
        return SimpleNamespace(id=7, name="Sepang", code="SEP", is_active=True)

    class _FakeDateTime:
        @classmethod
        def now(cls, tz):
            return datetime(2026, 4, 8, 8, 45)

    monkeypatch.setattr("bot.admin_handlers.is_admin", lambda user_id: True)
    monkeypatch.setattr("bot.admin_handlers.session_scope", _fake_session_scope)
    monkeypatch.setattr("bot.admin_handlers.get_site_by_id", _fake_get_site_by_id)
    monkeypatch.setattr("bot.admin_handlers.datetime", _FakeDateTime)

    asyncio.run(choose_custom_report_site(callback))

    assert callback.answer_calls == 1
    assert "Pilih Bulan Laporan" in callback.message.answers[0]
    assert "Site: Sepang" in callback.message.answers[0]
    reply_markup = callback.message.answer_payloads[0]["reply_markup"]
    button_text = [button.text for row in reply_markup.inline_keyboard for button in row]
    assert "Jan" in button_text
    assert "Dec" in button_text
    assert "Tukar Site" in button_text


def test_choose_custom_report_month_shows_format_options(monkeypatch) -> None:
    callback = DummyCallback("admin:report:custom:month:7:2026:4")

    @asynccontextmanager
    async def _fake_session_scope():
        yield object()

    async def _fake_get_site_by_id(*args, **kwargs):
        return SimpleNamespace(id=7, name="Sepang", code="SEP", is_active=True)

    monkeypatch.setattr("bot.admin_handlers.is_admin", lambda user_id: True)
    monkeypatch.setattr("bot.admin_handlers.session_scope", _fake_session_scope)
    monkeypatch.setattr("bot.admin_handlers.get_site_by_id", _fake_get_site_by_id)

    asyncio.run(choose_custom_report_month(callback))

    assert callback.answer_calls == 1
    assert "Pilih Format Laporan" in callback.message.answers[0]
    assert "Tempoh: April 2026" in callback.message.answers[0]
    reply_markup = callback.message.answer_payloads[0]["reply_markup"]
    button_text = [button.text for row in reply_markup.inline_keyboard for button in row]
    assert "Ringkasan Telegram" in button_text
    assert "PDF" in button_text
    assert "Excel" in button_text


def test_run_custom_report_summary_uses_selected_site_and_period(monkeypatch) -> None:
    callback = DummyCallback("admin:report:custom:run:7:2026:4:summary")

    @asynccontextmanager
    async def _fake_session_scope():
        yield object()

    async def _fake_get_site_by_id(*args, **kwargs):
        return SimpleNamespace(id=7, name="Sepang", code="SEP", is_active=True)

    async def _fake_build_monthly_attendance_report(*args, **kwargs):
        assert kwargs["site_id"] == 7
        assert kwargs["year"] == 2026
        assert kwargs["month"] == 4
        return {
            "period_label": "April 2026",
            "site_name": "Sepang",
            "summary": {
                "total_workers": 9,
                "total_present_days": 100,
                "total_completed_days": 97,
                "average_present_days": 11.1,
                "completion_rate": 97.0,
            },
        }

    monkeypatch.setattr("bot.admin_handlers.is_admin", lambda user_id: True)
    monkeypatch.setattr("bot.admin_handlers.session_scope", _fake_session_scope)
    monkeypatch.setattr("bot.admin_handlers.get_site_by_id", _fake_get_site_by_id)
    monkeypatch.setattr("bot.admin_handlers.build_monthly_attendance_report", _fake_build_monthly_attendance_report)

    asyncio.run(run_custom_report(callback))

    assert callback.answer_calls == 1
    assert "Skop: Sepang" in callback.message.answers[0]
    assert "Kadar lengkap: 97%" in callback.message.answers[0]
