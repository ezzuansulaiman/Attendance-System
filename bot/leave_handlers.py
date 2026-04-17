from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.context import (
    inactive_worker_text,
    leave_restriction_text,
    load_worker_access,
    registered_workers_only_text,
    worker_chat_is_allowed,
    worker_group_id,
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
from bot.messages import build_leave_confirmation_text, build_leave_summary_text, format_display_date, parse_user_date
from bot.notifications import send_leave_request_to_admins
from bot.states import LeaveApplicationStates
from models import session_scope
from services.attendance_service import get_worker_by_telegram_id
from services.leave_service import (
    LeaveError,
    annual_leave_earliest_start_date,
    annual_leave_notice_met,
    annual_leave_notice_text,
    create_leave_request,
    is_supported_leave_day_portion,
    is_supported_leave_type,
    leave_label,
    leave_requires_photo,
)

router = Router()
logger = logging.getLogger(__name__)
LEAVE_BACK_CALLBACK = "leave:back"
LEAVE_CANCEL_CALLBACK = "leave:cancel"


async def _log_leave_block(reason_code: str, *, telegram_user_id: int, chat_type: str) -> None:
    logger.info(
        "leave_apply_blocked reason=%s telegram_user_id=%s chat_type=%s",
        reason_code,
        telegram_user_id,
        chat_type,
    )


def _classify_leave_error_reason(error_message: str) -> str:
    normalized = error_message.lower()
    if "bertindih" in normalized:
        return "overlap_existing_leave"
    if "gambar sokongan" in normalized:
        return "missing_supporting_photo"
    if "sekurang-kurangnya" in normalized:
        return "annual_notice_failed"
    if "tarikh akhir" in normalized:
        return "invalid_date_range"
    if "bahagian hari" in normalized:
        return "invalid_day_portion"
    return "service_validation_failed"


def _in_leave_flow(state: str | None) -> bool:
    """Return True if the user currently has an active leave application flow."""
    return state is not None and state.startswith("LeaveApplicationStates:")


async def _cancel_leave_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Permohonan cuti dibatalkan. Anda boleh kembali ke menu pekerja.",
        reply_markup=worker_menu_keyboard(),
    )


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


def _group_not_configured_notice_text() -> str:
    return (
        "Group Telegram site anda belum ditetapkan. "
        "Permohonan Cuti Sakit atau Cuti Kecemasan masih boleh dihantar, "
        "tetapi bukti hanya akan dihantar kepada admin sehingga group site disediakan."
    )


async def _show_leave_confirmation(message: Message, state: FSMContext, *, telegram_user_id: int) -> None:
    data = await state.get_data()
    async with session_scope() as session:
        worker = await get_worker_by_telegram_id(session, telegram_user_id, active_only=False)
    if not worker:
        _log_leave_block("worker_not_registered", telegram_user_id=telegram_user_id, chat_type=message.chat.type)
        await message.answer(registered_workers_only_text())
        await state.clear()
        return
    if worker.is_active is False:
        _log_leave_block("worker_inactive", telegram_user_id=telegram_user_id, chat_type=message.chat.type)
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


async def _submit_leave_request(message: Message, state: FSMContext, bot: Bot, *, telegram_user_id: int) -> None:
    data = await state.get_data()
    async with session_scope() as session:
        worker = await get_worker_by_telegram_id(session, telegram_user_id, active_only=False)
        if not worker:
            _log_leave_block("worker_not_registered", telegram_user_id=telegram_user_id, chat_type=message.chat.type)
            await message.answer(registered_workers_only_text())
            await state.clear()
            return
        if worker.is_active is False:
            _log_leave_block("worker_inactive", telegram_user_id=telegram_user_id, chat_type=message.chat.type)
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
            _log_leave_block(
                _classify_leave_error_reason(str(exc)),
                telegram_user_id=telegram_user_id,
                chat_type=message.chat.type,
            )
            # Keep state alive so the user can press Back to fix the issue instead of starting over
            await message.answer(
                str(exc) + "\n\nTekan <b>Kembali</b> untuk tukar maklumat atau <b>Batal</b> untuk keluar.",
                reply_markup=confirmation_keyboard(
                    confirm_callback="leave:confirm",
                    back_callback=LEAVE_BACK_CALLBACK,
                    cancel_callback=LEAVE_CANCEL_CALLBACK,
                ),
            )
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

    await message.answer("Anda sudah berada di langkah pertama. Sila pilih jenis cuti atau tekan Batal.")


# ---------------------------------------------------------------------------
# Flow entry point
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "leave:start")
async def start_leave_flow(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    worker_access = await load_worker_access(callback.from_user.id)
    if worker_access.is_inactive:
        _log_leave_block("worker_inactive", telegram_user_id=callback.from_user.id, chat_type=callback.message.chat.type)
        await callback.message.answer(inactive_worker_text())
        return
    worker = worker_access.worker
    if not worker:
        _log_leave_block(
            "worker_not_registered",
            telegram_user_id=callback.from_user.id,
            chat_type=callback.message.chat.type,
        )
        await callback.message.answer(registered_workers_only_text())
        return
    if not worker_chat_is_allowed(worker, callback):
        _log_leave_block(
            "chat_not_allowed",
            telegram_user_id=callback.from_user.id,
            chat_type=callback.message.chat.type,
        )
        await callback.message.answer(
            "Permohonan cuti hanya boleh dibuat dalam kumpulan Telegram site anda. Sila gunakan group ini untuk memohon cuti."
        )
        return

    # Sekarang kita sudah dalam group yang dibenarkan, teruskan flow permohonan cuti
    await state.clear()
    await state.set_state(LeaveApplicationStates.leave_type)
    await _show_leave_type_prompt(callback.message)


# ---------------------------------------------------------------------------
# Step 1 — pick leave type
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("leave:type:"))
async def pick_leave_type(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()

    worker_access = await load_worker_access(callback.from_user.id)
    if worker_access.is_inactive:
        await callback.answer("Akaun anda tidak aktif.", show_alert=True)
        return
    worker = worker_access.worker
    if not worker:
        await callback.answer("Anda belum berdaftar sebagai pekerja.", show_alert=True)
        return

    # If there is no active leave flow (state is None or some other flow like registration),
    # re-check the group restriction before restarting cleanly.
    if not _in_leave_flow(current_state):
        if not worker_chat_is_allowed(worker, callback):
            await callback.answer("Permohonan cuti hanya boleh dibuat dalam kumpulan Telegram site anda.", show_alert=True)
            return
        await state.clear()
        await state.set_state(LeaveApplicationStates.leave_type)
    elif current_state != LeaveApplicationStates.leave_type.state:
        # User is deeper in the leave flow and clicked a type button — restart with new type.
        await state.clear()
        await state.set_state(LeaveApplicationStates.leave_type)

    await callback.answer()
    leave_type = callback.data.split(":")[-1]
    if not is_supported_leave_type(leave_type):
        await callback.message.answer("Jenis cuti ini tidak disokong.")
        return

    if leave_requires_photo(leave_type):
        if worker_group_id(worker) is None:
            await callback.message.answer(_group_not_configured_notice_text())
            await state.update_data(group_delivery_unavailable=True)
        else:
            await state.update_data(group_delivery_unavailable=False)
    else:
        await state.update_data(group_delivery_unavailable=False)

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


# ---------------------------------------------------------------------------
# Step 2 — start date
# ---------------------------------------------------------------------------


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

    data = await state.get_data()
    if not annual_leave_notice_met(leave_type=data.get("leave_type", ""), start_date=start_date):
        _log_leave_block("annual_notice_failed", telegram_user_id=message.from_user.id, chat_type=message.chat.type)
        earliest = annual_leave_earliest_start_date()
        await message.answer(
            annual_leave_notice_text()
            + f"\nTarikh terawal yang dibenarkan ialah <b>{format_display_date(earliest)}</b>.\n"
            "Sila masukkan semula tarikh mula."
        )
        return

    await state.update_data(start_date=start_date)
    await state.set_state(LeaveApplicationStates.end_date)
    await message.answer(
        "Baik, sekarang sila hantar tarikh akhir dalam format YYYY-MM-DD atau DD/MM/YYYY.",
        reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
    )


# ---------------------------------------------------------------------------
# Step 3 — end date
# ---------------------------------------------------------------------------


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
        _log_leave_block("invalid_date_range", telegram_user_id=message.from_user.id, chat_type=message.chat.type)
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


# ---------------------------------------------------------------------------
# Step 4 — day portion (only shown when start == end date)
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("leave:portion:"))
async def pick_leave_day_portion(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()

    worker_access = await load_worker_access(callback.from_user.id)
    if worker_access.is_inactive:
        await callback.answer("Akaun anda tidak aktif.", show_alert=True)
        return
    if not worker_access.worker:
        await callback.answer("Anda belum berdaftar sebagai pekerja.", show_alert=True)
        return

    if current_state != LeaveApplicationStates.day_portion.state:
        # Soft toast only — never block with show_alert so the user is not disrupted.
        if _in_leave_flow(current_state):
            await callback.answer("Untuk tukar pilihan ini, tekan butang Kembali dahulu.")
        else:
            await callback.answer("Tiada permohonan aktif. Sila tekan 'Mohon Cuti' untuk mula.")
        return

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


@router.message(LeaveApplicationStates.day_portion)
async def prompt_leave_day_portion_again(message: Message, state: FSMContext) -> None:
    if is_cancel_alias(message.text):
        await _cancel_leave_flow(message, state)
        return
    if is_back_alias(message.text):
        await _step_back_in_leave_flow(message, state)
        return
    await _show_leave_day_portion_prompt(message)


# ---------------------------------------------------------------------------
# Step 5 — reason
# ---------------------------------------------------------------------------


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
        _log_leave_block("missing_reason", telegram_user_id=message.from_user.id, chat_type=message.chat.type)
        await message.answer("Sebab permohonan cuti diperlukan.")
        return

    data = await state.get_data()
    await state.update_data(reason=reason)
    if leave_requires_photo(data["leave_type"]):
        await state.set_state(LeaveApplicationStates.photo)
        photo_prompt = (
            "Sila muat naik gambar sokongan sekarang. "
            "Bukti ini akan dihantar ke group site bersama alasan."
        )
        if data.get("group_delivery_unavailable"):
            photo_prompt = (
                "Sila muat naik gambar sokongan sekarang. "
                "Bukti ini akan dihantar kepada admin dahulu kerana group site belum dikonfigurasi."
            )
        await message.answer(
            photo_prompt,
            reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
        )
        return

    await _show_leave_confirmation(message, state, telegram_user_id=message.from_user.id)


# ---------------------------------------------------------------------------
# Step 6 — supporting photo (MC / emergency only)
# ---------------------------------------------------------------------------


@router.message(LeaveApplicationStates.photo, F.photo)
async def capture_photo(message: Message, state: FSMContext) -> None:
    file_id = message.photo[-1].file_id
    await state.update_data(telegram_file_id=file_id)
    await _show_leave_confirmation(message, state, telegram_user_id=message.from_user.id)


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
        "Sila muat naik imej supaya bukti boleh dilampirkan bersama alasan."
    )


# ---------------------------------------------------------------------------
# Step 7 — confirmation and submission
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "leave:confirm")
async def confirm_leave_request(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    current_state = await state.get_state()

    worker_access = await load_worker_access(callback.from_user.id)
    if worker_access.is_inactive:
        await callback.answer("Akaun anda tidak aktif.", show_alert=True)
        return
    if not worker_access.worker:
        await callback.answer("Anda belum berdaftar sebagai pekerja.", show_alert=True)
        return

    if current_state != LeaveApplicationStates.confirmation.state:
        # Soft toast only — never a blocking popup.
        if _in_leave_flow(current_state):
            await callback.answer("Sila lengkapkan borang cuti terlebih dahulu.")
        else:
            await callback.answer("Tiada permohonan aktif. Sila tekan 'Mohon Cuti' untuk mula.")
        return

    await callback.answer()
    await _submit_leave_request(callback.message, state, bot, telegram_user_id=callback.from_user.id)


# ---------------------------------------------------------------------------
# Navigation — back and cancel callbacks
# ---------------------------------------------------------------------------


@router.callback_query(F.data == LEAVE_BACK_CALLBACK)
async def handle_leave_back_callback(callback: CallbackQuery, state: FSMContext) -> None:
    current = await state.get_state()
    if not _in_leave_flow(current):
        await callback.answer("Tiada permohonan aktif. Sila tekan 'Mohon Cuti' untuk mula.")
        return
    await callback.answer()
    await _step_back_in_leave_flow(callback.message, state)


@router.callback_query(F.data == LEAVE_CANCEL_CALLBACK)
async def handle_leave_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    current = await state.get_state()
    if not _in_leave_flow(current):
        await callback.answer("Tiada permohonan aktif untuk dibatalkan.")
        return
    await callback.answer()
    await _cancel_leave_flow(callback.message, state)


# ---------------------------------------------------------------------------
# Text-based cancel / back for all leave states
# ---------------------------------------------------------------------------


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
