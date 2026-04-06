from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Final

from fastapi import Request

CSRF_SESSION_KEY: Final[str] = "csrf_token"
ADMIN_SESSION_KEY: Final[str] = "is_admin"
ADMIN_USERNAME_SESSION_KEY: Final[str] = "admin_username"
PASSWORD_HASH_SCHEME: Final[str] = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS: Final[int] = 390000


class SecurityError(ValueError):
    pass


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def hash_password(password: str, *, iterations: int = PASSWORD_HASH_ITERATIONS) -> str:
    if not password:
        raise ValueError("Password cannot be empty.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{PASSWORD_HASH_SCHEME}${iterations}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, *, password_hash: str, fallback_password: str = "") -> bool:
    if password_hash:
        try:
            scheme, raw_iterations, salt_value, digest_value = password_hash.split("$", 3)
            if scheme != PASSWORD_HASH_SCHEME:
                return False
            iterations = int(raw_iterations)
            expected_digest = _b64decode(digest_value)
            actual_digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                _b64decode(salt_value),
                iterations,
            )
            return secrets.compare_digest(actual_digest, expected_digest)
        except (TypeError, ValueError):
            return False
    if fallback_password:
        return secrets.compare_digest(password, fallback_password)
    return False


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if token:
        return token
    token = secrets.token_urlsafe(32)
    request.session[CSRF_SESSION_KEY] = token
    return token


def csrf_token(request: Request) -> str:
    return ensure_csrf_token(request)


def verify_csrf_token(request: Request, submitted_token: str) -> None:
    session_token = request.session.get(CSRF_SESSION_KEY)
    if not session_token or not submitted_token or not secrets.compare_digest(session_token, submitted_token):
        raise SecurityError("Your session expired or the form token was invalid. Please try again.")


def login_admin(request: Request, *, username: str) -> None:
    request.session.clear()
    request.session[ADMIN_SESSION_KEY] = True
    request.session[ADMIN_USERNAME_SESSION_KEY] = username
    request.session[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)


def logout_admin(request: Request) -> None:
    request.session.clear()


def session_admin_username(request: Request) -> str | None:
    value = request.session.get(ADMIN_USERNAME_SESSION_KEY)
    return str(value) if value else None
