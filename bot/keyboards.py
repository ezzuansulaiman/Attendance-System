from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

WORKER_MENU_BUTTON = "Menu Kehadiran"
ADMIN_MENU_BUTTON = "Menu Admin"


def normalize_menu_trigger(raw_text: Optional[str]) -> str:
    return " ".join((raw_text or "").split()).casefold()


def is_worker_menu_alias(raw_text: Optional[str]) -> bool:
    return normalize_menu_trigger(raw_text) == "menu"


def is_admin_menu_alias(raw_text: Optional[str]) -> bool:
    return normalize_menu_trigger(raw_text) == "admin"


def main_menu_keyboard(*, show_worker_menu: bool, show_admin_menu: bool) -> Optional[ReplyKeyboardMarkup]:
    keyboard_rows: list[list[KeyboardButton]] = []
    first_row: list[KeyboardButton] = []

    if show_worker_menu:
        first_row.append(KeyboardButton(text=WORKER_MENU_BUTTON))
    if show_admin_menu:
        first_row.append(KeyboardButton(text=ADMIN_MENU_BUTTON))
    if first_row:
        keyboard_rows.append(first_row)

    if not keyboard_rows:
        return None

    return ReplyKeyboardMarkup(
        keyboard=keyboard_rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Pilih menu yang anda perlukan",
    )


def worker_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Rekod Masuk", callback_data="attendance:checkin"),
                InlineKeyboardButton(text="Rekod Keluar", callback_data="attendance:checkout"),
            ],
            [InlineKeyboardButton(text="Mohon Cuti", callback_data="leave:start")],
        ]
    )


def leave_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Cuti Tahunan", callback_data="leave:type:annual")],
            [InlineKeyboardButton(text="Cuti Sakit", callback_data="leave:type:mc")],
            [InlineKeyboardButton(text="Cuti Kecemasan", callback_data="leave:type:emergency")],
        ]
    )


def admin_menu_keyboard(*, web_login_url: Optional[str] = None) -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(text="Pending Leaves", callback_data="admin:pending")],
        [InlineKeyboardButton(text="Current Month PDF", callback_data="admin:report:current")],
    ]
    if web_login_url:
        inline_keyboard.append([InlineKeyboardButton(text="Open Admin Web", url=web_login_url)])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def leave_review_keyboard(leave_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Approve", callback_data=f"leave:approve:{leave_id}"),
                InlineKeyboardButton(text="Reject", callback_data=f"leave:reject:{leave_id}"),
            ]
        ]
    )
