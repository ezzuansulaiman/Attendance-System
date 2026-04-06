from __future__ import annotations

import asyncio
import logging

import uvicorn

from bot.runner import run_bot_polling
from config import get_settings
from models.database import init_database
from web.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

settings = get_settings()


async def run_web_server() -> None:
    app = create_app()
    config = uvicorn.Config(
        app=app,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


def build_runtime_tasks() -> list:
    tasks = [run_web_server()]
    if settings.bot_enabled:
        tasks.append(run_bot_polling())
    return tasks


async def main() -> None:
    await init_database()
    await asyncio.gather(*build_runtime_tasks())


if __name__ == "__main__":
    asyncio.run(main())
