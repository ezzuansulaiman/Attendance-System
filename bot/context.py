from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from aiogram.types import CallbackQuery, Message

from config import get_settings
from models import session_scope
from models.models import Worker
from services.attendance_service import get_worker_by_telegram_id

settings = get_settings()
local_tz = settings.local_timezone
TelegramEvent = Union[Message, CallbackQuery]


@dataclass(frozen=True)
class WorkerAccess:
    worker: Optional[Worker]
    is_inactive: bool = False


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def chat_is_allowed(event: TelegramEvent) -> bool:
    chat = event.message.chat if isinstance(event, CallbackQuery) else event.chat
    if chat.type == "private":
        return True
    if chat.type in {"group", "supergroup"}:
        return settings.group_id is not None and chat.id == settings.group_id
    return False


def worker_group_id(worker: Optional[Worker]) -> Optional[int]:
    if worker and worker.site and worker.site.telegram_group_id:
        return worker.site.telegram_group_id
    return settings.group_id


def worker_chat_is_allowed(worker: Optional[Worker], event: TelegramEvent) -> bool:
    chat = event.message.chat if isinstance(event, CallbackQuery) else event.chat
    if chat.type == "private":
        return True
    if chat.type in {"group", "supergroup"}:
        allowed_group_id = worker_group_id(worker)
        return allowed_group_id is not None and chat.id == allowed_group_id
    return False


async def load_worker_access(telegram_user_id: int) -> WorkerAccess:
    async with session_scope() as session:
        worker = await get_worker_by_telegram_id(session, telegram_user_id, active_only=False)
    if not worker:
        return WorkerAccess(worker=None, is_inactive=False)
    if worker.is_active is False:
        return WorkerAccess(worker=None, is_inactive=True)
    return WorkerAccess(worker=worker, is_inactive=False)


def worker_group_restriction_text() -> str:
    return "Bot ini hanya boleh digunakan dalam kumpulan pekerja yang ditetapkan atau melalui chat peribadi."


def attendance_restriction_text() -> str:
    return "Fungsi kehadiran hanya boleh digunakan dalam kumpulan pekerja yang ditetapkan atau melalui chat peribadi."


def leave_restriction_text() -> str:
    return (
        "Permohonan cuti hanya boleh dibuat dalam kumpulan pekerja yang ditetapkan atau melalui chat peribadi. "
        "Jika anda berada dalam group lain, buka chat peribadi bot dan tekan Mohon Cuti semula."
    )


def registered_workers_only_text() -> str:
    return "Fungsi ini hanya untuk pekerja yang telah berdaftar."


def inactive_worker_text() -> str:
    return "Rekod anda wujud dalam sistem tetapi akaun pekerja ini sedang tidak aktif. Sila hubungi admin."
