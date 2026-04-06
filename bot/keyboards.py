from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def worker_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Check-In", callback_data="attendance:checkin"),
                InlineKeyboardButton(text="Check-Out", callback_data="attendance:checkout"),
            ],
            [InlineKeyboardButton(text="Apply Leave", callback_data="leave:start")],
        ]
    )


def leave_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Annual", callback_data="leave:type:annual")],
            [InlineKeyboardButton(text="MC", callback_data="leave:type:mc")],
            [InlineKeyboardButton(text="Emergency", callback_data="leave:type:emergency")],
        ]
    )


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Pending Leaves", callback_data="admin:pending")],
            [InlineKeyboardButton(text="Current Month PDF", callback_data="admin:report:current")],
        ]
    )


def leave_review_keyboard(leave_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Approve", callback_data=f"leave:approve:{leave_id}"),
                InlineKeyboardButton(text="Reject", callback_data=f"leave:reject:{leave_id}"),
            ]
        ]
    )
