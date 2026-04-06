from aiogram import Router

from bot.admin_handlers import router as admin_router
from bot.admin_handlers import set_bot_commands
from bot.leave_handlers import router as leave_router
from bot.worker_handlers import router as worker_router

router = Router()
router.include_router(worker_router)
router.include_router(leave_router)
router.include_router(admin_router)

__all__ = ["router", "set_bot_commands"]
