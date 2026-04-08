from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

WORKER_MENU_BUTTON = "Menu Kehadiran"
ADMIN_MENU_BUTTON = "Menu Admin"
CANCEL_CALLBACK = "flow:cancel"
BACK_CALLBACK = "flow:back"


def normalize_menu_trigger(raw_text: Optional[str]) -> str:
    return " ".join((raw_text or "").split()).casefold()


def is_worker_menu_alias(raw_text: Optional[str]) -> bool:
    return normalize_menu_trigger(raw_text) == "menu"


def is_admin_menu_alias(raw_text: Optional[str]) -> bool:
    return normalize_menu_trigger(raw_text) == "admin"


def is_cancel_alias(raw_text: Optional[str]) -> bool:
    return normalize_menu_trigger(raw_text) in {"cancel", "batal"}


def is_back_alias(raw_text: Optional[str]) -> bool:
    return normalize_menu_trigger(raw_text) in {"back", "kembali"}


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
            [
                InlineKeyboardButton(text="Mohon Cuti", callback_data="leave:start"),
                InlineKeyboardButton(text="Status Hari Ini", callback_data="worker:status"),
            ],
            [
                InlineKeyboardButton(text="Cuti Saya", callback_data="worker:leaves"),
                InlineKeyboardButton(text="Profil Saya", callback_data="worker:profile"),
            ],
        ]
    )


def leave_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Cuti Tahunan", callback_data="leave:type:annual")],
            [InlineKeyboardButton(text="Cuti Sakit", callback_data="leave:type:mc")],
            [InlineKeyboardButton(text="Cuti Kecemasan", callback_data="leave:type:emergency")],
            [InlineKeyboardButton(text="Batal", callback_data=CANCEL_CALLBACK)],
        ]
    )


def leave_day_portion_keyboard(
    *,
    back_callback: str = BACK_CALLBACK,
    cancel_callback: str = CANCEL_CALLBACK,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Sehari Penuh", callback_data="leave:portion:full")],
            [InlineKeyboardButton(text="Separuh Hari (Pagi)", callback_data="leave:portion:am")],
            [InlineKeyboardButton(text="Separuh Hari (Petang)", callback_data="leave:portion:pm")],
            [
                InlineKeyboardButton(text="Kembali", callback_data=back_callback),
                InlineKeyboardButton(text="Batal", callback_data=cancel_callback),
            ],
        ]
    )


def admin_menu_keyboard(*, web_login_url: Optional[str] = None) -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(text="Cuti Menunggu", callback_data="admin:pending")],
        [InlineKeyboardButton(text="PDF Bulan Semasa", callback_data="admin:report:current")],
        [InlineKeyboardButton(text="Excel Bulan Semasa", callback_data="admin:report:current:excel")],
    ]
    if web_login_url:
        inline_keyboard.append([InlineKeyboardButton(text="Buka Admin Web", url=web_login_url)])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def leave_review_keyboard(leave_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Lulus", callback_data=f"leave:approve:{leave_id}"),
                InlineKeyboardButton(text="Tolak", callback_data=f"leave:reject:{leave_id}"),
            ]
        ]
    )


def flow_control_keyboard(
    *,
    include_back: bool = True,
    back_callback: str = BACK_CALLBACK,
    cancel_callback: str = CANCEL_CALLBACK,
) -> InlineKeyboardMarkup:
    row: list[InlineKeyboardButton] = []
    if include_back:
        row.append(InlineKeyboardButton(text="Kembali", callback_data=back_callback))
    row.append(InlineKeyboardButton(text="Batal", callback_data=cancel_callback))
    return InlineKeyboardMarkup(inline_keyboard=[row])


def confirmation_keyboard(
    *,
    confirm_callback: str,
    back_callback: str = BACK_CALLBACK,
    cancel_callback: str = CANCEL_CALLBACK,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Sahkan", callback_data=confirm_callback)],
            [
                InlineKeyboardButton(text="Kembali", callback_data=back_callback),
                InlineKeyboardButton(text="Batal", callback_data=cancel_callback),
            ],
        ]
    )
