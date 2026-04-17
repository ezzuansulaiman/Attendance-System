from __future__ import annotations

import calendar
import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import BotCommand, BufferedInputFile, CallbackQuery, Message

from bot.context import is_admin, local_tz
from bot.keyboards import (
    ADMIN_MENU_BUTTON,
    admin_menu_keyboard,
    admin_report_format_keyboard,
    admin_report_month_keyboard,
    admin_report_site_keyboard,
    is_admin_menu_alias,
    leave_review_keyboard,
)
from bot.reminders import extract_reminder_chat_ids
from bot.notifications import send_leave_review_to_worker
from bot.messages import (
    admin_menu_text,
    build_admin_report_format_picker_text,
    build_admin_report_month_picker_text,
    build_admin_report_site_picker_text,
    build_admin_today_summary_text,
    build_bot_guide_text,
    build_leave_summary_text,
    build_monthly_report_summary_text,
)
from config import get_settings
from models import session_scope
from services.attendance_service import get_dashboard_summary
from services.leave_service import (
    LeaveError,
    approve_leave_request,
    get_leave_request,
    list_pending_leave_requests,
    reject_leave_request,
)
from services.pdf_generator import PdfExportError
from services.report_service import (
    build_report_download_filename,
    build_monthly_attendance_report,
    generate_monthly_attendance_excel,
    generate_monthly_attendance_pdf,
)
from services.site_service import get_site_by_id, list_sites

router = Router()
settings = get_settings()
PDF_EXPORT_FAILURE_MESSAGE = "PDF tidak dapat dijana sekarang. Sila semak log pelayan dan cuba lagi."


async def send_admin_menu_message(message: Message) -> None:
    await message.answer(
        admin_menu_text(web_login_enabled=bool(settings.admin_web_login_url)),
        reply_markup=admin_menu_keyboard(web_login_url=settings.admin_web_login_url),
    )


async def _require_admin(callback: CallbackQuery) -> bool:
    if not is_admin(callback.from_user.id):
        await callback.message.answer("Akses pentadbir diperlukan.")
        return False
    return True


def _today_local_date() -> date:
    return datetime.now(local_tz).date()


def _relative_month(reference_date: date, *, offset: int) -> tuple[int, int]:
    month_index = (reference_date.year * 12 + reference_date.month - 1) + offset
    year = month_index // 12
    month = month_index % 12 + 1
    return year, month


def _report_period_label(*, year: int, month: int) -> str:
    return f"{calendar.month_name[month]} {year}"


async def _get_active_site(site_id: int):
    async with session_scope() as session:
        site = await get_site_by_id(session, site_id)
    if not site or not site.is_active:
        return None
    return site


async def _send_monthly_pdf(
    callback: CallbackQuery,
    *,
    year: int,
    month: int,
    site_id: int | None = None,
    site_name: str | None = None,
) -> None:
    try:
        async with session_scope() as session:
            pdf_bytes = await generate_monthly_attendance_pdf(
                session,
                year=year,
                month=month,
                site_id=site_id,
            )
    except PdfExportError:
        await callback.message.answer(PDF_EXPORT_FAILURE_MESSAGE)
        return

    filename = build_report_download_filename(year=year, month=month, extension="pdf")
    month_name = calendar.month_name[month]
    caption = f"Laporan kehadiran {month_name} {year}."
    if site_name:
        caption = f"Laporan kehadiran {month_name} {year} untuk {site_name}."
    await callback.message.answer_document(
        BufferedInputFile(pdf_bytes, filename=filename),
        caption=caption,
    )


async def _send_monthly_excel(
    callback: CallbackQuery,
    *,
    year: int,
    month: int,
    site_id: int | None = None,
    site_name: str | None = None,
) -> None:
    async with session_scope() as session:
        excel_bytes = await generate_monthly_attendance_excel(
            session,
            year=year,
            month=month,
            site_id=site_id,
        )

    filename = build_report_download_filename(year=year, month=month, extension="xlsx")
    month_name = calendar.month_name[month]
    caption = f"Laporan Excel kehadiran {month_name} {year}."
    if site_name:
        caption = f"Laporan Excel kehadiran {month_name} {year} untuk {site_name}."
    await callback.message.answer_document(
        BufferedInputFile(excel_bytes, filename=filename),
        caption=caption,
    )


async def _send_monthly_summary(
    callback: CallbackQuery,
    *,
    year: int,
    month: int,
    site_id: int | None = None,
) -> None:
    async with session_scope() as session:
        report = await build_monthly_attendance_report(session, year=year, month=month, site_id=site_id)

    await callback.message.answer(
        build_monthly_report_summary_text(
            period_label=report["period_label"],
            site_name=report["site_name"],
            total_workers=report["summary"]["total_workers"],
            total_present_days=report["summary"]["total_present_days"],
            total_completed_days=report["summary"]["total_completed_days"],
            average_present_days=report["summary"]["average_present_days"],
            completion_rate=report["summary"]["completion_rate"],
        )
    )


async def _show_custom_report_site_picker(callback: CallbackQuery) -> None:
    async with session_scope() as session:
        sites = list(await list_sites(session, active_only=True))

    if not sites:
        await callback.message.answer("Tiada site aktif ditemui untuk jana laporan.")
        return

    await callback.message.answer(
        build_admin_report_site_picker_text(),
        reply_markup=admin_report_site_keyboard(sites=sites),
    )


async def _show_custom_report_month_picker(callback: CallbackQuery, *, site_id: int, year: int) -> None:
    site = await _get_active_site(site_id)
    if not site:
        await callback.message.answer("Site tidak ditemui atau tidak lagi aktif.")
        return

    await callback.message.answer(
        build_admin_report_month_picker_text(site_name=site.name, year=year),
        reply_markup=admin_report_month_keyboard(site_id=site.id, year=year),
    )


@router.message(Command("admin"))
@router.message(F.text.func(is_admin_menu_alias))
async def admin_menu(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Arahan ini hanya untuk pentadbir Telegram yang didaftarkan dalam ADMIN_IDS.")
        return
    await send_admin_menu_message(message)


@router.message(F.text == ADMIN_MENU_BUTTON)
async def admin_menu_from_text_button(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Menu ini hanya untuk pentadbir yang didaftarkan.")
        return
    await send_admin_menu_message(message)


@router.callback_query(F.data == "admin:menu")
async def admin_menu_from_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback):
        return
    await send_admin_menu_message(callback.message)


@router.callback_query(F.data == "admin:broadcast:guide")
async def broadcast_bot_guide(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    if not await _require_admin(callback):
        return

    async with session_scope() as session:
        sites = await list_sites(session, active_only=True)

    chat_ids = extract_reminder_chat_ids(list(sites), settings.group_id)
    if not chat_ids:
        await callback.message.answer(
            "Tiada group Telegram yang dikonfigurasi. Sila tetapkan GROUP_ID atau telegram_group_id untuk site."
        )
        return

    guide_text = build_bot_guide_text()
    sent = 0
    failed = 0
    for chat_id in chat_ids:
        try:
            await bot.send_message(chat_id=chat_id, text=guide_text)
            sent += 1
        except Exception as exc:
            logger.warning("Failed to send guide to chat %s: %s", chat_id, exc)
            failed += 1

    if sent:
        suffix = f" ({failed} group gagal)" if failed else ""
        await callback.message.answer(f"Panduan berjaya dihantar ke {sent} group{suffix}.")
    else:
        await callback.message.answer(
            "Panduan gagal dihantar ke semua group. Pastikan bot adalah ahli group dan mempunyai kebenaran menghantar mesej."
        )


@router.callback_query(F.data == "admin:pending")
async def show_pending_leaves(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback):
        return

    async with session_scope() as session:
        pending_requests = await list_pending_leave_requests(session)

    if not pending_requests:
        await callback.message.answer("Tiada permohonan cuti yang menunggu semakan.")
        return

    for leave_request in pending_requests:
        text = build_leave_summary_text(
            leave_request.id,
            leave_request.worker.full_name,
            leave_request.leave_type,
            leave_request.start_date,
            leave_request.end_date,
            leave_request.day_portion,
            leave_request.reason,
        )
        if leave_request.telegram_file_id:
            await callback.message.answer_photo(
                photo=leave_request.telegram_file_id,
                caption=text,
                reply_markup=leave_review_keyboard(leave_request.id),
            )
            continue

        await callback.message.answer(
            text,
            reply_markup=leave_review_keyboard(leave_request.id),
        )


@router.message(Command("setgroup"))
async def set_group_command(message: Message) -> None:
    """Admin command to set telegram_group_id for a site. Usage: /setgroup <site_id> <group_id>"""
    if not is_admin(message.from_user.id):
        await message.answer("Arahan ini hanya untuk pentadbir.")
        return
    
    args = message.text.split()
    if len(args) != 3:
        await message.answer(
            "Penggunaan: /setgroup <site_id> <group_id>\n\n"
            "Contoh: /setgroup 1 -100123456789\n\n"
            "Untuk dapatkan group ID:\n"
            "1. Tambah bot ke dalam group\n"
            "2. Forward satu mesej dari group itu ke @userinfobot\n"
            "3. Atau gunakan @RawDataBot untuk lihat ID group"
        )
        return
    
    try:
        site_id = int(args[1])
        group_id = int(args[2])
    except ValueError:
        await message.answer("Site ID dan Group ID mestilah nombor.")
        return
    
    async with session_scope() as session:
        from sqlalchemy import text, select
        from models.models import Site
        
        # Check if site exists
        result = await session.execute(select(Site).where(Site.id == site_id))
        site = result.scalar_one_or_none()
        
        if not site:
            await message.answer(f"Site dengan ID {site_id} tidak ditemui.")
            return
        
        # Update the telegram_group_id
        await session.execute(
            text("UPDATE sites SET telegram_group_id = :group_id WHERE id = :site_id"),
            {"group_id": group_id, "site_id": site_id}
        )
        await session.commit()
    
    await message.answer(
        f"✅ Berjaya!\n\n"
        f"Site: {site.name} (ID: {site_id})\n"
        f"Telegram Group ID: {group_id}\n\n"
        f"Sekarang pekerja boleh memohon cuti dalam group tersebut."
    )


@router.message(Command("sitelist"))
async def list_sites_command(message: Message) -> None:
    """Admin command to list all sites and their telegram_group_id"""
    if not is_admin(message.from_user.id):
        await message.answer("Arahan ini hanya untuk pentadbir.")
        return
    
    async with session_scope() as session:
        from sqlalchemy import text
        
        result = await session.execute(text("SELECT id, name, code, telegram_group_id FROM sites ORDER BY id"))
        sites = result.fetchall()
    
    if not sites:
        await message.answer("Tiada site dalam database.")
        return
    
    text_response = "📋 **SENARAI SITE**\n\n"
    for site in sites:
        group_status = f"Group ID: `{site.telegram_group_id}`" if site.telegram_group_id else "❌ Group ID: Tidak ditetapkan"
        text_response += f"• ID: {site.id}\n  Nama: {site.name}\n  Kod: {site.code or 'N/A'}\n  {group_status}\n\n"
    
    text_response += "\nGunakan /setgroup <site_id> <group_id> untuk set group ID."
    await message.answer(text_response)


@router.callback_query(F.data == "admin:report:custom")
async def start_custom_report_flow(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback):
        return
    await _show_custom_report_site_picker(callback)


@router.callback_query(F.data.startswith("admin:report:custom:site:"))
async def choose_custom_report_site(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback):
        return

    site_id = int(callback.data.rsplit(":", 1)[-1])
    await _show_custom_report_month_picker(callback, site_id=site_id, year=_today_local_date().year)


@router.callback_query(F.data.startswith("admin:report:custom:year:"))
async def choose_custom_report_year(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback):
        return

    _, _, _, _, raw_site_id, raw_year = callback.data.split(":")
    await _show_custom_report_month_picker(callback, site_id=int(raw_site_id), year=int(raw_year))


@router.callback_query(F.data.startswith("admin:report:custom:month:"))
async def choose_custom_report_month(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback):
        return

    _, _, _, _, raw_site_id, raw_year, raw_month = callback.data.split(":")
    site_id = int(raw_site_id)
    year = int(raw_year)
    month = int(raw_month)
    if month < 1 or month > 12:
        await callback.message.answer("Bulan laporan tidak sah.")
        return

    site = await _get_active_site(site_id)
    if not site:
        await callback.message.answer("Site tidak ditemui atau tidak lagi aktif.")
        return

    await callback.message.answer(
        build_admin_report_format_picker_text(
            site_name=site.name,
            period_label=_report_period_label(year=year, month=month),
        ),
        reply_markup=admin_report_format_keyboard(site_id=site.id, year=year, month=month),
    )


@router.callback_query(F.data.startswith("admin:report:custom:run:"))
async def run_custom_report(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback):
        return

    _, _, _, _, raw_site_id, raw_year, raw_month, action = callback.data.split(":")
    site_id = int(raw_site_id)
    year = int(raw_year)
    month = int(raw_month)
    if month < 1 or month > 12:
        await callback.message.answer("Bulan laporan tidak sah.")
        return

    site = await _get_active_site(site_id)
    if not site:
        await callback.message.answer("Site tidak ditemui atau tidak lagi aktif.")
        return

    if action == "summary":
        await _send_monthly_summary(callback, year=year, month=month, site_id=site.id)
        return
    if action == "pdf":
        await _send_monthly_pdf(callback, year=year, month=month, site_id=site.id, site_name=site.name)
        return
    if action == "excel":
        await _send_monthly_excel(callback, year=year, month=month, site_id=site.id, site_name=site.name)
        return

    await callback.message.answer("Format laporan tidak sah.")


@router.callback_query(F.data == "admin:report:today:summary")
async def send_today_summary(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback):
        return

    today = _today_local_date()
    async with session_scope() as session:
        summary = await get_dashboard_summary(session, target_date=today)

    await callback.message.answer(
        build_admin_today_summary_text(
            target_date=today,
            total_workers=summary["total_workers"],
            checked_in=summary["checked_in"],
            checked_out=summary["checked_out"],
            pending_leaves=summary["pending_leaves"],
        )
    )


@router.callback_query(F.data == "admin:report:current:summary")
async def send_current_month_summary(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback):
        return

    today = _today_local_date()
    year, month = _relative_month(today, offset=0)
    await _send_monthly_summary(callback, year=year, month=month)


@router.callback_query(F.data == "admin:report:previous:summary")
async def send_previous_month_summary(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback):
        return

    today = _today_local_date()
    year, month = _relative_month(today, offset=-1)
    await _send_monthly_summary(callback, year=year, month=month)


@router.callback_query(F.data == "admin:report:current")
async def send_current_month_report(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback):
        return

    today = _today_local_date()
    year, month = _relative_month(today, offset=0)
    await _send_monthly_pdf(callback, year=year, month=month)


@router.callback_query(F.data == "admin:report:previous")
async def send_previous_month_report(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback):
        return

    today = _today_local_date()
    year, month = _relative_month(today, offset=-1)
    await _send_monthly_pdf(callback, year=year, month=month)


@router.callback_query(F.data == "admin:report:current:excel")
async def send_current_month_excel(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback):
        return

    today = _today_local_date()
    year, month = _relative_month(today, offset=0)
    await _send_monthly_excel(callback, year=year, month=month)


@router.callback_query(F.data == "admin:report:previous:excel")
async def send_previous_month_excel(callback: CallbackQuery) -> None:
    await callback.answer()
    if not await _require_admin(callback):
        return

    today = _today_local_date()
    year, month = _relative_month(today, offset=-1)
    await _send_monthly_excel(callback, year=year, month=month)


async def _review_leave(callback: CallbackQuery, bot: Bot, *, approve: bool) -> None:
    if not await _require_admin(callback):
        return

    leave_id = int(callback.data.rsplit(":", 1)[-1])
    async with session_scope() as session:
        leave_request = await get_leave_request(session, leave_id)
        if not leave_request:
            await callback.message.answer("Permohonan cuti tidak ditemui.")
            return
        try:
            if approve:
                leave_request = await approve_leave_request(
                    session,
                    leave_request=leave_request,
                    admin_telegram_id=callback.from_user.id,
                )
            else:
                leave_request = await reject_leave_request(
                    session,
                    leave_request=leave_request,
                    admin_telegram_id=callback.from_user.id,
                )
        except LeaveError as exc:
            await callback.message.answer(str(exc))
            return

    if leave_request.status == "approved":
        action_label = "diluluskan"
    elif approve:
        action_label = "ditolak automatik"
    else:
        action_label = "ditolak"
    await callback.message.answer(f"Permohonan cuti #{leave_request.id} telah {action_label}.")
    await send_leave_review_to_worker(bot, leave_request.id)


@router.callback_query(F.data.startswith("leave:approve:"))
async def approve_leave(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    await _review_leave(callback, bot, approve=True)


@router.callback_query(F.data.startswith("leave:reject:"))
async def reject_leave(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    await _review_leave(callback, bot, approve=False)


async def set_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Buka menu kehadiran"),
            BotCommand(command="menu", description="Paparkan menu pekerja"),
            BotCommand(command="admin", description="Paparkan menu pentadbir"),
        ]
    )
