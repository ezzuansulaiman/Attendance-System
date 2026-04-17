# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application locally
python main.py

# Run all tests
pytest

# Run a single test file
pytest tests/test_attendance_service.py

# Run a single test
pytest tests/test_attendance_service.py::test_function_name -v
```

No linting or formatting tools are configured in this project.

## Architecture Overview

This is a **Python 3.12 async application** that runs two concurrent services in a single process:

1. **FastAPI web dashboard** (admin interface, port 8000)
2. **Telegram bot** (aiogram 3.x, long-polling)

Both share the same database and service layer. `main.py` is the entry point that launches both via `asyncio.gather`.

### Layer Structure

```
main.py
├── web/app.py          → FastAPI app factory, route registration, Jinja2 setup
│   └── web/*_routes.py → Endpoint handlers (auth, dashboard, workers, attendance, leaves, reports, sites)
├── bot/runner.py       → aiogram Dispatcher setup, FSM storage init
│   └── bot/*_handlers.py → Telegram command/callback handlers
├── services/           → Business logic shared by both web and bot
└── models/             → SQLAlchemy ORM models + DB engine factory
```

### Database

- **Local dev:** SQLite via `aiosqlite` (auto-created at `SQLITE_PATH`, default `attendance.db`)
- **Production:** PostgreSQL via `asyncpg`
- Detection is automatic based on `DATABASE_URL` prefix
- No migration tool — schema is created via `create_all()` at startup. `models/database.py` handles backward-compatible schema changes for SQLite/PostgreSQL compatibility

**Core models:** `Worker`, `AttendanceRecord`, `LeaveRequest`, `Site`, `PublicHoliday`, `BotFSMState`

Key constraint: `attendance_records` has a unique index on `(worker_id, attendance_date)` — one record per worker per day.

### Telegram Bot FSM

Leave applications and worker registration use aiogram's FSM (Finite State Machine). States are defined in `bot/states.py` and persisted in the `bot_fsm_states` table via `bot/db_storage.py` (custom FSM storage backend).

### Authentication & Security

Web dashboard uses session-based auth with CSRF protection (`web/security.py`). Passwords are hashed with PBKDF2-SHA256 (390k iterations). In production (`APP_ENV=production`), `ADMIN_WEB_PASSWORD_HASH` is required instead of plaintext `ADMIN_WEB_PASSWORD`, and `SESSION_SECRET` must be ≥32 characters.

### Multi-Site Support

Workers belong to a `Site`. Attendance, leave requests, reports, and Telegram reminders are all filterable by site. Each site can have its own `telegram_group_id` for notifications.

## Key Configuration (config.py)

All config is loaded from environment variables (`.env` file in local dev). Critical variables:

| Variable | Notes |
|---|---|
| `BOT_TOKEN` | Optional — bot features disabled if unset |
| `DATABASE_URL` | `sqlite+aiosqlite:///./attendance.db` or `postgresql+asyncpg://...` |
| `ADMIN_IDS` | Comma-separated Telegram user IDs with admin access |
| `APP_ENV` | `development` (default) or `production` |
| `TIMEZONE` | Default `Asia/Kuala_Lumpur` |
| `ADMIN_WEB_PASSWORD_HASH` | Required in production (PBKDF2-SHA256) |
| `SESSION_SECRET` | Required in production (≥32 chars) |

See `.env.example` and `.env.local.example` for full variable reference.

## Testing Patterns

Tests use `pytest` with async support. Database tests typically create an in-memory SQLite instance. Bot handler tests mock the aiogram `Message` and `FSMContext` objects. Web route tests use FastAPI's `TestClient`. There are 75 tests across 18 files in `tests/`.
