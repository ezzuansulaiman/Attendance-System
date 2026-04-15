from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.context import (
    inactive_worker_text,
    leave_restriction_text,
    load_worker_access,
    registered_workers_only_text,
    worker_group_id,
    worker_chat_is_allowed,
)
from bot.keyboards import (
    confirmation_keyboard,
    flow_control_keyboard,
    is_back_alias,
    is_cancel_alias,
    leave_day_portion_keyboard,
    worker_menu_keyboard,
    leave_type_keyboard,
)
from bot.messages import build_leave_confirmation_text, build_leave_summary_text, parse_user_date
from bot.notifications import send_leave_request_to_admins
from bot.states import LeaveApplicationStates
from models import session_scope
from services.attendance_service import get_worker_by_telegram_id
from services.leave_service import (
    LeaveError,
    annual_leave_notice_text,
    create_leave_request,
    is_supported_leave_day_portion,
    is_supported_leave_type,
    leave_label,
    leave_requires_photo,
)

router = Router()
LEAVE_BACK_CALLBACK = "leave:back"
LEAVE_CANCEL_CALLBACK = "leave:cancel"


async def _submit_leave_request(message: Message, state: FSMContext, bot: Bot, *, telegram_user_id: int) -> None:
    data = await state.get_data()
    async with session_scope() as session:
        worker = await get_worker_by_telegram_id(session, telegram_user_id, active_only=False)
        if not worker:
            await message.answer(registered_workers_only_text())
            await state.clear()
            return
        if worker.is_active is False:
            await message.answer(inactive_worker_text())
            await state.clear()
            return

        try:
            leave_request = await create_leave_request(
                session,
                worker=worker,
                leave_type=data["leave_type"],
                start_date=data["start_date"],
                end_date=data["end_date"],
                day_portion=data.get("day_portion"),
                reason=data["reason"],
                telegram_file_id=data.get("telegram_file_id"),
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
            leave_request.day_portion,
            leave_request.reason,
        )
        + "\nStatus: DALAM SEMAKAN"
    )
    await send_leave_request_to_admins(bot, leave_request.id)
    await state.clear()


async def _show_leave_type_prompt(target: Message, *, editing: bool = False) -> None:
    intro = "Sila pilih jenis cuti." if not editing else "Baik, sila pilih semula jenis cuti."
    await target.answer(intro, reply_markup=leave_type_keyboard(cancel_callback=LEAVE_CANCEL_CALLBACK))


async def _show_leave_day_portion_prompt(target: Message) -> None:
    await target.answer(
        "Sila pilih sama ada cuti ini sehari penuh atau separuh hari.",
        reply_markup=leave_day_portion_keyboard(
            back_callback=LEAVE_BACK_CALLBACK,
            cancel_callback=LEAVE_CANCEL_CALLBACK,
        ),
    )


def _required_group_support_text() -> str:
    return (
        "Cuti Sakit dan Cuti Kecemasan memerlukan bukti sokongan di group site bersama alasan. "
        "Sila hubungi admin jika group Telegram site anda belum ditetapkan."
    )


async def _show_leave_confirmation(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    async with session_scope() as session:
        worker = await get_worker_by_telegram_id(session, message.from_user.id, active_only=False)
    if not worker:
        await message.answer(registered_workers_only_text())
        await state.clear()
        return
    if worker.is_active is False:
        await message.answer(inactive_worker_text())
        await state.clear()
        return

    await state.set_state(LeaveApplicationStates.confirmation)
    await message.answer(
        build_leave_confirmation_text(
            worker_name=worker.full_name,
            leave_type=data["leave_type"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            day_portion=data.get("day_portion"),
            reason=data["reason"],
            has_supporting_photo=bool(data.get("telegram_file_id")),
        ),
        reply_markup=confirmation_keyboard(
            confirm_callback="leave:confirm",
            back_callback=LEAVE_BACK_CALLBACK,
            cancel_callback=LEAVE_CANCEL_CALLBACK,
        ),
    )


async def _cancel_leave_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Permohonan cuti dibatalkan. Anda boleh kembali ke menu pekerja.", reply_markup=worker_menu_keyboard())


async def _step_back_in_leave_flow(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    data = await state.get_data()

    if current_state == LeaveApplicationStates.start_date.state:
        await state.set_state(LeaveApplicationStates.leave_type)
        await _show_leave_type_prompt(message, editing=True)
        return
    if current_state == LeaveApplicationStates.end_date.state:
        await state.set_state(LeaveApplicationStates.start_date)
        await message.answer(
            "Sila hantar semula tarikh mula dalam format YYYY-MM-DD atau DD/MM/YYYY.",
            reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
        )
        return
    if current_state == LeaveApplicationStates.day_portion.state:
        await state.set_state(LeaveApplicationStates.end_date)
        await message.answer(
            "Sila hantar semula tarikh akhir dalam format YYYY-MM-DD atau DD/MM/YYYY.",
            reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
        )
        return
    if current_state == LeaveApplicationStates.reason.state:
        if data.get("start_date") == data.get("end_date"):
            await state.set_state(LeaveApplicationStates.day_portion)
            await _show_leave_day_portion_prompt(message)
            return
        await state.set_state(LeaveApplicationStates.end_date)
        await message.answer(
            "Sila hantar semula tarikh akhir dalam format YYYY-MM-DD atau DD/MM/YYYY.",
            reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
        )
        return
    if current_state == LeaveApplicationStates.photo.state:
        await state.set_state(LeaveApplicationStates.reason)
        await message.answer(
            "Sila hantar semula sebab ringkas bagi permohonan cuti ini.",
            reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
        )
        return
    if current_state == LeaveApplicationStates.confirmation.state:
        if leave_requires_photo(data.get("leave_type", "")):
            await state.set_state(LeaveApplicationStates.photo)
            await message.answer(
                "Sila muat naik semula gambar sokongan. Bukti ini akan dihantar ke group site bersama alasan.",
                reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
            )
            return
        await state.set_state(LeaveApplicationStates.reason)
        await message.answer(
            "Sila hantar semula sebab ringkas bagi permohonan cuti ini.",
            reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
        )
        return

    await message.answer("Anda sudah berada di langkah pertama. Tekan jenis cuti atau pilih Batal.")


@router.callback_query(F.data == "leave:start")
async def start_leave_flow(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
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

    if callback.message.chat.type in {"group", "supergroup"}:
        bot_info = await bot.get_me()
        deep_link_url = f"https://t.me/{bot_info.username}?start=leave"
        await callback.message.answer(
            "Sila mohon cuti melalui chat peribadi bot untuk memastikan privasi maklumat anda.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Mohon Cuti Sekarang", url=deep_link_url)]]
            ),
        )
        return

    await state.clear()
    await state.set_state(LeaveApplicationStates.leave_type)
    await _show_leave_type_prompt(callback.message)


@router.callback_query(F.data.startswith("leave:type:"))
async def pick_leave_type(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    leave_type = callback.data.split(":")[-1]
    if not is_supported_leave_type(leave_type):
        await callback.message.answer("Jenis cuti ini tidak disokong.")
        return
    if leave_requires_photo(leave_type):
        worker_access = await load_worker_access(callback.from_user.id)
        if worker_access.is_inactive:
            await callback.message.answer(inactive_worker_text())
            await state.clear()
            return
        worker = worker_access.worker
        if not worker:
            await callback.message.answer(registered_workers_only_text())
            await state.clear()
            return
        if worker_group_id(worker) is None:
            await callback.message.answer(_required_group_support_text())
            await state.clear()
            return

    await state.update_data(leave_type=leave_type)
    await state.set_state(LeaveApplicationStates.start_date)
    prompt_lines = [f"Jenis cuti dipilih: {leave_label(leave_type)}."]
    if leave_type == "annual":
        prompt_lines.append(annual_leave_notice_text())
    prompt_lines.append("Sila hantar tarikh mula dalam format YYYY-MM-DD atau DD/MM/YYYY.")
    await callback.message.answer(
        "\n".join(prompt_lines),
        reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
    )


@router.message(LeaveApplicationStates.start_date)
async def capture_start_date(message: Message, state: FSMContext) -> None:
    if is_cancel_alias(message.text):
        await _cancel_leave_flow(message, state)
        return
    if is_back_alias(message.text):
        await _step_back_in_leave_flow(message, state)
        return

    try:
        start_date = parse_user_date(message.text or "")
    except ValueError as exc:
        await message.answer(str(exc))
        return

    await state.update_data(start_date=start_date)
    await state.set_state(LeaveApplicationStates.end_date)
    await message.answer(
        "Baik, sekarang sila hantar tarikh akhir dalam format YYYY-MM-DD atau DD/MM/YYYY.",
        reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
    )


@router.message(LeaveApplicationStates.end_date)
async def capture_end_date(message: Message, state: FSMContext) -> None:
    if is_cancel_alias(message.text):
        await _cancel_leave_flow(message, state)
        return
    if is_back_alias(message.text):
        await _step_back_in_leave_flow(message, state)
        return

    try:
        end_date = parse_user_date(message.text or "")
    except ValueError as exc:
        await message.answer(str(exc))
        return

    data = await state.get_data()
    if end_date < data["start_date"]:
        await message.answer("Tarikh akhir tidak boleh lebih awal daripada tarikh mula.")
        return

    await state.update_data(end_date=end_date)
    if end_date == data["start_date"]:
        await state.set_state(LeaveApplicationStates.day_portion)
        await _show_leave_day_portion_prompt(message)
        return

    await state.update_data(day_portion="full")
    await state.set_state(LeaveApplicationStates.reason)
    await message.answer(
        "Sila hantar sebab ringkas bagi permohonan cuti ini.",
        reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
    )


@router.callback_query(F.data.startswith("leave:portion:"))
async def pick_leave_day_portion(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    day_portion = callback.data.split(":")[-1]
    if not is_supported_leave_day_portion(day_portion):
        await callback.message.answer("Pilihan bahagian hari ini tidak disokong.")
        return

    await state.update_data(day_portion=day_portion)
    await state.set_state(LeaveApplicationStates.reason)
    await callback.message.answer(
        "Sila hantar sebab ringkas bagi permohonan cuti ini.",
        reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
    )


@router.message(LeaveApplicationStates.reason)
async def capture_reason(message: Message, state: FSMContext) -> None:
    if is_cancel_alias(message.text):
        await _cancel_leave_flow(message, state)
        return
    if is_back_alias(message.text):
        await _step_back_in_leave_flow(message, state)
        return

    reason = (message.text or "").strip()
    if not reason:
        await message.answer("Sebab permohonan cuti diperlukan.")
        return

    data = await state.get_data()
    await state.update_data(reason=reason)
    if leave_requires_photo(data["leave_type"]):
        await state.set_state(LeaveApplicationStates.photo)
        await message.answer(
            "Sila muat naik gambar sokongan sekarang. Bukti ini akan dihantar ke group site bersama alasan.",
            reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
        )
        return

    await _show_leave_confirmation(message, state)


@router.message(LeaveApplicationStates.photo, F.photo)
async def capture_photo(message: Message, state: FSMContext) -> None:
    file_id = message.photo[-1].file_id
    await state.update_data(telegram_file_id=file_id)
    await _show_leave_confirmation(message, state)


@router.message(LeaveApplicationStates.photo)
async def prompt_photo_again(message: Message, state: FSMContext) -> None:
    if is_cancel_alias(message.text):
        await _cancel_leave_flow(message, state)
        return
    if is_back_alias(message.text):
        await _step_back_in_leave_flow(message, state)
        return
    await message.answer(
        "Gambar sokongan diperlukan untuk Cuti Sakit dan Cuti Kecemasan. "
        "Sila muat naik imej supaya bukti boleh dilampirkan ke group site bersama alasan."
    )


@router.callback_query(F.data == "leave:confirm")
async def confirm_leave_request(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if await state.get_state() != LeaveApplicationStates.confirmation.state:
        await callback.answer(
            "Permohonan ini sudah tidak aktif. Sila mulakan semula dari menu.",
            show_alert=True,
        )
        return
    await callback.answer()
    await _submit_leave_request(callback.message, state, bot, telegram_user_id=callback.from_user.id)


@router.callback_query(F.data == LEAVE_BACK_CALLBACK)
async def handle_leave_back_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _step_back_in_leave_flow(callback.message, state)


@router.callback_query(F.data == LEAVE_CANCEL_CALLBACK)
async def handle_leave_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _cancel_leave_flow(callback.message, state)


@router.message(LeaveApplicationStates.leave_type, F.text.func(is_cancel_alias))
@router.message(LeaveApplicationStates.start_date, F.text.func(is_cancel_alias))
@router.message(LeaveApplicationStates.end_date, F.text.func(is_cancel_alias))
@router.message(LeaveApplicationStates.day_portion, F.text.func(is_cancel_alias))
@router.message(LeaveApplicationStates.reason, F.text.func(is_cancel_alias))
@router.message(LeaveApplicationStates.photo, F.text.func(is_cancel_alias))
@router.message(LeaveApplicationStates.confirmation, F.text.func(is_cancel_alias))
async def cancel_leave_from_text(message: Message, state: FSMContext) -> None:
    await _cancel_leave_flow(message, state)


@router.message(LeaveApplicationStates.leave_type, F.text.func(is_back_alias))
@router.message(LeaveApplicationStates.start_date, F.text.func(is_back_alias))
@router.message(LeaveApplicationStates.end_date, F.text.func(is_back_alias))
@router.message(LeaveApplicationStates.day_portion, F.text.func(is_back_alias))
@router.message(LeaveApplicationStates.reason, F.text.func(is_back_alias))
@router.message(LeaveApplicationStates.photo, F.text.func(is_back_alias))
@router.message(LeaveApplicationStates.confirmation, F.text.func(is_back_alias))
async def go_back_in_leave_from_text(message: Message, state: FSMContext) -> None:
    await _step_back_in_leave_flow(message, state)


@router.message(LeaveApplicationStates.day_portion)
async def prompt_leave_day_portion_again(message: Message, state: FSMContext) -> None:
    if is_cancel_alias(message.text):
        await _cancel_leave_flow(message, state)
        return
    if is_back_alias(message.text):
        await _step_back_in_leave_flow(message, state)
        return
    await _show_leave_day_portion_prompt(message)
