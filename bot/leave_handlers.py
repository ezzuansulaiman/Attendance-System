from __future__ import annotations

import logging
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ForceReply, Message

from bot.context import (
    inactive_worker_text,
    leave_restriction_text,
    load_worker_access,
    local_tz,
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
    leave_quick_end_date_keyboard,
    leave_quick_start_date_keyboard,
    leave_reason_keyboard,
    leave_type_keyboard,
    worker_menu_keyboard,
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
        "Ok, permohonan cuti dibatalkan.",
        reply_markup=worker_menu_keyboard(),
    )


async def _show_leave_type_prompt(target: Message, *, editing: bool = False) -> None:
    intro = "Pilih jenis cuti:" if not editing else "Ok, pilih jenis cuti semula:"
    await target.answer(intro, reply_markup=leave_type_keyboard(cancel_callback=LEAVE_CANCEL_CALLBACK))


async def _show_leave_day_portion_prompt(target: Message) -> None:
    await target.answer(
        "Sehari penuh atau separuh hari?",
        reply_markup=leave_day_portion_keyboard(
            back_callback=LEAVE_BACK_CALLBACK,
            cancel_callback=LEAVE_CANCEL_CALLBACK,
        ),
    )


async def _prompt_for_reply(target: Message, label: str, placeholder: str = "") -> None:
    """Send a ForceReply message so users in groups with privacy mode ON can reply with text/photo."""
    await target.answer(label, reply_markup=ForceReply(selective=True, input_field_placeholder=placeholder))


def _uses_quick_date_picker(leave_type: str) -> bool:
    """MC and Emergency use inline date buttons; Annual uses free-text date entry."""
    return leave_type in ("mc", "emergency")


_QUICK_REASONS: dict[str, str] = {
    "sakit": "Sakit / Demam",
    "kemalangan": "Kemalangan",
    "urusan": "Urusan peribadi",
    "kecemasan": "Kecemasan keluarga",
}


async def _show_start_date_prompt(target: Message, *, leave_type: str, editing: bool = False) -> None:
    if _uses_quick_date_picker(leave_type):
        prompt = "Pilih tarikh mula:" if not editing else "Pilih semula tarikh mula:"
        await target.answer(
            prompt,
            reply_markup=leave_quick_start_date_keyboard(
                back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK
            ),
        )
    else:
        lines: list[str] = []
        if leave_type == "annual" and not editing:
            lines.append(annual_leave_notice_text())
        lines.append(
            "Hantar tarikh mula — boleh guna format 17/04/2026 atau 2026-04-17."
            if not editing
            else "Hantar semula tarikh mula — format: 17/04/2026 atau 2026-04-17."
        )
        await target.answer(
            "\n".join(lines),
            reply_markup=flow_control_keyboard(
                back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK
            ),
        )
        await _prompt_for_reply(target, "Tarikh mula:", "cth: 17/04/2026")


async def _show_end_date_prompt(target: Message, *, leave_type: str, editing: bool = False) -> None:
    if _uses_quick_date_picker(leave_type):
        prompt = "Pilih tarikh akhir:" if not editing else "Pilih semula tarikh akhir:"
        await target.answer(
            prompt,
            reply_markup=leave_quick_end_date_keyboard(
                back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK
            ),
        )
    else:
        await target.answer(
            "Hantar tarikh akhir — boleh guna format 17/04/2026 atau 2026-04-17."
            if not editing
            else "Hantar semula tarikh akhir — format: 17/04/2026 atau 2026-04-17.",
            reply_markup=flow_control_keyboard(
                back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK
            ),
        )
        await _prompt_for_reply(target, "Tarikh akhir:", "cth: 17/04/2026")


async def _show_reason_prompt(target: Message, *, editing: bool = False) -> None:
    prompt = "Pilih atau taip sebab cuti:" if not editing else "Pilih atau taip semula sebab cuti:"
    await target.answer(
        prompt,
        reply_markup=leave_reason_keyboard(
            back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK
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
    # Phase 1: write to database — if this fails, nothing was committed and the user can retry.
    try:
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
    except Exception as exc:
        logger.exception(
            "DB error submitting leave request for user %s: %s: %s",
            telegram_user_id, type(exc).__name__, exc,
        )
        await message.answer(
            f"Ada masalah sistem masa nak hantar permohonan ({type(exc).__name__}). Cuba lagi atau hubungi admin."
        )
        return

    # Phase 2: notify — best-effort; leave request is already committed above.
    await state.clear()
    try:
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
    except Exception:
        logger.exception("Failed to send leave submission confirmation to user %s", telegram_user_id)

    try:
        await send_leave_request_to_admins(bot, leave_request.id)
    except Exception:
        logger.exception("Failed to send leave %s admin notifications", leave_request.id)


async def _step_back_in_leave_flow(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    data = await state.get_data()

    if current_state == LeaveApplicationStates.start_date.state:
        await state.set_state(LeaveApplicationStates.leave_type)
        await _show_leave_type_prompt(message, editing=True)
        return

    if current_state == LeaveApplicationStates.end_date.state:
        await state.set_state(LeaveApplicationStates.start_date)
        await _show_start_date_prompt(message, leave_type=data.get("leave_type", ""), editing=True)
        return

    if current_state == LeaveApplicationStates.day_portion.state:
        await state.set_state(LeaveApplicationStates.end_date)
        await _show_end_date_prompt(message, leave_type=data.get("leave_type", ""), editing=True)
        return

    if current_state == LeaveApplicationStates.reason.state:
        if data.get("start_date") == data.get("end_date"):
            await state.set_state(LeaveApplicationStates.day_portion)
            await _show_leave_day_portion_prompt(message)
            return
        await state.set_state(LeaveApplicationStates.end_date)
        await _show_end_date_prompt(message, leave_type=data.get("leave_type", ""), editing=True)
        return

    if current_state == LeaveApplicationStates.photo.state:
        await state.set_state(LeaveApplicationStates.reason)
        await _show_reason_prompt(message, editing=True)
        return

    if current_state == LeaveApplicationStates.confirmation.state:
        if leave_requires_photo(data.get("leave_type", "")):
            await state.set_state(LeaveApplicationStates.photo)
            await message.answer(
                "Muat naik semula gambar sokongan. Bukti ni akan dihantar ke group site.",
                reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
            )
            await _prompt_for_reply(message, "Muat naik gambar sokongan di sini:", "lampirkan foto MC / surat doktor")
            return
        await state.set_state(LeaveApplicationStates.reason)
        await _show_reason_prompt(message, editing=True)
        return

    await message.answer("Dah kat langkah pertama. Pilih jenis cuti atau tekan Batal.")


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
            "Permohonan cuti mesti dibuat dalam group Telegram site anda. Guna group tersebut untuk mohon cuti."
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
            await callback.answer("Cuti mesti dipohon dalam group Telegram site anda.", show_alert=True)
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
    await callback.message.answer(f"Jenis cuti dipilih: {leave_label(leave_type)}.")
    await _show_start_date_prompt(callback.message, leave_type=leave_type)


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
            + f"\nTarikh terawal yang boleh dipilih ialah <b>{format_display_date(earliest)}</b>.\n"
            "Cuba hantar semula tarikh mula."
        )
        return

    data = await state.get_data()
    await state.update_data(start_date=start_date)
    await state.set_state(LeaveApplicationStates.end_date)
    await _show_end_date_prompt(message, leave_type=data.get("leave_type", ""))


@router.callback_query(F.data.startswith("leave:startdate:"))
async def pick_start_date_quick(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state != LeaveApplicationStates.start_date.state:
        if _in_leave_flow(current_state):
            await callback.answer("Ikut langkah semasa atau tekan Kembali untuk tukar.")
        else:
            await callback.answer("Tiada permohonan aktif. Tekan 'Mohon Cuti' untuk mula.")
        return

    offsets = {"today": 0, "tomorrow": 1, "yesterday": -1}
    key = callback.data.split(":")[-1]
    if key not in offsets:
        await callback.answer()
        return
    await callback.answer()
    start_date = datetime.now(local_tz).date() + timedelta(days=offsets[key])
    data = await state.get_data()
    await state.update_data(start_date=start_date)
    await state.set_state(LeaveApplicationStates.end_date)
    await callback.message.answer(f"Tarikh mula dipilih: {format_display_date(start_date)}.")
    await _show_end_date_prompt(callback.message, leave_type=data.get("leave_type", ""))


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
    await _show_reason_prompt(message)


@router.callback_query(F.data.startswith("leave:enddate:"))
async def pick_end_date_quick(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state != LeaveApplicationStates.end_date.state:
        if _in_leave_flow(current_state):
            await callback.answer("Ikut langkah semasa atau tekan Kembali untuk tukar.")
        else:
            await callback.answer("Tiada permohonan aktif. Tekan 'Mohon Cuti' untuk mula.")
        return

    await callback.answer()
    data = await state.get_data()
    key = callback.data.split(":")[-1]
    today = datetime.now(local_tz).date()

    if key == "same":
        end_date = data["start_date"]
    elif key == "today":
        end_date = today
    elif key == "tomorrow":
        end_date = today + timedelta(days=1)
    else:
        return

    if end_date < data["start_date"]:
        await callback.message.answer(
            f"Tarikh akhir ({format_display_date(end_date)}) tidak boleh lebih awal daripada "
            f"tarikh mula ({format_display_date(data['start_date'])})."
        )
        return

    await state.update_data(end_date=end_date)
    if end_date == data["start_date"]:
        await state.set_state(LeaveApplicationStates.day_portion)
        await _show_leave_day_portion_prompt(callback.message)
        return

    await state.update_data(day_portion="full")
    await state.set_state(LeaveApplicationStates.reason)
    await _show_reason_prompt(callback.message)


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
            await callback.answer("Tekan Kembali dahulu untuk tukar pilihan ni.")
        else:
            await callback.answer("Tiada permohonan aktif. Tekan 'Mohon Cuti' untuk mula.")
        return

    await callback.answer()
    day_portion = callback.data.split(":")[-1]
    if not is_supported_leave_day_portion(day_portion):
        await callback.message.answer("Pilihan bahagian hari ini tidak disokong.")
        return

    await state.update_data(day_portion=day_portion)
    await state.set_state(LeaveApplicationStates.reason)
    await _show_reason_prompt(callback.message)


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


@router.callback_query(F.data.startswith("leave:reason:"))
async def pick_reason_quick(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state != LeaveApplicationStates.reason.state:
        if _in_leave_flow(current_state):
            await callback.answer("Ikut langkah semasa atau tekan Kembali untuk tukar.")
        else:
            await callback.answer("Tiada permohonan aktif. Tekan 'Mohon Cuti' untuk mula.")
        return

    key = callback.data.split(":")[-1]
    if key == "other":
        await callback.answer()
        await _prompt_for_reply(callback.message, "Tulis sebab cuti anda:", "cth: Demam, Kemalangan...")
        return

    reason = _QUICK_REASONS.get(key)
    if not reason:
        await callback.answer()
        return

    await callback.answer()
    await state.update_data(reason=reason)
    data = await state.get_data()
    if leave_requires_photo(data["leave_type"]):
        await state.set_state(LeaveApplicationStates.photo)
        photo_prompt = (
            "Muat naik gambar sokongan sekarang. "
            "Bukti ni akan dihantar ke group site."
        )
        if data.get("group_delivery_unavailable"):
            photo_prompt = (
                "Muat naik gambar sokongan sekarang. "
                "Akan dihantar ke admin dulu sebab group site belum dikonfigurasi."
            )
        await callback.message.answer(
            photo_prompt,
            reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
        )
        await _prompt_for_reply(callback.message, "Muat naik gambar sokongan di sini:", "lampirkan foto MC / surat doktor")
        return

    await _show_leave_confirmation(callback.message, state, telegram_user_id=callback.from_user.id)


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
        await message.answer("Kena isi sebab cuti.")
        return

    data = await state.get_data()
    await state.update_data(reason=reason)
    if leave_requires_photo(data["leave_type"]):
        await state.set_state(LeaveApplicationStates.photo)
        photo_prompt = (
            "Muat naik gambar sokongan sekarang. "
            "Bukti ni akan dihantar ke group site."
        )
        if data.get("group_delivery_unavailable"):
            photo_prompt = (
                "Muat naik gambar sokongan sekarang. "
                "Akan dihantar ke admin dulu sebab group site belum dikonfigurasi."
            )
        await message.answer(
            photo_prompt,
            reply_markup=flow_control_keyboard(back_callback=LEAVE_BACK_CALLBACK, cancel_callback=LEAVE_CANCEL_CALLBACK),
        )
        await _prompt_for_reply(message, "Muat naik gambar sokongan di sini:", "lampirkan foto MC / surat doktor")
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
        "Kena muat naik gambar sokongan untuk jenis cuti ini. "
        "Lampirkan foto MC atau surat doktor."
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
            await callback.answer("Lengkapkan borang cuti dulu.")
        else:
            await callback.answer("Tiada permohonan aktif. Tekan 'Mohon Cuti' untuk mula.")
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
        await callback.answer("Tiada permohonan aktif. Tekan 'Mohon Cuti' untuk mula.")
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
