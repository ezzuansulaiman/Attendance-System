from __future__ import annotations

import calendar
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import BotCommand, BufferedInputFile, CallbackQuery, Message

from bot.context import is_admin, local_tz
from bot.keyboards import admin_menu_keyboard, leave_review_keyboard
from bot.leave_handlers import notify_worker_review
from bot.messages import admin_menu_text, build_leave_summary_text
from config import get_settings
from models import session_scope
from services.leave_service import (
    LeaveError,
    approve_leave_request,
    get_leave_request,
    list_pending_leave_requests,
    reject_leave_request,
)
from services.report_service import generate_monthly_attendance_pdf

router = Router()
settings = get_settings()


@router.message(Command("admin"))
async def admin_menu(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("This command is restricted to Telegram admins configured in ADMIN_IDS.")
        return
    await message.answer(
        admin_menu_text(web_login_enabled=bool(settings.admin_web_login_url)),
        reply_markup=admin_menu_keyboard(web_login_url=settings.admin_web_login_url),
    )


@router.callback_query(F.data == "admin:pending")
async def show_pending_leaves(callback: CallbackQuery) -> None:
    await callback.answer()
    if not is_admin(callback.from_user.id):
        await callback.message.answer("Admin access required.")
        return

    async with session_scope() as session:
        pending_requests = await list_pending_leave_requests(session)

    if not pending_requests:
        await callback.message.answer("There are no pending leave requests.")
        return

    for leave_request in pending_requests:
        text = build_leave_summary_text(
            leave_request.id,
            leave_request.worker.full_name,
            leave_request.leave_type,
            leave_request.start_date,
            leave_request.end_date,
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


@router.callback_query(F.data == "admin:report:current")
async def send_current_month_report(callback: CallbackQuery) -> None:
    await callback.answer()
    if not is_admin(callback.from_user.id):
        await callback.message.answer("Admin access required.")
        return

    today = datetime.now(local_tz).date()
    async with session_scope() as session:
        pdf_bytes = await generate_monthly_attendance_pdf(
            session,
            year=today.year,
            month=today.month,
        )

    filename = f"attendance-{today.year}-{today.month:02d}.pdf"
    month_name = calendar.month_name[today.month]
    await callback.message.answer_document(
        BufferedInputFile(pdf_bytes, filename=filename),
        caption=f"{month_name} {today.year} attendance report.",
    )


async def _review_leave(callback: CallbackQuery, *, approve: bool) -> None:
    if not is_admin(callback.from_user.id):
        await callback.message.answer("Admin access required.")
        return

    leave_id = int(callback.data.rsplit(":", 1)[-1])
    async with session_scope() as session:
        leave_request = await get_leave_request(session, leave_id)
        if not leave_request:
            await callback.message.answer("Leave request not found.")
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

    action = "approved" if approve else "rejected"
    await callback.message.answer(f"Leave request #{leave_request.id} {action}.")
    await notify_worker_review(callback.bot, leave_request.id)


@router.callback_query(F.data.startswith("leave:approve:"))
async def approve_leave(callback: CallbackQuery) -> None:
    await callback.answer()
    await _review_leave(callback, approve=True)


@router.callback_query(F.data.startswith("leave:reject:"))
async def reject_leave(callback: CallbackQuery) -> None:
    await callback.answer()
    await _review_leave(callback, approve=False)


async def set_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Buka menu kehadiran"),
            BotCommand(command="menu", description="Paparkan menu pekerja"),
            BotCommand(command="admin", description="Open admin controls"),
        ]
    )
