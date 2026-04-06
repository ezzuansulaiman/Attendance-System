from datetime import datetime, time
from zoneinfo import ZoneInfo

from bot.reminders import (
    ReminderSlot,
    due_reminder_targets,
    extract_reminder_chat_ids,
    reminder_token,
)
from models.models import Site


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
