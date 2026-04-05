# KHSAR Attendance System

Sistem attendance pekerja dengan web admin, portal pekerja, dan bot Telegram.

## Setup Railway terbaik

Guna 3 service dalam satu project Railway:

1. `PostgreSQL`
2. `attendance-web`
3. `attendance-bot`

Kedua-dua service app boleh guna repo yang sama.

## Start command Railway

Untuk `attendance-web`:

```bash
py -3 main.py
```

Variables:

```env
SERVICE_MODE=web
DATABASE_URL=${{Postgres.DATABASE_URL}}
FLASK_SECRET_KEY=<nilai-rawak-panjang>
ADMIN_PASSWORD=<kata-laluan-admin-kuat>
SESSION_COOKIE_SECURE=1
PORT=8080
```

Untuk `attendance-bot`:

```bash
py -3 main.py
```

Variables:

```env
SERVICE_MODE=bot
DATABASE_URL=${{Postgres.DATABASE_URL}}
TELEGRAM_BOT_TOKEN=<token-botfather>
ADMIN_TELEGRAM_IDS=<id1,id2>
BOT_TIMEZONE=Asia/Kuala_Lumpur
WORKDAY_START=07:00
WORKDAY_END=17:30
```

Bot akan hantar peringatan check-in automatik kepada pekerja aktif yang telah
link Telegram pada setiap hari Isnin hingga Jumaat, tepat pada `WORKDAY_START`.

## Kenapa PostgreSQL paling sesuai

- Railway menyokong PostgreSQL, MySQL, Redis, MongoDB, dan database lain melalui Docker/template.
- Untuk sistem ini, PostgreSQL paling sesuai kerana web app dan bot Telegram akan berkongsi data yang sama secara stabil.
- SQLite sesuai untuk local test atau single-instance sahaja, bukan pilihan terbaik bila web dan bot dideploy sebagai dua service berasingan.

Rujukan Railway:

- https://docs.railway.com/data-storage

## Local run

Web + Bot serentak:

```bash
set SERVICE_MODE=all
py -3 main.py
```

Atau terus guna:

```bash
start.bat
```

Web:

```bash
set SERVICE_MODE=web
py -3 main.py
```

Bot:

```bash
set SERVICE_MODE=bot
py -3 main.py
```
