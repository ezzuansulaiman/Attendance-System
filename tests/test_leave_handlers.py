import asyncio
from types import SimpleNamespace

from bot.leave_handlers import _classify_leave_error_reason, confirm_leave_request, pick_leave_type
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

    async def clear(self) -> None:
        self.current_state = None
        self.data = {}


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

    async def _fake_load_worker_access(_telegram_id: int):
        return SimpleNamespace(
            is_inactive=False,
            worker=SimpleNamespace(is_active=True),
        )

    monkeypatch.setattr("bot.leave_handlers._submit_leave_request", _fake_submit_leave_request)
    monkeypatch.setattr("bot.leave_handlers.load_worker_access", _fake_load_worker_access)
    monkeypatch.setattr("bot.leave_handlers.worker_chat_is_allowed", lambda _worker, _callback: True)

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

    async def _fake_load_worker_access(_telegram_id: int):
        return SimpleNamespace(
            is_inactive=False,
            worker=SimpleNamespace(is_active=True),
        )

    monkeypatch.setattr("bot.leave_handlers.load_worker_access", _fake_load_worker_access)
    monkeypatch.setattr("bot.leave_handlers.worker_chat_is_allowed", lambda _worker, _callback: True)

    asyncio.run(confirm_leave_request(callback, state, dummy_bot))

    assert callback.answer_calls == 1
    # Must NOT use show_alert=True — that creates a blocking popup which is the bug we fixed
    assert callback.answer_kwargs[0].get("show_alert") is not True
    assert callback.answer_kwargs[0]["text"] != ""


def test_pick_leave_type_allows_mc_without_group_mapping(monkeypatch) -> None:
    """pick_leave_type proceeds for MC even when no group is mapped (group_delivery_unavailable=True)."""
    callback = DummyCallback()
    callback.data = "leave:type:mc"
    callback.message.chat = SimpleNamespace(type="supergroup", id=-100123)
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


def test_pick_leave_type_proceeds_without_rechecking_group_when_flow_active(monkeypatch) -> None:
    """When a leave flow is already active (state set by start_leave_flow), pick_leave_type
    must NOT re-run the group restriction check — trusting the FSM state instead."""
    callback = DummyCallback()
    callback.data = "leave:type:annual"
    callback.message.chat = SimpleNamespace(type="supergroup", id=-100999)
    state = DummyState(LeaveApplicationStates.leave_type.state)

    async def _fake_load_worker_access(_telegram_id: int):
        return SimpleNamespace(
            is_inactive=False,
            worker=SimpleNamespace(site=None),
        )

    # Group check would return False — but it must NOT be called when flow is active.
    monkeypatch.setattr("bot.leave_handlers.load_worker_access", _fake_load_worker_access)
    monkeypatch.setattr("bot.leave_handlers.worker_chat_is_allowed", lambda _worker, _event: False)
    monkeypatch.setattr("bot.leave_handlers.worker_group_id", lambda _worker: None)

    asyncio.run(pick_leave_type(callback, state))

    # State advanced despite group check returning False — group check was skipped.
    assert state.current_state == LeaveApplicationStates.start_date.state
    assert state.data["leave_type"] == "annual"


def test_pick_leave_type_stale_or_foreign_state_restarts_flow_if_group_ok(monkeypatch) -> None:
    """When the FSM state is None or a non-leave state (e.g. stuck registration), the handler
    should restart the leave flow if the group check passes — not block with a toast."""
    for stuck_state in (None, "RegistrationStates:full_name", "RegistrationStates:ic_number"):
        callback = DummyCallback()
        callback.data = "leave:type:annual"
        callback.message.chat = SimpleNamespace(type="supergroup", id=-100999)
        state = DummyState(stuck_state)

        async def _fake_load_worker_access(_telegram_id: int):
            return SimpleNamespace(is_inactive=False, worker=SimpleNamespace(site=None))

        monkeypatch.setattr("bot.leave_handlers.load_worker_access", _fake_load_worker_access)
        monkeypatch.setattr("bot.leave_handlers.worker_chat_is_allowed", lambda _w, _e: True)
        monkeypatch.setattr("bot.leave_handlers.worker_group_id", lambda _w: None)

        asyncio.run(pick_leave_type(callback, state))

        assert state.current_state == LeaveApplicationStates.start_date.state, (
            f"Expected start_date state but got {state.current_state!r} for stuck_state={stuck_state!r}"
        )


def test_pick_leave_type_stale_button_in_wrong_group_is_blocked(monkeypatch) -> None:
    """When there is no active leave flow and the group check fails, the handler must block."""
    callback = DummyCallback()
    callback.data = "leave:type:annual"
    callback.message.chat = SimpleNamespace(type="supergroup", id=-100999)
    state = DummyState(None)

    async def _fake_load_worker_access(_telegram_id: int):
        return SimpleNamespace(is_inactive=False, worker=SimpleNamespace(site=None))

    monkeypatch.setattr("bot.leave_handlers.load_worker_access", _fake_load_worker_access)
    monkeypatch.setattr("bot.leave_handlers.worker_chat_is_allowed", lambda _w, _e: False)

    asyncio.run(pick_leave_type(callback, state))

    assert state.current_state is None
    assert callback.answer_kwargs[0].get("show_alert") is True


def test_classify_leave_error_reason_uses_expected_codes() -> None:
    assert _classify_leave_error_reason("Sudah ada permohonan cuti yang bertindih.") == "overlap_existing_leave"
    assert _classify_leave_error_reason("Gambar sokongan Telegram diperlukan.") == "missing_supporting_photo"
    assert _classify_leave_error_reason("Permohonan perlu dibuat sekurang-kurangnya 3 hari.") == "annual_notice_failed"
