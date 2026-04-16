from __future__ import annotations

import html
from datetime import date, datetime
from typing import Optional

from datetime_utils import format_local_datetime
from services.leave_service import annual_leave_notice_text, leave_duration_days, leave_label


def format_display_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def format_display_datetime(value: datetime) -> str:
    return format_local_datetime(value, "%d/%m/%Y %H:%M")


def format_leave_duration(*, start_date: date, end_date: date, day_portion: Optional[str]) -> str:
    duration_days = leave_duration_days(start_date=start_date, end_date=end_date, day_portion=day_portion)
    if float(duration_days).is_integer():
        return f"{int(duration_days)} hari"
    return f"{duration_days:.1f} hari"


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
        "Untuk Cuti Sakit dan Cuti Kecemasan, anda akan diminta muat naik gambar sokongan. Bukti sokongan dan alasan akan dihantar ke group site untuk makluman."
    )


def build_bot_guide_text() -> str:
    return (
        "<b>PANDUAN PENGGUNAAN BOT KEHADIRAN</b>\n\n"
        "<b>KEHADIRAN HARIAN</b>\n"
        "Tekan butang <b>Menu Kehadiran</b> (atau taip <code>menu</code>) untuk buka menu.\n"
        "• <b>Rekod Masuk</b> — Tekan bila tiba di tempat kerja\n"
        "• <b>Rekod Keluar</b> — Tekan bila selesai bertugas\n\n"
        "<b>PERMOHONAN CUTI</b>\n"
        "• Tekan <b>Mohon Cuti</b> dalam menu group ini\n"
        "• Bot akan hantar pautan — klik untuk sambung dalam chat peribadi\n"
        "• Ikuti langkah dalam chat peribadi:\n"
        "   ① Pilih jenis cuti (Tahunan / Sakit / Kecemasan)\n"
        "   ② Masukkan tarikh mula (format: YYYY-MM-DD atau DD/MM/YYYY)\n"
        "   ③ Masukkan tarikh akhir\n"
        "   ④ Masukkan alasan ringkas\n"
        "   ⑤ Muat naik gambar sokongan (untuk Cuti Sakit &amp; Kecemasan sahaja)\n"
        "   ⑥ Tekan <b>Sahkan</b> untuk hantar\n"
        "• Setelah dihantar, makluman akan dipaparkan dalam group site\n\n"
        "<b>JENIS CUTI</b>\n"
        f"• <b>Cuti Tahunan</b> — {annual_leave_notice_text()}\n"
        "• <b>Cuti Sakit (MC)</b> — Wajib muat naik gambar MC/surat doktor\n"
        "• <b>Cuti Kecemasan</b> — Wajib muat naik gambar sokongan\n\n"
        "<b>MAKLUMAT LAIN</b>\n"
        "• <b>Status Hari Ini</b> — Semak rekod kehadiran dan cuti hari ini\n"
        "• <b>Cuti Saya</b> — Lihat sejarah 5 permohonan cuti terkini\n"
        "• <b>Profil Saya</b> — Lihat maklumat profil anda\n\n"
        "Sebarang masalah, sila hubungi admin."
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
        "\nAnda boleh semak cuti menunggu, lihat ringkasan Telegram, jana laporan ikut site dan bulan, atau muat turun laporan PDF dan Excel terus dari sini."
        f"{web_line}"
    )


def build_admin_report_site_picker_text() -> str:
    return (
        "<b>Laporan Ikut Site/Bulan</b>\n"
        "Pilih site yang anda mahu gunakan untuk laporan Telegram ini."
    )


def build_admin_report_month_picker_text(*, site_name: str, year: int) -> str:
    return (
        "<b>Pilih Bulan Laporan</b>\n"
        f"Site: {html.escape(site_name)}\n"
        f"Tahun: {year}\n"
        "Tekan bulan yang anda mahu jana."
    )


def build_admin_report_format_picker_text(*, site_name: str, period_label: str) -> str:
    return (
        "<b>Pilih Format Laporan</b>\n"
        f"Site: {html.escape(site_name)}\n"
        f"Tempoh: {html.escape(period_label)}\n"
        "Pilih ringkasan Telegram, PDF, atau Excel."
    )


def _format_metric_value(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def build_admin_today_summary_text(
    *,
    target_date: date,
    total_workers: int,
    checked_in: int,
    checked_out: int,
    pending_leaves: int,
) -> str:
    missing_check_in = max(total_workers - checked_in, 0)
    pending_checkout = max(checked_in - checked_out, 0)
    return (
        "<b>Ringkasan Hari Ini</b>\n"
        f"Tarikh: {format_display_date(target_date)}\n"
        f"Jumlah pekerja aktif: {total_workers}\n"
        f"Sudah rekod masuk: {checked_in}\n"
        f"Sudah rekod keluar: {checked_out}\n"
        f"Belum rekod masuk: {missing_check_in}\n"
        f"Belum rekod keluar: {pending_checkout}\n"
        f"Cuti menunggu semakan: {pending_leaves}"
    )


def build_monthly_report_summary_text(
    *,
    period_label: str,
    site_name: str,
    total_workers: int,
    total_present_days: int,
    total_completed_days: int,
    average_present_days: float,
    completion_rate: float,
) -> str:
    pending_checkout_days = max(total_present_days - total_completed_days, 0)
    return (
        "<b>Ringkasan Laporan Bulanan</b>\n"
        f"Tempoh: {html.escape(period_label)}\n"
        f"Skop: {html.escape(site_name)}\n"
        f"Jumlah pekerja: {total_workers}\n"
        f"Jumlah hari hadir: {total_present_days}\n"
        f"Jumlah hari lengkap: {total_completed_days}\n"
        f"Hari belum lengkap: {pending_checkout_days}\n"
        f"Purata hari hadir seorang: {_format_metric_value(average_present_days)}\n"
        f"Kadar lengkap: {_format_metric_value(completion_rate)}%"
    )


def build_leave_summary_text(
    leave_id: int,
    worker_name: str,
    leave_type: str,
    start_date: date,
    end_date: date,
    day_portion: Optional[str],
    reason: str,
) -> str:
    return (
        f"<b>Permohonan Cuti #{leave_id}</b>\n"
        f"Pekerja: {worker_name}\n"
        f"Jenis: {leave_label(leave_type, day_portion=day_portion)}\n"
        f"Tarikh: {format_display_date(start_date)} hingga {format_display_date(end_date)}\n"
        f"Tempoh: {format_leave_duration(start_date=start_date, end_date=end_date, day_portion=day_portion)}\n"
        f"Sebab: {reason}"
    )


def build_leave_review_text(
    leave_id: int,
    leave_type: str,
    start_date: date,
    end_date: date,
    day_portion: Optional[str],
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
        f"Jenis: {leave_label(leave_type, day_portion=day_portion)}\n"
        f"Tarikh: {format_display_date(start_date)} hingga {format_display_date(end_date)}\n"
        f"Tempoh: {format_leave_duration(start_date=start_date, end_date=end_date, day_portion=day_portion)}"
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
    day_portion: Optional[str],
    reason: str,
    has_supporting_photo: bool,
) -> str:
    document_line = "Ada" if has_supporting_photo else "Tiada"
    if has_supporting_photo:
        group_notice = "\nMakluman Group: Bukti sokongan dan alasan akan dihantar ke group site."
    else:
        group_notice = "\nMakluman Group: Permohonan ini akan dimaklumkan ke group site."
    return (
        "<b>Sahkan Permohonan Cuti</b>\n"
        f"Pekerja: {worker_name}\n"
        f"Jenis: {leave_label(leave_type, day_portion=day_portion)}\n"
        f"Tarikh: {format_display_date(start_date)} hingga {format_display_date(end_date)}\n"
        f"Tempoh: {format_leave_duration(start_date=start_date, end_date=end_date, day_portion=day_portion)}\n"
        f"Sebab: {reason}\n"
        f"Dokumen Sokongan: {document_line}\n\n"
        f"Tekan <b>Sahkan</b> untuk menghantar permohonan."
        f"{group_notice}"
    )


def build_today_status_text(
    *,
    worker_name: str,
    site_name: Optional[str],
    check_in_at: Optional[datetime],
    check_out_at: Optional[datetime],
    approved_leave_label: Optional[str],
    approved_leave_is_partial: bool = False,
    public_holiday_label: Optional[str] = None,
) -> str:
    site_line = site_name or "Belum ditetapkan"
    if approved_leave_label:
        if approved_leave_is_partial and (check_in_at or check_out_at):
            status_line = f"Kehadiran + Cuti Separuh Hari ({approved_leave_label})"
        elif approved_leave_is_partial:
            status_line = f"Cuti Separuh Hari ({approved_leave_label})"
        else:
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
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    raise ValueError(
        "Format tarikh tidak dikenali. Sila gunakan salah satu format berikut:\n"
        "• <code>2026-05-20</code> (YYYY-MM-DD)\n"
        "• <code>20/05/2026</code> (DD/MM/YYYY)\n"
        "• <code>20-05-2026</code> (DD-MM-YYYY)"
    )
