import calendar
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


def leave_type_keyboard(*, cancel_callback: str = CANCEL_CALLBACK) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Cuti Tahunan", callback_data="leave:type:annual")],
            [InlineKeyboardButton(text="Cuti Sakit", callback_data="leave:type:mc")],
            [InlineKeyboardButton(text="Cuti Kecemasan", callback_data="leave:type:emergency")],
            [InlineKeyboardButton(text="Batal", callback_data=cancel_callback)],
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
        [InlineKeyboardButton(text="Ringkasan Hari Ini", callback_data="admin:report:today:summary")],
        [InlineKeyboardButton(text="Laporan Ikut Site/Bulan", callback_data="admin:report:custom")],
        [
            InlineKeyboardButton(text="Ringkasan Bulan Semasa", callback_data="admin:report:current:summary"),
            InlineKeyboardButton(text="Ringkasan Bulan Lepas", callback_data="admin:report:previous:summary"),
        ],
        [
            InlineKeyboardButton(text="PDF Bulan Semasa", callback_data="admin:report:current"),
            InlineKeyboardButton(text="PDF Bulan Lepas", callback_data="admin:report:previous"),
        ],
        [
            InlineKeyboardButton(text="Excel Bulan Semasa", callback_data="admin:report:current:excel"),
            InlineKeyboardButton(text="Excel Bulan Lepas", callback_data="admin:report:previous:excel"),
        ],
        [InlineKeyboardButton(text="Hantar Panduan ke Group", callback_data="admin:broadcast:guide")],
    ]
    if web_login_url:
        inline_keyboard.append([InlineKeyboardButton(text="Buka Admin Web", url=web_login_url)])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def _site_button_label(site: object) -> str:
    site_name = str(getattr(site, "name", "Site")).strip() or "Site"
    site_code = str(getattr(site, "code", "") or "").strip()
    if site_code:
        return f"{site_code} - {site_name}"
    return site_name


def admin_report_site_keyboard(*, sites: list[object]) -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(text=_site_button_label(site), callback_data=f"admin:report:custom:site:{site.id}")]
        for site in sites
    ]
    inline_keyboard.append([InlineKeyboardButton(text="Menu Admin", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def admin_report_month_keyboard(*, site_id: int, year: int) -> InlineKeyboardMarkup:
    inline_keyboard: list[list[InlineKeyboardButton]] = []
    for start_month in (1, 4, 7, 10):
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=calendar.month_abbr[month],
                    callback_data=f"admin:report:custom:month:{site_id}:{year}:{month}",
                )
                for month in range(start_month, start_month + 3)
            ]
        )

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=f"<< {year - 1}",
                callback_data=f"admin:report:custom:year:{site_id}:{year - 1}",
            ),
            InlineKeyboardButton(
                text=f"{year + 1} >>",
                callback_data=f"admin:report:custom:year:{site_id}:{year + 1}",
            ),
        ]
    )
    inline_keyboard.append(
        [
            InlineKeyboardButton(text="Tukar Site", callback_data="admin:report:custom"),
            InlineKeyboardButton(text="Menu Admin", callback_data="admin:menu"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def admin_report_format_keyboard(*, site_id: int, year: int, month: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Ringkasan Telegram",
                    callback_data=f"admin:report:custom:run:{site_id}:{year}:{month}:summary",
                )
            ],
            [
                InlineKeyboardButton(
                    text="PDF",
                    callback_data=f"admin:report:custom:run:{site_id}:{year}:{month}:pdf",
                ),
                InlineKeyboardButton(
                    text="Excel",
                    callback_data=f"admin:report:custom:run:{site_id}:{year}:{month}:excel",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Tukar Bulan",
                    callback_data=f"admin:report:custom:year:{site_id}:{year}",
                ),
                InlineKeyboardButton(text="Tukar Site", callback_data="admin:report:custom"),
            ],
            [InlineKeyboardButton(text="Menu Admin", callback_data="admin:menu")],
        ]
    )


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
