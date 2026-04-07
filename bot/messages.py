from __future__ import annotations

from datetime import date, datetime

from services.leave_service import annual_leave_notice_text, leave_label


def worker_menu_text() -> str:
    return (
        "<b>Menu Kehadiran</b>\n"
        "Sila gunakan butang di bawah dalam kumpulan pekerja atau chat peribadi.\n\n"
        "Pekerja yang berdaftar boleh merekod masuk, merekod keluar, dan memohon cuti.\n"
        f"{annual_leave_notice_text()}\n"
        "Untuk Cuti Sakit dan Cuti Kecemasan, anda akan diminta muat naik gambar sokongan. Hanya <code>file_id</code> Telegram akan disimpan."
    )


def build_attendance_reminder_text(reminder_type: str) -> str:
    if reminder_type == "checkin":
        return (
            "<b>Reminder Check-In</b>\n"
            "Selamat bekerja team. Kalau anda bertugas hari ini, jangan lupa tekan <b>Check-In</b>."
        )
    if reminder_type == "checkout":
        return (
            "<b>Reminder Check-Out</b>\n"
            "Kalau kerja hari ini sudah selesai, jangan lupa tekan <b>Check-Out</b> sebelum balik."
        )
    raise ValueError(f"Unsupported attendance reminder type: {reminder_type}")


def registration_intro_text() -> str:
    return (
        "<b>Pendaftaran Kali Pertama</b>\n"
        "Sebelum menggunakan sistem kehadiran, sila daftar terlebih dahulu.\n\n"
        "Sila hantar <b>NAMA PENUH</b> anda."
    )


def admin_menu_text(*, web_login_enabled: bool) -> str:
    web_line = (
        "\nUse <b>Open Admin Web</b> to open the dashboard login page in your browser."
        if web_login_enabled
        else "\nSet <code>WEB_BASE_URL</code> to show a direct dashboard link here."
    )
    return (
        "<b>Admin Menu</b>\n"
        "Use the buttons below to review pending leave requests or generate the current monthly PDF report."
        f"{web_line}"
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
        f"<b>Permohonan Cuti #{leave_id}</b>\n"
        f"Pekerja: {worker_name}\n"
        f"Jenis: {leave_label(leave_type)}\n"
        f"Tarikh: {start_date.isoformat()} hingga {end_date.isoformat()}\n"
        f"Sebab: {reason}"
    )


def build_leave_review_text(
    leave_id: int,
    leave_type: str,
    start_date: date,
    end_date: date,
    status: str,
) -> str:
    status_map = {
        "approved": "DILULUSKAN",
        "rejected": "DITOLAK",
        "pending": "DALAM SEMAKAN",
    }
    return (
        f"Permohonan cuti anda #{leave_id} kini <b>{status_map.get(status, status.upper())}</b>.\n"
        f"Jenis: {leave_label(leave_type)}\n"
        f"Tarikh: {start_date.isoformat()} hingga {end_date.isoformat()}"
    )


def parse_user_date(raw_value: str) -> date:
    cleaned = (raw_value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    raise ValueError("Sila gunakan format tarikh YYYY-MM-DD atau DD/MM/YYYY.")
