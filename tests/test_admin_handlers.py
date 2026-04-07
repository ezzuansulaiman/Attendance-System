import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from bot.admin_handlers import PDF_EXPORT_FAILURE_MESSAGE, send_current_month_report
from services.pdf_generator import PdfExportError


class DummyMessage:
    def __init__(self) -> None:
        self.answers: list[str] = []
        self.documents: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answers.append(text)

    async def answer_document(self, *args, **kwargs) -> None:
        self.documents.append((args, kwargs))


class DummyCallback:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=123456)
        self.message = DummyMessage()
        self.answer_calls = 0

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
