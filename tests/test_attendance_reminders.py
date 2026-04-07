from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from bot.reminders import (
    ReminderSlot,
    due_reminder_targets,
    extract_reminder_chat_ids,
    pending_worker_names,
    reminder_token,
    select_workers_for_chat,
)
from models.models import AttendanceRecord, Site, Worker


LOCAL_TZ = ZoneInfo("Asia/Kuala_Lumpur")


def test_due_reminder_targets_only_fire_once_per_chat_and_slot() -> None:
    now = datetime(2026, 4, 6, 8, 5, tzinfo=LOCAL_TZ)
    slots = (
        ReminderSlot(key="checkin", trigger_time=time(8, 0)),
        ReminderSlot(key="checkout", trigger_time=time(17, 0)),
    )
    sent_tokens: set[str] = set()

    due = due_reminder_targets(
        now=now,
        slots=slots,
        workdays=(0, 1, 2, 3, 4),
        chat_ids=(-1001, -1002),
        sent_tokens=sent_tokens,
    )

    assert [(slot.key, chat_id) for slot, chat_id in due] == [
        ("checkin", -1001),
        ("checkin", -1002),
    ]

    sent_tokens.update(
        reminder_token(target_date=now.date(), slot_key=slot.key, chat_id=chat_id) for slot, chat_id in due
    )
    second_due = due_reminder_targets(
        now=now,
        slots=slots,
        workdays=(0, 1, 2, 3, 4),
        chat_ids=(-1001, -1002),
        sent_tokens=sent_tokens,
    )

    assert second_due == []


def test_due_reminder_targets_skip_non_workdays() -> None:
    saturday = datetime(2026, 4, 11, 8, 5, tzinfo=LOCAL_TZ)
    slots = (ReminderSlot(key="checkin", trigger_time=time(8, 0)),)

    due = due_reminder_targets(
        now=saturday,
        slots=slots,
        workdays=(0, 1, 2, 3, 4),
        chat_ids=(-1001,),
        sent_tokens=set(),
    )

    assert due == []


def test_extract_reminder_chat_ids_uses_site_groups_and_global_fallback() -> None:
    sites = [
        Site(id=1, name="Alpha", code="ALPHA", telegram_group_id=-10010, is_active=True),
        Site(id=2, name="Beta", code="BETA", telegram_group_id=None, is_active=True),
        Site(id=3, name="Gamma", code="GAMMA", telegram_group_id=-10010, is_active=True),
        Site(id=4, name="Old", code="OLD", telegram_group_id=-10099, is_active=False),
    ]

    chat_ids = extract_reminder_chat_ids(sites, fallback_group_id=-10077)

    assert chat_ids == (-10077, -10010)


def test_select_workers_for_chat_routes_site_groups_and_fallback_group() -> None:
    alpha = Site(id=1, name="Alpha", code="ALPHA", telegram_group_id=-10010, is_active=True)
    beta = Site(id=2, name="Beta", code="BETA", telegram_group_id=None, is_active=True)
    workers = [
        Worker(id=1, telegram_user_id=101, full_name="Ali", site=alpha, site_id=1, is_active=True),
        Worker(id=2, telegram_user_id=102, full_name="Bala", site=beta, site_id=2, is_active=True),
        Worker(id=3, telegram_user_id=103, full_name="Chen", site=None, site_id=None, is_active=True),
    ]

    alpha_workers = select_workers_for_chat(workers, chat_id=-10010, fallback_group_id=-10077)
    fallback_workers = select_workers_for_chat(workers, chat_id=-10077, fallback_group_id=-10077)

    assert [worker.full_name for worker in alpha_workers] == ["Ali"]
    assert [worker.full_name for worker in fallback_workers] == ["Bala", "Chen"]


def test_pending_worker_names_skip_approved_leave_and_completed_checkout() -> None:
    workers = [
        Worker(id=1, telegram_user_id=101, full_name="Ali", is_active=True),
        Worker(id=2, telegram_user_id=102, full_name="Bala", is_active=True),
        Worker(id=3, telegram_user_id=103, full_name="Chen", is_active=True),
    ]
    attendance_lookup = {
        1: AttendanceRecord(worker_id=1, attendance_date=date(2026, 4, 7)),
        2: AttendanceRecord(
            worker_id=2,
            attendance_date=date(2026, 4, 7),
            check_in_at=datetime(2026, 4, 7, 8, 0, tzinfo=LOCAL_TZ),
        ),
        3: AttendanceRecord(
            worker_id=3,
            attendance_date=date(2026, 4, 7),
            check_in_at=datetime(2026, 4, 7, 8, 0, tzinfo=LOCAL_TZ),
            check_out_at=datetime(2026, 4, 7, 17, 0, tzinfo=LOCAL_TZ),
        ),
    }

    checkin_pending = pending_worker_names(
        reminder_type="checkin",
        workers=workers,
        attendance_lookup=attendance_lookup,
        approved_leave_worker_ids={1},
    )
    checkout_pending = pending_worker_names(
        reminder_type="checkout",
        workers=workers,
        attendance_lookup=attendance_lookup,
        approved_leave_worker_ids=set(),
    )

    assert checkin_pending == []
    assert checkout_pending == ["Bala"]
