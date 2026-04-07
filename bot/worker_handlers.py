from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.context import (
    attendance_restriction_text,
    is_admin,
    load_registered_worker,
    local_tz,
    registered_workers_only_text,
    worker_group_restriction_text,
    worker_chat_is_allowed,
)
from bot.keyboards import admin_menu_keyboard, worker_menu_keyboard
from bot.messages import admin_menu_text, registration_intro_text, worker_menu_text
from bot.states import RegistrationStates
from config import get_settings
from models import session_scope
from services.attendance_service import (
    AttendanceError,
    check_in,
    check_out,
    get_worker_by_telegram_id,
    self_register_worker,
)

router = Router()
settings = get_settings()


@router.message(CommandStart())
@router.message(Command("menu"))
async def show_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    worker = await load_registered_worker(message.from_user.id)
    if not worker_chat_is_allowed(worker, message) and not is_admin(message.from_user.id):
        await message.answer(worker_group_restriction_text())
        return
    if not worker and not is_admin(message.from_user.id):
        await state.set_state(RegistrationStates.full_name)
        await message.answer(registration_intro_text())
        return

    if worker:
        await message.answer(worker_menu_text(), reply_markup=worker_menu_keyboard())
    if is_admin(message.from_user.id):
        await message.answer(
            admin_menu_text(web_login_enabled=bool(settings.admin_web_login_url)),
            reply_markup=admin_menu_keyboard(web_login_url=settings.admin_web_login_url),
        )


@router.callback_query(F.data.in_({"attendance:checkin", "attendance:checkout"}))
async def handle_attendance_action(callback: CallbackQuery) -> None:
    await callback.answer()
    async with session_scope() as session:
        worker = await get_worker_by_telegram_id(session, callback.from_user.id)
        if not worker:
            await callback.message.answer(registered_workers_only_text())
            return
        if not worker_chat_is_allowed(worker, callback):
            await callback.message.answer(attendance_restriction_text())
            return

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
                    f"{worker.full_name} berjaya direkod masuk pada {record.check_in_at.astimezone(local_tz):%H:%M:%S}."
                )
                return

            record = await check_out(
                session,
                worker=worker,
                chat_id=callback.message.chat.id,
                occurred_at=now,
            )
            await callback.message.answer(
                f"{worker.full_name} berjaya direkod keluar pada {record.check_out_at.astimezone(local_tz):%H:%M:%S}."
            )
        except AttendanceError as exc:
            await callback.message.answer(str(exc))


@router.message(RegistrationStates.full_name)
async def capture_registration_name(message: Message, state: FSMContext) -> None:
    full_name = (message.text or "").strip()
    if not full_name:
        await message.answer("Sila hantar <b>NAMA PENUH</b> anda.")
        return

    await state.update_data(full_name=full_name)
    await state.set_state(RegistrationStates.ic_number)
    await message.answer("Baik, sekarang sila hantar <b>NO. IC</b> anda.")


@router.message(RegistrationStates.ic_number)
async def capture_registration_ic(message: Message, state: FSMContext) -> None:
    ic_number = (message.text or "").strip()
    if not ic_number:
        await message.answer("Sila hantar <b>NO. IC</b> anda.")
        return

    data = await state.get_data()
    async with session_scope() as session:
        try:
            worker = await self_register_worker(
                session,
                telegram_user_id=message.from_user.id,
                full_name=data["full_name"],
                ic_number=ic_number,
            )
        except AttendanceError as exc:
            await message.answer(str(exc))
            await state.clear()
            return

    await state.clear()
    await message.answer(
        f"Pendaftaran untuk {worker.full_name} telah berjaya.\n"
        "Anda kini boleh menggunakan menu kehadiran.",
        reply_markup=worker_menu_keyboard(),
    )
