"""Shared Telegram helpers for admin routing and leave actions."""

import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _parse_signed_ids(raw_value):
    ids = []
    for chunk in (raw_value or "").split(","):
        item = chunk.strip()
        if not item:
            continue
        if item.startswith("-") and item[1:].isdigit():
            ids.append(int(item))
        elif item.isdigit():
            ids.append(int(item))
    return ids


def admin_user_ids_from_env():
    return {
        chat_id for chat_id in _parse_signed_ids(os.getenv("ADMIN_TELEGRAM_IDS", ""))
        if chat_id > 0
    }


def admin_chat_ids_from_env():
    chat_ids = set(_parse_signed_ids(os.getenv("ADMIN_TELEGRAM_IDS", "")))
    chat_ids.update(_parse_signed_ids(os.getenv("ADMIN_TELEGRAM_GROUP_IDS", "")))
    return sorted(chat_ids)


def leave_approval_markup(lr_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Luluskan", callback_data=f"leave:approve:{lr_id}"),
        InlineKeyboardButton("Tolak", callback_data=f"leave:reject:{lr_id}"),
    ]])
