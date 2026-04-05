"""Helpers for validating and storing leave supporting images."""

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
