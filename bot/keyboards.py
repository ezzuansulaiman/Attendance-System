from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


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
