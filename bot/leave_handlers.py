from __future__ import annotations

from typing import Optional

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.context import (
    leave_restriction_text,
    load_registered_worker,
    registered_workers_only_text,
    settings,
    worker_chat_is_allowed,
)
from bot.keyboards import leave_review_keyboard, leave_type_keyboard
from bot.messages import build_leave_review_text, build_leave_summary_text, parse_user_date
from bot.states import LeaveApplicationStates
from models import session_scope
from services.attendance_service import get_worker_by_telegram_id
from services.leave_service import (
    LeaveError,
    create_leave_request,
    get_leave_request,
    is_supported_leave_type,
    leave_label,
)

router = Router()


async def _notify_admins(bot: Bot, leave_request_id: int) -> None:
    async with session_scope() as session:
        leave_request = await get_leave_request(session, leave_request_id)
        if not leave_request:
            return

        text = build_leave_summary_text(
            leave_request.id,
            leave_request.worker.full_name,
            leave_request.leave_type,
            leave_request.start_date,
            leave_request.end_date,
            leave_request.reason,
        )
        for admin_id in settings.admin_ids:
            try:
                if leave_request.telegram_file_id:
                    await bot.send_photo(
                        chat_id=admin_id,
                        photo=leave_request.telegram_file_id,
                        caption=text,
                        reply_markup=leave_review_keyboard(leave_request.id),
                    )
                else:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=text,
                        reply_markup=leave_review_keyboard(leave_request.id),
                    )
            except Exception:
                continue


async def notify_worker_review(bot: Bot, leave_request_id: int) -> None:
    async with session_scope() as session:
        leave_request = await get_leave_request(session, leave_request_id)
        if not leave_request:
            return
        try:
            await bot.send_message(
                chat_id=leave_request.worker.telegram_user_id,
                text=build_leave_review_text(
                    leave_request.id,
                    leave_request.leave_type,
                    leave_request.start_date,
                    leave_request.end_date,
                    leave_request.status,
                ),
            )
        except Exception:
            return


async def _submit_leave_request(
    message: Message,
    state: FSMContext,
    telegram_file_id: Optional[str] = None,
) -> None:
    data = await state.get_data()
    async with session_scope() as session:
        worker = await get_worker_by_telegram_id(session, message.from_user.id)
        if not worker:
            await message.answer(registered_workers_only_text())
            await state.clear()
            return

        try:
            leave_request = await create_leave_request(
                session,
                worker=worker,
                leave_type=data["leave_type"],
                start_date=data["start_date"],
                end_date=data["end_date"],
                reason=data["reason"],
                telegram_file_id=telegram_file_id,
            )
        except LeaveError as exc:
            await message.answer(str(exc))
            await state.clear()
            return

    await message.answer(
        build_leave_summary_text(
            leave_request.id,
            worker.full_name,
            leave_request.leave_type,
            leave_request.start_date,
            leave_request.end_date,
            leave_request.reason,
        )
        + "\nStatus: PENDING"
    )
    await _notify_admins(message.bot, leave_request.id)
    await state.clear()


@router.callback_query(F.data == "leave:start")
async def start_leave_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    worker = await load_registered_worker(callback.from_user.id)
    if not worker:
        await callback.message.answer(registered_workers_only_text())
        return
    if not worker_chat_is_allowed(worker, callback):
        await callback.message.answer(leave_restriction_text())
        return

    await state.clear()
    await state.set_state(LeaveApplicationStates.leave_type)
    await callback.message.answer("Choose the leave type.", reply_markup=leave_type_keyboard())


@router.callback_query(F.data.startswith("leave:type:"))
async def pick_leave_type(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    leave_type = callback.data.split(":")[-1]
    if not is_supported_leave_type(leave_type):
        await callback.message.answer("Unsupported leave type.")
        return

    await state.update_data(leave_type=leave_type)
    await state.set_state(LeaveApplicationStates.start_date)
    await callback.message.answer(
        f"{leave_label(leave_type)} selected.\nSend the start date in YYYY-MM-DD or DD/MM/YYYY format."
    )


@router.message(LeaveApplicationStates.start_date)
async def capture_start_date(message: Message, state: FSMContext) -> None:
    try:
        start_date = parse_user_date(message.text or "")
    except ValueError as exc:
        await message.answer(str(exc))
        return

    await state.update_data(start_date=start_date)
    await state.set_state(LeaveApplicationStates.end_date)
    await message.answer("Now send the end date in YYYY-MM-DD or DD/MM/YYYY format.")


@router.message(LeaveApplicationStates.end_date)
async def capture_end_date(message: Message, state: FSMContext) -> None:
    try:
        end_date = parse_user_date(message.text or "")
    except ValueError as exc:
        await message.answer(str(exc))
        return

    data = await state.get_data()
    if end_date < data["start_date"]:
        await message.answer("End date cannot be earlier than start date.")
        return

    await state.update_data(end_date=end_date)
    await state.set_state(LeaveApplicationStates.reason)
    await message.answer("Send a short reason for the leave.")


@router.message(LeaveApplicationStates.reason)
async def capture_reason(message: Message, state: FSMContext) -> None:
    reason = (message.text or "").strip()
    if not reason:
        await message.answer("A reason is required.")
        return

    data = await state.get_data()
    await state.update_data(reason=reason)
    if data["leave_type"] in {"mc", "emergency"}:
        await state.set_state(LeaveApplicationStates.photo)
        await message.answer("Upload the supporting photo now. Only the Telegram file_id will be saved.")
        return

    await _submit_leave_request(message, state)


@router.message(LeaveApplicationStates.photo, F.photo)
async def capture_photo(message: Message, state: FSMContext) -> None:
    file_id = message.photo[-1].file_id
    await _submit_leave_request(message, state, telegram_file_id=file_id)


@router.message(LeaveApplicationStates.photo)
async def prompt_photo_again(message: Message) -> None:
    await message.answer("A photo is required for MC and Emergency Leave. Please upload an image.")
