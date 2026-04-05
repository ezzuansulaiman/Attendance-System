"""Helpers for validating leave supporting images and Telegram-backed metadata."""

import json
import os
from datetime import datetime

from werkzeug.utils import secure_filename

REQUIRED_IMAGE_LEAVE_TYPES = {"MC", "EML"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_UPLOAD_ROOT = os.path.join(_BASE_DIR, "uploads")
_LEAVE_DOCS_DIR = os.path.join(_UPLOAD_ROOT, "leave_docs")


def leave_type_requires_supporting_doc(leave_type):
    return leave_type in REQUIRED_IMAGE_LEAVE_TYPES


def is_allowed_image(filename="", mime_type=""):
    ext = os.path.splitext((filename or "").lower())[1]
    if ext in ALLOWED_IMAGE_EXTENSIONS:
        return True
    return (mime_type or "").lower() in {
        "image/jpeg",
        "image/png",
        "image/webp",
    }


def ensure_supporting_doc_dir():
    os.makedirs(_LEAVE_DOCS_DIR, exist_ok=True)
    return _LEAVE_DOCS_DIR


def build_supporting_doc_name(leave_type, employee_id, source_name="proof.jpg"):
    clean_name = secure_filename(source_name or "proof.jpg")
    _, ext = os.path.splitext(clean_name)
    ext = ext.lower() if ext.lower() in ALLOWED_IMAGE_EXTENSIONS else ".jpg"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{leave_type.lower()}_{employee_id}_{stamp}{ext}"


def get_absolute_supporting_doc_path(stored_name):
    if not stored_name:
        return None
    abs_path = os.path.abspath(os.path.join(ensure_supporting_doc_dir(), stored_name))
    docs_root = os.path.abspath(ensure_supporting_doc_dir())
    if not abs_path.startswith(docs_root):
        raise ValueError("Laluan dokumen sokongan tidak sah.")
    return abs_path


def build_telegram_supporting_doc(
    *,
    kind,
    file_id,
    file_unique_id="",
    chat_id=None,
    message_id=None,
    file_name="proof.jpg",
    mime_type="image/jpeg",
):
    payload = {
        "storage": "telegram",
        "kind": kind,
        "file_id": file_id,
        "file_unique_id": file_unique_id or "",
        "chat_id": chat_id,
        "message_id": message_id,
        "file_name": file_name or "proof.jpg",
        "mime_type": mime_type or "image/jpeg",
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def parse_supporting_doc(stored_value):
    if not stored_value:
        return None
    try:
        payload = json.loads(stored_value)
    except (TypeError, ValueError):
        return {
            "storage": "legacy_local",
            "stored_name": str(stored_value),
            "file_name": os.path.basename(str(stored_value)) or "proof.jpg",
            "mime_type": "image/jpeg",
        }

    if not isinstance(payload, dict):
        return None
    if payload.get("storage") != "telegram" or not payload.get("file_id"):
        return None
    return payload
