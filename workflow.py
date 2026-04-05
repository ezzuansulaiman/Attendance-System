"""Shared workflow rules for attendance check-in and leave applications."""

import os
from datetime import date, datetime, timedelta

from supporting_docs import leave_type_requires_supporting_doc

ANNUAL_LEAVE_NOTICE_DAYS = int(os.getenv("ANNUAL_LEAVE_NOTICE_DAYS", "5"))
LATE_CUTOFF_TIME = os.getenv("LATE_CUTOFF_TIME", "08:00")
SAME_DAY_ABSENCE_LEAVE_TYPES = {"MC", "EML"}


def _parse_clock(value):
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise ValueError(
            f"Masa '{value}' tidak sah. Guna format HH:MM, contoh 08:00."
        ) from exc


def validate_leave_request(
    leave_type,
    start_date,
    submitted_on=None,
    supporting_doc_present=False,
):
    submitted_on = submitted_on or date.today()

    if leave_type_requires_supporting_doc(leave_type) and not supporting_doc_present:
        raise ValueError(
            "MC dan Cuti Kecemasan mesti disertakan dengan gambar bukti sokongan."
        )

    if leave_type == "AL":
        min_start = submitted_on + timedelta(days=ANNUAL_LEAVE_NOTICE_DAYS)
        if start_date < min_start:
            raise ValueError(
                "Cuti Tahunan (AL) mesti dipohon sekurang-kurangnya "
                f"{ANNUAL_LEAVE_NOTICE_DAYS} hari lebih awal."
            )

    if start_date <= submitted_on and leave_type not in SAME_DAY_ABSENCE_LEAVE_TYPES:
        raise ValueError(
            "Untuk ketidakhadiran segera atau hari yang sama, sila guna MC "
            "atau Cuti Kecemasan."
        )


def build_checkin_note(checkin_at=None):
    checkin_at = checkin_at or datetime.now()
    cutoff = _parse_clock(LATE_CUTOFF_TIME)
    checkin_time = checkin_at.strftime("%H:%M")
    is_late = checkin_at.time() > cutoff
    return {
        "checkin_time": checkin_time,
        "cutoff_time": LATE_CUTOFF_TIME,
        "is_late": is_late,
        "timing_label": "Lewat" if is_late else "Tepat Masa",
        "note": (
            f"checkin={checkin_time};"
            f"cutoff={LATE_CUTOFF_TIME};"
            f"lateness={'late' if is_late else 'on_time'}"
        ),
    }


def build_checkout_note(existing_notes, checkout_at=None):
    checkout_at = checkout_at or datetime.now()
    checkout_time = checkout_at.strftime("%H:%M")
    parsed = _parse_checkin_parts(existing_notes)
    if "checkin" not in parsed:
        raise ValueError(
            "Rekod check-in hari ini tidak ditemui. Sila daftar hadir dahulu."
        )
    parsed["checkout"] = checkout_time
    return {
        "checkin_time": parsed["checkin"],
        "checkout_time": checkout_time,
        "cutoff_time": parsed.get("cutoff", LATE_CUTOFF_TIME),
        "is_late": parsed.get("lateness") == "late",
        "timing_label": "Lewat" if parsed.get("lateness") == "late" else "Tepat Masa",
        "note": _serialize_checkin_parts(parsed),
    }


def _parse_checkin_parts(notes):
    if not notes or "checkin=" not in notes:
        return {}

    parsed = {}
    for part in notes.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _serialize_checkin_parts(parts):
    ordered_keys = ["checkin", "cutoff", "lateness", "checkout"]
    serialized = []
    for key in ordered_keys:
        value = parts.get(key)
        if value:
            serialized.append(f"{key}={value}")
    for key, value in parts.items():
        if key in ordered_keys or not value:
            continue
        serialized.append(f"{key}={value}")
    return ";".join(serialized)


def parse_checkin_note(notes):
    parsed = _parse_checkin_parts(notes)
    if "checkin" not in parsed:
        return None

    is_late = parsed.get("lateness") == "late"
    return {
        "checkin_time": parsed["checkin"],
        "checkout_time": parsed.get("checkout"),
        "cutoff_time": parsed.get("cutoff", LATE_CUTOFF_TIME),
        "is_late": is_late,
        "timing_label": "Lewat" if is_late else "Tepat Masa",
    }
