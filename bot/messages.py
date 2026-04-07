from __future__ import annotations

import html
from datetime import date, datetime
from typing import Optional

from datetime_utils import format_local_datetime
from services.leave_service import annual_leave_notice_text, leave_label


def format_display_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def format_display_datetime(value: datetime) -> str:
    return format_local_datetime(value, "%d/%m/%Y %H:%M")


def mask_sensitive_value(value: Optional[str], *, visible_suffix: int = 4) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return "-"
    if len(cleaned) <= visible_suffix:
        return cleaned
    return f"{'*' * max(0, len(cleaned) - visible_suffix)}{cleaned[-visible_suffix:]}"


def worker_menu_text() -> str:
    return (
        "<b>Menu Kehadiran</b>\n"
        "Sila gunakan butang menu yang dipaparkan. Anda tidak perlu menaip <code>/menu</code>. Jika butang tidak muncul, taip <code>menu</code> sahaja.\n\n"
        "Pekerja yang berdaftar boleh merekod masuk, merekod keluar, semak status hari ini, melihat cuti sendiri, dan memohon cuti.\n"
        f"{annual_leave_notice_text()}\n"
        "Untuk Cuti Sakit dan Cuti Kecemasan, anda akan diminta muat naik gambar sokongan. Hanya <code>file_id</code> Telegram akan disimpan."
    )


def build_attendance_reminder_text(reminder_type: str, *, pending_names: Optional[list[str]] = None) -> str:
    pending_names = pending_names or []
    if pending_names:
        preview = ", ".join(pending_names[:8])
        extra = ""
        if len(pending_names) > 8:
            extra = f" dan {len(pending_names) - 8} lagi"
        pending_line = f"\nBelum direkod: <b>{len(pending_names)}</b> pekerja\n{preview}{extra}."
    else:
        pending_line = ""

    if reminder_type == "checkin":
        return (
            "<b>Reminder Check-In</b>\n"
            "Selamat bekerja team. Kalau anda bertugas hari ini, jangan lupa tekan <b>Check-In</b>."
            f"{pending_line}"
        )
    if reminder_type == "checkout":
        return (
            "<b>Reminder Check-Out</b>\n"
            "Kalau kerja hari ini sudah selesai, jangan lupa tekan <b>Check-Out</b> sebelum balik."
            f"{pending_line}"
        )
    raise ValueError(f"Unsupported attendance reminder type: {reminder_type}")


def registration_intro_text() -> str:
    return (
        "<b>Pendaftaran Kali Pertama</b>\n"
        "Sebelum menggunakan sistem kehadiran, sila daftar terlebih dahulu.\n\n"
        "Sila hantar <b>NAMA PENUH</b> anda.\n"
        "Jika anda mahu berhenti, tekan <b>Batal</b> atau taip <code>batal</code>."
    )


def admin_menu_text(*, web_login_enabled: bool) -> str:
    web_line = (
        "\nGunakan <b>Buka Admin Web</b> untuk membuka halaman login dashboard di browser."
        if web_login_enabled
        else "\nTetapkan <code>WEB_BASE_URL</code> jika anda mahu pautan dashboard dipaparkan di sini."
    )
    return (
        "<b>Menu Admin</b>\n"
        "Sila gunakan butang menu yang dipaparkan. Anda tidak perlu menaip <code>/admin</code>. Jika butang tidak muncul, taip <code>admin</code> sahaja."
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
        f"Tarikh: {format_display_date(start_date)} hingga {format_display_date(end_date)}\n"
        f"Sebab: {reason}"
    )


def build_leave_review_text(
    leave_id: int,
    leave_type: str,
    start_date: date,
    end_date: date,
    status: str,
    review_notes: Optional[str] = None,
) -> str:
    status_map = {
        "approved": "DILULUSKAN",
        "rejected": "DITOLAK",
        "pending": "DALAM SEMAKAN",
    }
    notes_line = f"\nCatatan: {review_notes}" if review_notes else ""
    return (
        f"Permohonan cuti anda #{leave_id} kini <b>{status_map.get(status, status.upper())}</b>.\n"
        f"Jenis: {leave_label(leave_type)}\n"
        f"Tarikh: {format_display_date(start_date)} hingga {format_display_date(end_date)}"
        f"{notes_line}"
    )


def build_registration_confirmation_text(full_name: str, ic_number: str) -> str:
    return (
        "<b>Sahkan Pendaftaran</b>\n"
        f"Nama Penuh: {full_name}\n"
        f"No. IC: {ic_number}\n\n"
        "Pastikan maklumat betul sebelum anda sahkan."
    )


def build_leave_confirmation_text(
    *,
    worker_name: str,
    leave_type: str,
    start_date: date,
    end_date: date,
    reason: str,
    has_supporting_photo: bool,
) -> str:
    document_line = "Ada" if has_supporting_photo else "Tiada"
    return (
        "<b>Sahkan Permohonan Cuti</b>\n"
        f"Pekerja: {worker_name}\n"
        f"Jenis: {leave_label(leave_type)}\n"
        f"Tarikh: {format_display_date(start_date)} hingga {format_display_date(end_date)}\n"
        f"Sebab: {reason}\n"
        f"Dokumen Sokongan: {document_line}\n\n"
        "Tekan <b>Sahkan</b> untuk menghantar permohonan."
    )


def build_today_status_text(
    *,
    worker_name: str,
    site_name: Optional[str],
    check_in_at: Optional[datetime],
    check_out_at: Optional[datetime],
    approved_leave_label: Optional[str],
    public_holiday_label: Optional[str] = None,
) -> str:
    site_line = site_name or "Belum ditetapkan"
    if approved_leave_label:
        status_line = f"Cuti Diluluskan ({approved_leave_label})"
    elif public_holiday_label and not check_in_at and not check_out_at:
        status_line = f"Cuti Umum ({public_holiday_label})"
    elif check_in_at and check_out_at:
        status_line = "Lengkap"
    elif check_in_at:
        status_line = "Sudah Rekod Masuk"
    else:
        status_line = "Belum Rekod Masuk"
    public_holiday_line = ""
    if public_holiday_label:
        public_holiday_line = f"Cuti Umum: {public_holiday_label}\n"
    return (
        "<b>Status Hari Ini</b>\n"
        f"Nama: {worker_name}\n"
        f"Site: {site_line}\n"
        f"Status: {status_line}\n"
        f"{public_holiday_line}"
        f"Rekod Masuk: {format_display_datetime(check_in_at) if check_in_at else '-'}\n"
        f"Rekod Keluar: {format_display_datetime(check_out_at) if check_out_at else '-'}"
    )


def build_attendance_sync_text(
    *,
    attendance_date: date,
    check_in_at: Optional[datetime],
    check_out_at: Optional[datetime],
    notes: Optional[str],
    action: str,
) -> str:
    action_map = {
        "saved": "dikemaskini",
        "deleted": "dipadam",
    }
    notes_line = ""
    if notes:
        notes_line = f"\nCatatan: {html.escape(notes)}"
    return (
        "<b>Rekod Kehadiran Dikemas Kini</b>\n"
        f"Tarikh: {format_display_date(attendance_date)}\n"
        f"Tindakan: {action_map.get(action, action)} dari dashboard admin web\n"
        f"Rekod Masuk: {format_display_datetime(check_in_at) if check_in_at else '-'}\n"
        f"Rekod Keluar: {format_display_datetime(check_out_at) if check_out_at else '-'}"
        f"{notes_line}"
    )


def build_public_holiday_sync_text(
    *,
    holiday_date: date,
    holiday_name: str,
    site_name: Optional[str],
    notes: Optional[str],
    action: str,
) -> str:
    action_map = {
        "created": "direkodkan",
        "saved": "dikemaskini",
        "deleted": "dipadam",
    }
    scope_line = site_name or "Semua site"
    notes_line = f"\nCatatan: {html.escape(notes)}" if notes else ""
    return (
        "<b>Kemas Kini Cuti Umum</b>\n"
        f"Tarikh: {format_display_date(holiday_date)}\n"
        f"Nama: {html.escape(holiday_name)}\n"
        f"Skop: {html.escape(scope_line)}\n"
        f"Tindakan: {action_map.get(action, action)} dari dashboard admin web"
        f"{notes_line}"
    )


def build_worker_profile_text(
    *,
    worker_name: str,
    site_name: Optional[str],
    employee_code: Optional[str],
    ic_number: Optional[str],
    telegram_user_id: int,
) -> str:
    return (
        "<b>Profil Saya</b>\n"
        f"Nama: {worker_name}\n"
        f"Site: {site_name or 'Belum ditetapkan'}\n"
        f"Kod Pekerja: {employee_code or '-'}\n"
        f"No. IC: {mask_sensitive_value(ic_number)}\n"
        f"Telegram ID: <code>{telegram_user_id}</code>"
    )


def build_worker_leave_history_text(entries: list[dict[str, str]]) -> str:
    if not entries:
        return "<b>Cuti Saya</b>\nBelum ada rekod cuti."
    lines = ["<b>Cuti Saya</b>"]
    for entry in entries:
        lines.append(
            f"#{entry['id']} | {entry['type']} | {entry['date_range']} | <b>{entry['status']}</b>"
        )
    return "\n".join(lines)


def parse_user_date(raw_value: str) -> date:
    cleaned = (raw_value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    raise ValueError("Sila gunakan format tarikh YYYY-MM-DD atau DD/MM/YYYY.")
