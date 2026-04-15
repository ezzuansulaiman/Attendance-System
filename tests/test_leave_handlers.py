import asyncio
from types import SimpleNamespace

from bot.leave_handlers import confirm_leave_request
from bot.states import LeaveApplicationStates


class DummyMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=999999)
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answers.append(text)


class DummyCallback:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=123456)
        self.message = DummyMessage()
        self.answer_calls = 0
        self.answer_kwargs: list[dict] = []

    async def answer(self, text: str = "", **kwargs) -> None:
        self.answer_calls += 1
        self.answer_kwargs.append({"text": text, **kwargs})


class DummyState:
    def __init__(self, current_state: str) -> None:
        self.current_state = current_state

    async def get_state(self) -> str:
        return self.current_state


def test_confirm_leave_request_uses_callback_user_id_for_submission(monkeypatch) -> None:
    callback = DummyCallback()
    state = DummyState(LeaveApplicationStates.confirmation.state)
    captured: dict[str, object] = {}

    async def _fake_submit_leave_request(message, fsm_state, *, telegram_user_id: int) -> None:
        captured["message"] = message
        captured["state"] = fsm_state
        captured["telegram_user_id"] = telegram_user_id

    monkeypatch.setattr("bot.leave_handlers._submit_leave_request", _fake_submit_leave_request)

    asyncio.run(confirm_leave_request(callback, state))

    assert callback.answer_calls == 1
    assert callback.answer_kwargs[0]["text"] == ""
    assert captured["message"] is callback.message
    assert captured["state"] is state
    assert captured["telegram_user_id"] == callback.from_user.id


def test_confirm_leave_request_shows_alert_when_state_mismatch(monkeypatch) -> None:
    callback = DummyCallback()
    state = DummyState("some:other:state")

    asyncio.run(confirm_leave_request(callback, state))

    assert callback.answer_calls == 1
    assert callback.answer_kwargs[0]["show_alert"] is True
    assert "tidak aktif" in callback.answer_kwargs[0]["text"]
