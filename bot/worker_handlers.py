from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.context import (
    attendance_restriction_text,
    inactive_worker_text,
    is_admin,
    leave_restriction_text,
    load_worker_access,
    local_tz,
    registered_workers_only_text,
    worker_group_restriction_text,
    worker_chat_is_allowed,
)
from bot.keyboards import (
    WORKER_MENU_BUTTON,
    confirmation_keyboard,
    flow_control_keyboard,
    is_back_alias,
    is_cancel_alias,
    is_worker_menu_alias,
    leave_type_keyboard,
    main_menu_keyboard,
    worker_menu_keyboard,
)
from bot.admin_handlers import send_admin_menu_message
from bot.messages import (
    build_registration_confirmation_text,
    build_today_status_text,
    build_worker_leave_history_text,
    build_worker_profile_text,
    format_display_date,
    registration_intro_text,
    worker_menu_text,
)
from datetime_utils import format_local_datetime
from bot.states import LeaveApplicationStates, RegistrationStates
from models import session_scope
from services.attendance_service import (
    AttendanceError,
    check_in,
    check_out,
    get_approved_leave_for_day,
    get_attendance_for_date,
    self_register_worker,
)
from services.leave_service import leave_is_partial_day, leave_label, leave_status_label, list_leave_requests_for_worker
from services.public_holiday_service import get_public_holiday_for_date, public_holiday_label

REGISTRATION_BACK_CALLBACK = "registration:back"
REGISTRATION_CANCEL_CALLBACK = "registration:cancel"
router = Router()


async def _send_navigation_menu(message: Message, *, show_worker_menu: bool, show_admin_menu: bool) -> None:
    reply_markup = main_menu_keyboard(
        show_worker_menu=show_worker_menu,
        show_admin_menu=show_admin_menu and message.chat.type == "private",
    )
    if reply_markup:
        await message.answer(
            "Butang menu sudah dipaparkan di bawah. Pilih menu yang anda perlukan tanpa menaip command slash.",
            reply_markup=reply_markup,
        )


async def _send_worker_menu_message(message: Message) -> None:
    await message.answer(worker_menu_text(), reply_markup=worker_menu_keyboard())


async def _show_registration_confirmation(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(RegistrationStates.confirmation)
    await message.answer(
        build_registration_confirmation_text(data["full_name"], data["ic_number"]),
        reply_markup=confirmation_keyboard(
            confirm_callback="registration:confirm",
            back_callback=REGISTRATION_BACK_CALLBACK,
            cancel_callback=REGISTRATION_CANCEL_CALLBACK,
        ),
    )


async def _cancel_registration_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Pendaftaran dibatalkan. Taip <code>menu</code> bila anda mahu mula semula.")


async def _step_back_in_registration_flow(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state == RegistrationStates.ic_number.state:
        await state.set_state(RegistrationStates.full_name)
        await message.answer(
            "Baik, sila hantar semula <b>NAMA PENUH</b> anda.",
            reply_markup=flow_control_keyboard(include_back=False, cancel_callback=REGISTRATION_CANCEL_CALLBACK),
        )
        return
    if current_state == RegistrationStates.confirmation.state:
        await state.set_state(RegistrationStates.ic_number)
        await message.answer(
            "Sila hantar semula <b>NO. IC</b> anda.",
            reply_markup=flow_control_keyboard(
                back_callback=REGISTRATION_BACK_CALLBACK,
                cancel_callback=REGISTRATION_CANCEL_CALLBACK,
            ),
        )
        return
    await message.answer("Anda sudah berada di langkah pertama pendaftaran.")


@router.message(CommandStart(deep_link=True))
async def handle_deep_link_start(message: Message, command: CommandObject, state: FSMContext) -> None:
    if command.args != "leave":
        await show_menu(message, state)
        return

    worker_access = await load_worker_access(message.from_user.id)
    if worker_access.is_inactive:
        await message.answer(inactive_worker_text())
        return
    worker = worker_access.worker
    if not worker:
        await message.answer(registered_workers_only_text())
        return

    await state.clear()
    await state.set_state(LeaveApplicationStates.leave_type)
    await message.answer("Sila pilih jenis cuti.", reply_markup=leave_type_keyboard(cancel_callback="leave:cancel"))


@router.message(CommandStart())
@router.message(Command("menu"))
@router.message(F.text.func(is_worker_menu_alias))
async def show_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    worker_access = await load_worker_access(message.from_user.id)
    if worker_access.is_inactive:
        await message.answer(inactive_worker_text())
        return
    worker = worker_access.worker
    if not worker_chat_is_allowed(worker, message) and not is_admin(message.from_user.id):
        await message.answer(worker_group_restriction_text())
        return
    if not worker and not is_admin(message.from_user.id):
        await state.set_state(RegistrationStates.full_name)
        await message.answer(
            registration_intro_text(),
            reply_markup=flow_control_keyboard(include_back=False, cancel_callback=REGISTRATION_CANCEL_CALLBACK),
        )
        return

    await _send_navigation_menu(
        message,
        show_worker_menu=bool(worker),
        show_admin_menu=is_admin(message.from_user.id),
    )
    if worker:
        await _send_worker_menu_message(message)
    if is_admin(message.from_user.id) and message.chat.type == "private":
        await send_admin_menu_message(message)


@router.message(F.text == WORKER_MENU_BUTTON)
async def show_worker_menu_from_text_button(message: Message, state: FSMContext) -> None:
    await state.clear()
    worker_access = await load_worker_access(message.from_user.id)
    if worker_access.is_inactive:
        await message.answer(inactive_worker_text())
        return
    worker = worker_access.worker
    if not worker:
        await message.answer(registered_workers_only_text())
        return
    if not worker_chat_is_allowed(worker, message):
        await message.answer(worker_group_restriction_text())
        return

    await _send_navigation_menu(
        message,
        show_worker_menu=True,
        show_admin_menu=is_admin(message.from_user.id),
    )
    await _send_worker_menu_message(message)


@router.callback_query(F.data.in_({"attendance:checkin", "attendance:checkout"}))
async def handle_attendance_action(callback: CallbackQuery) -> None:
    await callback.answer()
    worker_access = await load_worker_access(callback.from_user.id)
    if worker_access.is_inactive:
        await callback.message.answer(inactive_worker_text())
        return
    worker = worker_access.worker
    if not worker:
        await callback.message.answer(registered_workers_only_text())
        return
    if not worker_chat_is_allowed(worker, callback):
        await callback.message.answer(attendance_restriction_text())
        return

    async with session_scope() as session:
        try:
            now = datetime.now(local_tz)
            if callback.data.endswith("checkin"):
                record = await check_in(
                    session,
                    worker=worker,
                    chat_id=callback.message.chat.id,
                    occurred_at=now,
                )
                await callback.message.answer(
                    f"{worker.full_name} berjaya direkod masuk pada {format_local_datetime(record.check_in_at, '%H:%M:%S')}."
                )
                return

            record = await check_out(
                session,
                worker=worker,
                chat_id=callback.message.chat.id,
                occurred_at=now,
            )
            await callback.message.answer(
                f"{worker.full_name} berjaya direkod keluar pada {format_local_datetime(record.check_out_at, '%H:%M:%S')}."
            )
        except AttendanceError as exc:
            await callback.message.answer(str(exc))


@router.callback_query(F.data == "worker:status")
async def show_worker_status(callback: CallbackQuery) -> None:
    await callback.answer()
    worker_access = await load_worker_access(callback.from_user.id)
    if worker_access.is_inactive:
        await callback.message.answer(inactive_worker_text())
        return
    worker = worker_access.worker
    if not worker:
        await callback.message.answer(registered_workers_only_text())
        return
    if not worker_chat_is_allowed(worker, callback):
        await callback.message.answer(attendance_restriction_text())
        return

    async with session_scope() as session:
        today = datetime.now(local_tz).date()
        attendance = await get_attendance_for_date(session, worker_id=worker.id, attendance_date=today)
        approved_leave = await get_approved_leave_for_day(session, worker_id=worker.id, target_date=today)
        public_holiday = await get_public_holiday_for_date(
            session,
            target_date=today,
            site_id=worker.site_id,
        )

    await callback.message.answer(
        build_today_status_text(
            worker_name=worker.full_name,
            site_name=worker.site.name if worker.site else None,
            check_in_at=attendance.check_in_at if attendance else None,
            check_out_at=attendance.check_out_at if attendance else None,
            approved_leave_label=(
                leave_label(approved_leave.leave_type, day_portion=approved_leave.day_portion)
                if approved_leave
                else None
            ),
            approved_leave_is_partial=leave_is_partial_day(approved_leave.day_portion) if approved_leave else False,
            public_holiday_label=public_holiday_label(public_holiday),
        ),
        reply_markup=worker_menu_keyboard(),
    )


@router.callback_query(F.data == "worker:profile")
async def show_worker_profile(callback: CallbackQuery) -> None:
    await callback.answer()
    worker_access = await load_worker_access(callback.from_user.id)
    if worker_access.is_inactive:
        await callback.message.answer(inactive_worker_text())
        return
    worker = worker_access.worker
    if not worker:
        await callback.message.answer(registered_workers_only_text())
        return
    if not worker_chat_is_allowed(worker, callback):
        await callback.message.answer(worker_group_restriction_text())
        return

    await callback.message.answer(
        build_worker_profile_text(
            worker_name=worker.full_name,
            site_name=worker.site.name if worker.site else None,
            employee_code=worker.employee_code,
            ic_number=worker.ic_number,
            telegram_user_id=worker.telegram_user_id,
        ),
        reply_markup=worker_menu_keyboard(),
    )


@router.callback_query(F.data == "worker:leaves")
async def show_worker_leave_history(callback: CallbackQuery) -> None:
    await callback.answer()
    worker_access = await load_worker_access(callback.from_user.id)
    if worker_access.is_inactive:
        await callback.message.answer(inactive_worker_text())
        return
    worker = worker_access.worker
    if not worker:
        await callback.message.answer(registered_workers_only_text())
        return
    if not worker_chat_is_allowed(worker, callback):
        await callback.message.answer(leave_restriction_text())
        return

    async with session_scope() as session:
        leave_items = await list_leave_requests_for_worker(session, worker_id=worker.id, limit=5)

    entries = [
        {
            "id": str(item.id),
            "type": leave_label(item.leave_type, day_portion=item.day_portion),
            "date_range": f"{format_display_date(item.start_date)} - {format_display_date(item.end_date)}",
            "status": leave_status_label(item.status),
        }
        for item in leave_items
    ]
    await callback.message.answer(build_worker_leave_history_text(entries), reply_markup=worker_menu_keyboard())


@router.message(RegistrationStates.full_name)
async def capture_registration_name(message: Message, state: FSMContext) -> None:
    if is_cancel_alias(message.text):
        await _cancel_registration_flow(message, state)
        return
    if is_back_alias(message.text):
        await _step_back_in_registration_flow(message, state)
        return

    full_name = (message.text or "").strip()
    if not full_name:
        await message.answer("Sila hantar <b>NAMA PENUH</b> anda.")
        return

    await state.update_data(full_name=full_name)
    await state.set_state(RegistrationStates.ic_number)
    await message.answer(
        "Baik, sekarang sila hantar <b>NO. IC</b> anda.",
        reply_markup=flow_control_keyboard(
            back_callback=REGISTRATION_BACK_CALLBACK,
            cancel_callback=REGISTRATION_CANCEL_CALLBACK,
        ),
    )


@router.message(RegistrationStates.ic_number)
async def capture_registration_ic(message: Message, state: FSMContext) -> None:
    if is_cancel_alias(message.text):
        await _cancel_registration_flow(message, state)
        return
    if is_back_alias(message.text):
        await _step_back_in_registration_flow(message, state)
        return

    ic_number = (message.text or "").strip()
    if not ic_number:
        await message.answer("Sila hantar <b>NO. IC</b> anda.")
        return

    await state.update_data(ic_number=ic_number)
    await _show_registration_confirmation(message, state)


@router.callback_query(F.data == "registration:confirm")
async def confirm_registration(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    async with session_scope() as session:
        try:
            worker = await self_register_worker(
                session,
                telegram_user_id=callback.from_user.id,
                full_name=data["full_name"],
                ic_number=data["ic_number"],
            )
        except AttendanceError as exc:
            await callback.message.answer(str(exc))
            await state.clear()
            return
    await state.clear()
    await _send_navigation_menu(
        callback.message,
        show_worker_menu=True,
        show_admin_menu=is_admin(callback.from_user.id),
    )
    await callback.message.answer(
        f"Pendaftaran untuk {worker.full_name} telah berjaya.\n"
        "Anda kini boleh menggunakan menu kehadiran.",
        reply_markup=worker_menu_keyboard(),
    )


@router.callback_query(F.data == REGISTRATION_BACK_CALLBACK)
async def handle_registration_back_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _step_back_in_registration_flow(callback.message, state)


@router.callback_query(F.data == REGISTRATION_CANCEL_CALLBACK)
async def handle_registration_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _cancel_registration_flow(callback.message, state)


@router.message(RegistrationStates.full_name, F.text.func(is_cancel_alias))
@router.message(RegistrationStates.ic_number, F.text.func(is_cancel_alias))
@router.message(RegistrationStates.confirmation, F.text.func(is_cancel_alias))
async def cancel_registration_from_text(message: Message, state: FSMContext) -> None:
    await _cancel_registration_flow(message, state)


@router.message(RegistrationStates.full_name, F.text.func(is_back_alias))
@router.message(RegistrationStates.ic_number, F.text.func(is_back_alias))
@router.message(RegistrationStates.confirmation, F.text.func(is_back_alias))
async def go_back_in_registration_from_text(message: Message, state: FSMContext) -> None:
    await _step_back_in_registration_flow(message, state)
