from __future__ import annotations

from datetime import date, datetime

from services.leave_service import annual_leave_notice_text, leave_label


def worker_menu_text() -> str:
    return (
        "<b>Attendance Menu</b>\n"
        "Use the buttons below inside the worker group.\n\n"
        "Registered workers can check in, check out, and apply leave.\n"
        f"{annual_leave_notice_text()}\n"
        "MC and Emergency Leave will ask for a photo, and only the Telegram <code>file_id</code> is stored."
    )


def registration_intro_text() -> str:
    return (
        "<b>First-Time Registration</b>\n"
        "Before using attendance, please register first.\n\n"
        "Send your <b>NAME</b>."
    )


def admin_menu_text() -> str:
    return (
        "<b>Admin Menu</b>\n"
        "Use the buttons below to review pending leave requests or generate the current monthly PDF report."
    )


def build_leave_summary_text(
    leave_id: int,
    worker_name: str,
    leave_type: str,
    start_date: date,
    end_date: date,
    reason: str,
) -> str:
    return (
        f"<b>Leave Request #{leave_id}</b>\n"
        f"Worker: {worker_name}\n"
        f"Type: {leave_label(leave_type)}\n"
        f"Dates: {start_date.isoformat()} to {end_date.isoformat()}\n"
        f"Reason: {reason}"
    )


def build_leave_review_text(
    leave_id: int,
    leave_type: str,
    start_date: date,
    end_date: date,
    status: str,
) -> str:
    return (
        f"Your leave request #{leave_id} is now <b>{status.upper()}</b>.\n"
        f"Type: {leave_label(leave_type)}\n"
        f"Dates: {start_date.isoformat()} to {end_date.isoformat()}"
    )


def parse_user_date(raw_value: str) -> date:
    cleaned = (raw_value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    raise ValueError("Please use YYYY-MM-DD or DD/MM/YYYY.")
