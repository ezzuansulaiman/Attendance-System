import asyncio
from types import SimpleNamespace

from bot.leave_handlers import confirm_leave_request, pick_leave_type
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
        self.data: dict[str, object] = {}

    async def get_state(self) -> str:
        return self.current_state

    async def set_state(self, new_state: str) -> None:
        self.current_state = new_state

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)


def test_confirm_leave_request_uses_callback_user_id_for_submission(monkeypatch) -> None:
    callback = DummyCallback()
    state = DummyState(LeaveApplicationStates.confirmation.state)
    captured: dict[str, object] = {}

    dummy_bot = object()

    async def _fake_submit_leave_request(message, fsm_state, bot, *, telegram_user_id: int) -> None:
        captured["message"] = message
        captured["state"] = fsm_state
        captured["bot"] = bot
        captured["telegram_user_id"] = telegram_user_id

    monkeypatch.setattr("bot.leave_handlers._submit_leave_request", _fake_submit_leave_request)

    asyncio.run(confirm_leave_request(callback, state, dummy_bot))

    assert callback.answer_calls == 1
    assert callback.answer_kwargs[0]["text"] == ""
    assert captured["message"] is callback.message
    assert captured["state"] is state
    assert captured["bot"] is dummy_bot
    assert captured["telegram_user_id"] == callback.from_user.id


def test_confirm_leave_request_shows_soft_toast_when_no_active_flow(monkeypatch) -> None:
    """When state is not the confirmation step, a soft toast (no blocking popup) is shown."""
    callback = DummyCallback()
    state = DummyState("some:other:state")
    dummy_bot = object()

    asyncio.run(confirm_leave_request(callback, state, dummy_bot))

    assert callback.answer_calls == 1
    # Must NOT use show_alert=True — that creates a blocking popup which is the bug we fixed
    assert callback.answer_kwargs[0].get("show_alert") is not True
    assert callback.answer_kwargs[0]["text"] != ""


def test_pick_leave_type_allows_mc_without_group_mapping(monkeypatch) -> None:
    callback = DummyCallback()
    callback.data = "leave:type:mc"
    callback.message.chat = SimpleNamespace(type="private")
    state = DummyState(LeaveApplicationStates.leave_type.state)

    async def _fake_load_worker_access(_telegram_id: int):
        return SimpleNamespace(
            is_inactive=False,
            worker=SimpleNamespace(site=SimpleNamespace(telegram_group_id=None)),
        )

    monkeypatch.setattr("bot.leave_handlers.load_worker_access", _fake_load_worker_access)
    monkeypatch.setattr("bot.leave_handlers.worker_group_id", lambda _worker: None)

    asyncio.run(pick_leave_type(callback, state))

    assert state.current_state == LeaveApplicationStates.start_date.state
    assert state.data["leave_type"] == "mc"
    assert state.data["group_delivery_unavailable"] is True
    assert any("boleh dihantar" in text for text in callback.message.answers)
