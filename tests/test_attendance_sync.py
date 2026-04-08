import asyncio
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from bot.messages import build_attendance_sync_text, build_public_holiday_sync_text, build_today_status_text
from web.attendance_routes import _attendance_sync_payload, _notify_worker_about_attendance_change


LOCAL_TZ = ZoneInfo("Asia/Kuala_Lumpur")


def test_build_attendance_sync_text_includes_admin_web_context() -> None:
    text = build_attendance_sync_text(
        attendance_date=date(2026, 4, 7),
        check_in_at=datetime(2026, 4, 7, 8, 0),
        check_out_at=datetime(2026, 4, 7, 17, 0),
        notes="Adjusted after site supervisor review",
        action="saved",
    )

    assert "dashboard admin web" in text
    assert "07/04/2026" in text
    assert "Adjusted after site supervisor review" in text


def test_build_attendance_sync_text_formats_aware_datetimes_in_malaysia_time() -> None:
    text = build_attendance_sync_text(
        attendance_date=date(2026, 4, 7),
        check_in_at=datetime(2026, 4, 7, 0, 0, tzinfo=ZoneInfo("UTC")),
        check_out_at=datetime(2026, 4, 7, 9, 0, tzinfo=LOCAL_TZ),
        notes=None,
        action="saved",
    )

    assert "Rekod Masuk: 07/04/2026 08:00" in text
    assert "Rekod Keluar: 07/04/2026 09:00" in text


def test_attendance_sync_payload_ignores_non_telegram_records() -> None:
    record = SimpleNamespace(
        source_chat_id=None,
        worker=SimpleNamespace(telegram_user_id=123456),
        attendance_date=date(2026, 4, 7),
        check_in_at=None,
        check_out_at=None,
        notes=None,
    )

    assert _attendance_sync_payload(record) is None


def test_build_public_holiday_sync_text_includes_scope_and_action() -> None:
    text = build_public_holiday_sync_text(
        holiday_date=date(2026, 5, 1),
        holiday_name="Labour Day",
        site_name="Sepang",
        notes=None,
        action="created",
    )

    assert "Labour Day" in text
    assert "Sepang" in text
    assert "direkodkan" in text


def test_build_today_status_text_surfaces_public_holiday() -> None:
    text = build_today_status_text(
        worker_name="Worker One",
        site_name="Sepang",
        check_in_at=None,
        check_out_at=None,
        approved_leave_label=None,
        public_holiday_label="Labour Day",
    )

    assert "Cuti Umum (Labour Day)" in text
    assert "Cuti Umum: Labour Day" in text


def test_build_today_status_text_surfaces_half_day_leave_with_attendance() -> None:
    text = build_today_status_text(
        worker_name="Worker One",
        site_name="Sepang",
        check_in_at=datetime(2026, 4, 7, 8, 0, tzinfo=LOCAL_TZ),
        check_out_at=None,
        approved_leave_label="Cuti Tahunan (Separuh Hari (Petang))",
        approved_leave_is_partial=True,
        public_holiday_label=None,
    )

    assert "Kehadiran + Cuti Separuh Hari" in text
    assert "Rekod Masuk: 07/04/2026 08:00" in text


def test_notify_worker_about_attendance_change_only_for_telegram_originated_records(monkeypatch) -> None:
    sent_payloads: list[dict[str, object]] = []

    async def _fake_sender(**payload: object) -> bool:
        sent_payloads.append(payload)
        return True

    monkeypatch.setattr("web.attendance_routes.send_attendance_sync_to_worker_via_configured_bot", _fake_sender)

    telegram_record = SimpleNamespace(
        source_chat_id=-100998877,
        worker=SimpleNamespace(telegram_user_id=123456),
        attendance_date=date(2026, 4, 7),
        check_in_at=datetime(2026, 4, 7, 8, 0),
        check_out_at=datetime(2026, 4, 7, 17, 0),
        notes="Updated from web",
    )
    manual_record = SimpleNamespace(
        source_chat_id=None,
        worker=SimpleNamespace(telegram_user_id=123456),
        attendance_date=date(2026, 4, 7),
        check_in_at=None,
        check_out_at=None,
        notes=None,
    )

    assert asyncio.run(_notify_worker_about_attendance_change(telegram_record, action="saved")) is True
    assert asyncio.run(_notify_worker_about_attendance_change(manual_record, action="saved")) is False

    assert sent_payloads == [
        {
            "worker_telegram_id": 123456,
            "attendance_date": date(2026, 4, 7),
            "check_in_at": datetime(2026, 4, 7, 8, 0),
            "check_out_at": datetime(2026, 4, 7, 17, 0),
            "notes": "Updated from web",
            "action": "saved",
        }
    ]
