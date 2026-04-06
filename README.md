# KHSAR Attendance System

Telegram attendance bot + FastAPI admin dashboard for `Khidmat Hartanah Samat Ayob & Rakan Sdn Bhd.`

## Current Architecture

- `main.py` runs the FastAPI web app and Telegram bot together in one process.
- Railway should deploy:
  1. one `PostgreSQL` service
  2. one `application` service from this repository
- The app listens on `0.0.0.0:${PORT}` and exposes `/health`.
- The app supports multiple sites, not just Sepang.

## Railway Deployment

Because this repository already includes a [Dockerfile](./Dockerfile), Railway will build from that Dockerfile by default. Railway's docs state that when a Dockerfile is present, the service uses the Dockerfile image and defaults to its `ENTRYPOINT`/`CMD` unless you override the start command.

Recommended Railway setup:

1. Create a new Railway project.
2. Add a `PostgreSQL` service.
3. Add one app service from this GitHub repo.
4. Do not set a custom Start Command unless you intentionally want to override the Dockerfile.
5. In the app service, set the Healthcheck Path to `/health`.

## Railway Variables

Set these variables on the app service:

```env
BOT_TOKEN=<telegram bot token from BotFather>
DATABASE_URL=${{Postgres.DATABASE_URL}}
ADMIN_IDS=<telegram_admin_id_1,telegram_admin_id_2>
GROUP_ID=<optional_fallback_telegram_worker_group_id>

PORT=8000
TIMEZONE=Asia/Kuala_Lumpur
COMPANY_NAME=Khidmat Hartanah Samat Ayob & Rakan Sdn Bhd.
DEFAULT_SITE_NAME=Sepang

ADMIN_WEB_USERNAME=admin
ADMIN_WEB_PASSWORD=<strong_admin_password>
SESSION_SECRET=<long_random_secret>
```

You can copy from [`.env.railway.example`](./.env.railway.example).

Optional variables:

```env
SQLITE_PATH=attendance.db
```

Notes:

- `DATABASE_URL` should come from the Railway PostgreSQL service reference variable.
- The app already converts `postgres://...` into the SQLAlchemy-compatible async format automatically.
- `GROUP_ID` is an optional fallback Telegram worker group if a site does not have its own Telegram group configured.
- `DEFAULT_SITE_NAME` is the first site auto-created during DB initialization.
- `SQLITE_PATH` is only useful for local development, not Railway production.

## What To Put In Railway

Use values like these:

```env
BOT_TOKEN=1234567890:AAExampleFromBotFather
DATABASE_URL=${{Postgres.DATABASE_URL}}
ADMIN_IDS=232621401
GROUP_ID=-1001234567890
PORT=8000
TIMEZONE=Asia/Kuala_Lumpur
COMPANY_NAME=Khidmat Hartanah Samat Ayob & Rakan Sdn Bhd.
DEFAULT_SITE_NAME=Sepang
ADMIN_WEB_USERNAME=admin
ADMIN_WEB_PASSWORD=use-a-strong-password-here
SESSION_SECRET=use-a-long-random-secret-here
```

## Telegram Setup

In BotFather:

1. Create or open your bot.
2. Copy the bot token into `BOT_TOKEN`.
3. Go to `Bot Settings` > `Group Privacy` > turn it `OFF`.

Telegram IDs:

- `ADMIN_IDS` must contain Telegram user IDs for admins who can use `/admin`.
- `GROUP_ID` must be the worker group ID, usually like `-100...`.

## Multi-Site

The system is now flexible for multiple sites:

- Create and manage sites in the web dashboard under `Sites`.
- Assign each worker to a site.
- Optionally assign each site its own `Telegram Group ID`.
- Filter dashboard, attendance, leave list, and PDF reports by site.
- The monthly PDF title will include the selected site when filtered.

## Important Security Remark

Your local `.env` currently contains a real Telegram bot token and a weak admin password. You should rotate both before production:

1. Regenerate the Telegram bot token in BotFather.
2. Replace `ADMIN_WEB_PASSWORD` with a strong value.
3. Replace `SESSION_SECRET` with a long random secret.
4. Do not commit `.env` to GitHub.

## Local Run

```bash
py -3 main.py
```

You can copy from [`.env.local.example`](./.env.local.example) for local setup.

Web admin access:

- Open `http://localhost:8000/`
- If you are not logged in, the app redirects to `/login`
- Sign in using `ADMIN_WEB_USERNAME` and `ADMIN_WEB_PASSWORD`

The app will:

- initialize the database
- start FastAPI
- start the Telegram bot if `BOT_TOKEN` is set

## Railway Notes

According to Railway's current docs:

- PostgreSQL exposes `DATABASE_URL` and related connection variables to other services in the same project.
- When a Dockerfile is present, Railway builds from that Dockerfile.
- If a healthcheck is configured, Railway waits for it to pass before marking the deployment active.

## Official References

- Railway PostgreSQL docs: https://docs.railway.com/guides/postgresql
- Railway deployments reference: https://docs.railway.com/deployments/reference
- Railway start command docs: https://docs.railway.com/deployments/start-command
