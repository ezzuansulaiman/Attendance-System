# Railway Setup Guide

This project is deployed to Railway as:

1. one `PostgreSQL` service
2. one `application` service from this repository

## 1. Create Services

Inside Railway:

1. Create a new project.
2. Add a `PostgreSQL` service.
3. Add a new service from your GitHub repository.

## 2. App Service Settings

Recommended:

- Source: this repository
- Build: use the existing `Dockerfile`
- Start command: leave empty unless you want to override Docker
- Health check path: `/health`

## 3. App Variables

Set these on the app service:

```env
BOT_TOKEN=<your bot token from BotFather>
DATABASE_URL=${{Postgres.DATABASE_URL}}
ADMIN_IDS=232621401
GROUP_ID=-1001234567890
WEB_BASE_URL=https://your-app-public-domain

PORT=8000
TIMEZONE=Asia/Kuala_Lumpur
COMPANY_NAME=Khidmat Hartanah Samat Ayob & Rakan Sdn Bhd.
DEFAULT_SITE_NAME=Sepang
ANNUAL_LEAVE_NOTICE_DAYS=5

ADMIN_WEB_USERNAME=admin
ADMIN_WEB_PASSWORD=<strong password>
SESSION_SECRET=<long random secret>
```

Optional for local use only:

```env
SQLITE_PATH=attendance.db
```

## 4. Telegram Requirements

In BotFather:

1. open your bot
2. go to `Bot Settings`
3. open `Group Privacy`
4. turn it `OFF`

## 5. Get Telegram IDs

You need:

- `ADMIN_IDS`: Telegram user IDs of your admins
- `GROUP_ID`: fallback worker group ID

Usually group IDs look like:

```text
-1001234567890
```

## 6. First Login

After deploy:

1. open your Railway public domain
2. if needed, go directly to `/login`
3. log in using `ADMIN_WEB_USERNAME` and `ADMIN_WEB_PASSWORD`
4. Telegram admins can also use `/admin` > `Open Admin Web` if `WEB_BASE_URL` is configured
5. confirm the dashboard opens
6. create sites in the `Sites` page
7. create or edit workers and assign each worker to a site
8. for each site, optionally fill `Telegram Group ID` to allow a separate Telegram group per site

## 7. Important Remark

Current bot access supports per-site Telegram groups.

That means:

- multiple sites are supported in the database, dashboard, filtering, and reports
- each site can have its own `Telegram Group ID`
- `GROUP_ID` now acts as a fallback default group if a site-specific group is not configured

## 8. Security

Before production:

1. rotate the bot token if it was ever exposed
2. use a strong `ADMIN_WEB_PASSWORD`
3. use a long random `SESSION_SECRET`
4. never commit your real `.env`
