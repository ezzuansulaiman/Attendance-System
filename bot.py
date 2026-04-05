"""
Telegram bot for the KHSAR Attendance System.

Staff commands:
  /start   - Register or welcome back
  /hadir   - Mark today as present (P)
  /cuti    - Apply for leave
  /status  - View this month's attendance
  /cancel  - Cancel current conversation

Admin commands:
  /pending      - List pending leave requests
  /lulus <id>   - Approve leave request
  /tolak <id>   - Reject leave request
"""

import calendar
import logging
import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import db
from constants import DAY_ABBR_MS, LEAVE_TYPES, REGIONS, STATUS_LABELS

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
    if x.strip().isdigit()
}
BOT_TIMEZONE = os.getenv("BOT_TIMEZONE", "Asia/Kuala_Lumpur")
WORKDAY_START = os.getenv("WORKDAY_START", "07:00")
WORKDAY_END = os.getenv("WORKDAY_END", "17:30")

try:
    LOCAL_TZ = ZoneInfo(BOT_TIMEZONE)
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=8))
    logger.warning(
        "Zon masa %s tidak tersedia, guna UTC+08:00 sebagai gantian.",
        BOT_TIMEZONE,
    )

REG_NAME, REG_REGION = range(2)
LEAVE_TYPE, LEAVE_FROM, LEAVE_TO, LEAVE_REASON = range(4, 8)

MENU_CHECKIN = "Hadir Hari Ini"
MENU_LEAVE = "Mohon Cuti"
MENU_STATUS = "Status Bulan Ini"
MENU_HELP = "Bantuan"
MENU_PENDING = "Semak Permohonan"


def _parse_local_time(value: str, fallback: str) -> time:
    raw = (value or fallback).strip()
    try:
        hour_str, minute_str = raw.split(":", 1)
        return time(hour=int(hour_str), minute=int(minute_str), tzinfo=LOCAL_TZ)
    except Exception:
        hour_str, minute_str = fallback.split(":", 1)
        return time(hour=int(hour_str), minute=int(minute_str), tzinfo=LOCAL_TZ)


REMINDER_TIME = _parse_local_time(WORKDAY_START, "07:00")


def _is_admin(update: Update) -> bool:
    return update.effective_user.id in ADMIN_IDS


def _get_emp(update: Update):
    return db.get_employee_by_telegram(str(update.effective_user.id))


def _work_schedule_label() -> str:
    return f"{WORKDAY_START}-{WORKDAY_END}"


def _staff_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [MENU_CHECKIN, MENU_LEAVE],
            [MENU_STATUS, MENU_HELP],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [MENU_CHECKIN, MENU_LEAVE],
            [MENU_STATUS, MENU_PENDING],
            [MENU_HELP],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _main_menu_markup(emp=None, is_admin=False):
    if is_admin:
        return _admin_menu_keyboard()
    if emp:
        return _staff_menu_keyboard()
    return ReplyKeyboardRemove()


async def _notify_admins(app, message: str):
    for admin_id in ADMIN_IDS:
        try:
            await app.bot.send_message(
                chat_id=admin_id,
                text=message,
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning("Gagal hantar notifikasi ke admin %s: %s", admin_id, exc)


async def _send_daily_checkin_reminder(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(LOCAL_TZ).date()
    if today.weekday() > 4:
        return

    employees = db.get_employees(active_only=True)
    sent = 0
    for emp in employees:
        telegram_id = (emp.get("telegram_id") or "").strip()
        if not telegram_id:
            continue
        if db.get_attendance(emp["id"], today):
            continue
        try:
            await context.bot.send_message(
                chat_id=int(telegram_id),
                text=(
                    "Peringatan kehadiran harian.\n\n"
                    f"Waktu kerja hari ini: {_work_schedule_label()}\n"
                    "Hari bekerja: Isnin hingga Jumaat\n"
                    "Sila daftar hadir sekarang dengan /hadir."
                ),
            )
            sent += 1
        except Exception as exc:
            logger.warning(
                "Gagal hantar peringatan ke pekerja %s (%s): %s",
                emp["id"],
                telegram_id,
                exc,
            )

    logger.info("Peringatan check-in dihantar kepada %s pekerja untuk %s", sent, today)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    emp = db.get_employee_by_telegram(str(user.id))

    if emp:
        await update.message.reply_text(
            (
                f"Selamat kembali, <b>{emp['full_name']}</b>!\n\n"
                f"Jawatan: {emp['designation']} | "
                f"Kawasan: {REGIONS.get(emp['region'], emp['region'])}\n"
                f"Waktu kerja: {_work_schedule_label()} (Isnin hingga Jumaat)\n\n"
                "Gunakan butang menu di bawah untuk daftar hadir, mohon cuti, "
                "atau semak status bulanan."
            ),
            parse_mode="HTML",
            reply_markup=_main_menu_markup(emp=emp, is_admin=_is_admin(update)),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        (
            "Assalamualaikum. Saya bot kehadiran KHSAR.\n\n"
            "Anda belum berdaftar. Sila masukkan <b>nama penuh</b> anda "
            "(seperti dalam IC)."
        ),
        parse_mode="HTML",
    )
    return REG_NAME


async def reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg_name"] = update.message.text.strip()
    keyboard = [[region_name] for region_name in REGIONS.values()]
    await update.message.reply_text(
        "Pilih kawasan kerja anda:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            one_time_keyboard=True,
            resize_keyboard=True,
        ),
    )
    return REG_REGION


async def reg_region(update: Update, context: ContextTypes.DEFAULT_TYPE):
    region_name_input = update.message.text.strip()
    region_key = next(
        (key for key, value in REGIONS.items() if value == region_name_input),
        None,
    )

    if not region_key:
        await update.message.reply_text("Sila pilih kawasan dari papan kekunci.")
        return REG_REGION

    full_name = context.user_data.get("reg_name", "Pekerja")
    user_id = str(update.effective_user.id)
    all_emps = db.get_employees(region=region_key, active_only=True)
    matched = next(
        (
            emp for emp in all_emps
            if emp["full_name"].lower() == full_name.lower() and not emp["telegram_id"]
        ),
        None,
    )

    if matched:
        db.link_telegram(matched["id"], user_id)
        emp = db.get_employee(matched["id"])
    else:
        emp_id = db.insert_employee(
            full_name=full_name,
            designation="Pekerja",
            region=region_key,
            telegram_id=user_id,
        )
        emp = db.get_employee(emp_id)

    await update.message.reply_text(
        (
            "Pendaftaran berjaya.\n\n"
            f"Nama: <b>{emp['full_name']}</b>\n"
            f"Kawasan: {REGIONS.get(region_key, region_key)}\n"
            f"Waktu kerja: {_work_schedule_label()} (Isnin hingga Jumaat)\n\n"
            "Butang menu telah diaktifkan. Tekan 'Hadir Hari Ini' untuk daftar "
            "kehadiran pertama anda."
        ),
        parse_mode="HTML",
        reply_markup=_main_menu_markup(emp=emp, is_admin=_is_admin(update)),
    )

    await _notify_admins(
        context.application,
        (
            "Pekerja baru berdaftar:\n"
            f"<b>{emp['full_name']}</b> - {REGIONS.get(region_key, region_key)}"
        ),
    )
    return ConversationHandler.END


async def cmd_hadir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    emp = _get_emp(update)
    if not emp:
        await update.message.reply_text(
            "Anda belum berdaftar atau akaun sudah tidak aktif. Sila taip /start.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    today = date.today()
    existing = db.get_attendance(emp["id"], today)
    if existing:
        label = STATUS_LABELS.get(existing["status"], existing["status"])
        await update.message.reply_text(
            (
                "Kehadiran hari ini sudah direkod.\n"
                f"Status: <b>{existing['status']} - {label}</b>\n"
                f"Tarikh: {today.strftime('%d/%m/%Y')}"
            ),
            parse_mode="HTML",
            reply_markup=_main_menu_markup(emp=emp, is_admin=_is_admin(update)),
        )
        return

    db.upsert_attendance(
        emp["id"],
        today,
        "P",
        entered_by=f"bot:{update.effective_user.id}",
    )
    await update.message.reply_text(
        (
            "Kehadiran direkod.\n\n"
            f"<b>{emp['full_name']}</b>\n"
            f"Tarikh: {today.strftime('%d %B %Y')}\n"
            "Status: Hadir (P)"
        ),
        parse_mode="HTML",
        reply_markup=_main_menu_markup(emp=emp, is_admin=_is_admin(update)),
    )


async def cmd_cuti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    emp = _get_emp(update)
    if not emp:
        await update.message.reply_text("Sila /start untuk daftar dahulu.")
        return ConversationHandler.END

    context.user_data["cuti_emp_id"] = emp["id"]
    keyboard = [
        [InlineKeyboardButton("AL - Cuti Tahunan", callback_data="AL")],
        [InlineKeyboardButton("MC - Cuti Sakit", callback_data="MC")],
        [InlineKeyboardButton("EML - Cuti Kecemasan", callback_data="EML")],
    ]
    await update.message.reply_text(
        "Pilih jenis cuti:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return LEAVE_TYPE


async def leave_type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    leave_type = query.data

    if leave_type not in LEAVE_TYPES:
        await query.edit_message_text("Jenis cuti tidak sah.")
        return ConversationHandler.END

    context.user_data["leave_type"] = leave_type
    await query.edit_message_text(
        (
            f"Jenis cuti: <b>{leave_type}</b>\n\n"
            "Sila masukkan <b>tarikh mula</b> cuti (DD/MM/YYYY)."
        ),
        parse_mode="HTML",
    )
    return LEAVE_FROM


async def leave_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        chosen_date = date(*reversed([int(x) for x in text.split("/")]))
    except Exception:
        await update.message.reply_text(
            "Format tidak sah. Sila masukkan tarikh dalam format DD/MM/YYYY. Contoh: 15/04/2026"
        )
        return LEAVE_FROM

    context.user_data["leave_from"] = chosen_date.isoformat()
    await update.message.reply_text(
        (
            f"Tarikh mula: <b>{chosen_date.strftime('%d %B %Y')}</b>\n\n"
            "Masukkan <b>tarikh akhir</b> cuti (DD/MM/YYYY)."
        ),
        parse_mode="HTML",
    )
    return LEAVE_TO


async def leave_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        chosen_date = date(*reversed([int(x) for x in text.split("/")]))
    except Exception:
        await update.message.reply_text("Format tidak sah. Contoh: 15/04/2026")
        return LEAVE_TO

    from_date = date.fromisoformat(context.user_data["leave_from"])
    if chosen_date < from_date:
        await update.message.reply_text(
            "Tarikh akhir tidak boleh lebih awal dari tarikh mula."
        )
        return LEAVE_TO

    context.user_data["leave_to"] = chosen_date.isoformat()
    await update.message.reply_text(
        (
            f"Tarikh akhir: <b>{chosen_date.strftime('%d %B %Y')}</b>\n\n"
            "Nyatakan sebab / alasan cuti (atau taip <b>skip</b>)."
        ),
        parse_mode="HTML",
    )
    return LEAVE_REASON


async def leave_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text.strip()
    if reason.lower() == "skip":
        reason = ""

    emp_id = context.user_data["cuti_emp_id"]
    leave_type = context.user_data["leave_type"]
    date_from = context.user_data["leave_from"]
    date_to = context.user_data["leave_to"]

    try:
        lr_id = db.insert_leave_request(emp_id, leave_type, date_from, date_to, reason)
    except Exception as exc:
        await update.message.reply_text(f"Ralat: {exc}")
        context.user_data.clear()
        return ConversationHandler.END

    emp = db.get_employee(emp_id)

    await update.message.reply_text(
        (
            f"Permohonan cuti dihantar. (ID: #{lr_id})\n\n"
            f"Jenis: <b>{leave_type}</b>\n"
            f"Dari: {date_from}\n"
            f"Hingga: {date_to}\n"
            "Sila tunggu kelulusan daripada penyelia."
        ),
        parse_mode="HTML",
        reply_markup=_main_menu_markup(emp=emp, is_admin=_is_admin(update)),
    )

    await _notify_admins(
        context.application,
        (
            f"Permohonan cuti baharu (ID #{lr_id})\n"
            f"<b>{emp['full_name']}</b> - {REGIONS.get(emp['region'], emp['region'])}\n"
            f"Jenis: {leave_type} | {date_from} hingga {date_to}\n"
            f"{'Sebab: ' + reason if reason else ''}\n\n"
            f"Lulus: /lulus {lr_id}   Tolak: /tolak {lr_id}"
        ),
    )

    context.user_data.clear()
    return ConversationHandler.END


async def cmd_baki(update: Update, context: ContextTypes.DEFAULT_TYPE):
    emp = _get_emp(update)
    if not emp:
        await update.message.reply_text(
            "Sila /start untuk daftar dahulu.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await update.message.reply_text(
        "Semakan baki cuti tidak dipaparkan melalui bot. Sila hubungi penyelia jika perlu.",
        reply_markup=_main_menu_markup(emp=emp, is_admin=_is_admin(update)),
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    emp = _get_emp(update)
    if not emp:
        await update.message.reply_text(
            "Sila /start untuk daftar dahulu.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    today = date.today()
    year, month = today.year, today.month
    _, grid = db.get_month_grid(emp["region"], year, month)
    my_grid = grid.get(emp["id"], {})
    num_days = calendar.monthrange(year, month)[1]

    counts = {status: 0 for status in ["P", "AL", "MC", "EML", "OD", "RD"]}
    for status in my_grid.values():
        if status in counts:
            counts[status] += 1

    month_names = [
        "Januari", "Februari", "Mac", "April", "Mei", "Jun",
        "Julai", "Ogos", "September", "Oktober", "November", "Disember",
    ]
    lines = [
        f"<b>Status Kehadiran - {month_names[month - 1]} {year}</b>",
        f"{emp['full_name']} | {REGIONS.get(emp['region'], emp['region'])}\n",
    ]

    week = []
    for day in range(1, num_days + 1):
        status = my_grid.get(day, ".")
        week.append(f"{day}({status})")
        if date(year, month, day).weekday() == 6 or day == num_days:
            lines.append("  ".join(week))
            week = []

    lines.append(
        "\nJumlah: "
        f"P={counts['P']} "
        f"AL={counts['AL']} "
        f"MC={counts['MC']} "
        f"EML={counts['EML']} "
        f"OD/RD={counts['OD'] + counts['RD']}"
    )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=_main_menu_markup(emp=emp, is_admin=_is_admin(update)),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    emp = _get_emp(update)
    is_admin = _is_admin(update)
    menu_text = (
        "<b>Menu Bot KHSAR</b>\n\n"
        f"{MENU_CHECKIN} - daftar hadir hari ini\n"
        f"{MENU_LEAVE} - hantar permohonan cuti\n"
        f"{MENU_STATUS} - semak rekod bulan ini\n"
        f"{MENU_HELP} - paparan bantuan ini\n"
    )
    if is_admin:
        menu_text += f"{MENU_PENDING} - lihat permohonan cuti tertangguh\n"
    menu_text += (
        "\nJika lebih selesa guna arahan, anda juga boleh taip "
        "/hadir, /cuti, /status, /cancel."
    )
    await update.message.reply_text(
        menu_text,
        parse_mode="HTML",
        reply_markup=_main_menu_markup(emp=emp, is_admin=is_admin),
    )


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    requests = db.get_leave_requests(status="pending", limit=20)
    if not requests:
        await update.message.reply_text(
            "Tiada permohonan cuti tertangguh.",
            reply_markup=_main_menu_markup(
                emp=_get_emp(update),
                is_admin=True,
            ),
        )
        return

    lines = ["<b>Permohonan Cuti Tertangguh:</b>\n"]
    for leave_request in requests:
        lines.append(
            (
                f"#{leave_request['id']} - <b>{leave_request['full_name']}</b> "
                f"({leave_request['region']})\n"
                f"  {leave_request['leave_type']} | "
                f"{leave_request['date_from']} hingga {leave_request['date_to']}\n"
                f"  /lulus {leave_request['id']}  /tolak {leave_request['id']}\n"
            )
        )
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=_main_menu_markup(emp=_get_emp(update), is_admin=True),
    )


async def cmd_lulus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "Guna: /lulus <id>",
            reply_markup=_main_menu_markup(emp=_get_emp(update), is_admin=True),
        )
        return

    lr_id = int(args[0])
    try:
        db.approve_leave(lr_id, reviewed_by=f"tg:{update.effective_user.id}")
        leave_request = db.get_leave_request(lr_id)
        await update.message.reply_text(
            (
                f"Permohonan #{lr_id} diluluskan.\n"
                f"<b>{leave_request['full_name']}</b> - {leave_request['leave_type']} "
                f"({leave_request['date_from']} hingga {leave_request['date_to']})"
            ),
            parse_mode="HTML",
            reply_markup=_main_menu_markup(emp=_get_emp(update), is_admin=True),
        )
        if leave_request.get("telegram_id"):
            try:
                await context.bot.send_message(
                    chat_id=int(leave_request["telegram_id"]),
                    text=(
                        "Permohonan cuti anda diluluskan.\n"
                        f"Jenis: {leave_request['leave_type']}\n"
                        f"Tarikh: {leave_request['date_from']} hingga {leave_request['date_to']}"
                    ),
                )
            except Exception:
                pass
    except Exception as exc:
        await update.message.reply_text(
            f"Ralat: {exc}",
            reply_markup=_main_menu_markup(emp=_get_emp(update), is_admin=True),
        )


async def cmd_tolak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "Guna: /tolak <id>",
            reply_markup=_main_menu_markup(emp=_get_emp(update), is_admin=True),
        )
        return

    lr_id = int(args[0])
    try:
        db.reject_leave(lr_id, reviewed_by=f"tg:{update.effective_user.id}")
        leave_request = db.get_leave_request(lr_id)
        await update.message.reply_text(
            (
                f"Permohonan #{lr_id} ditolak.\n"
                f"<b>{leave_request['full_name']}</b> - {leave_request['leave_type']}"
            ),
            parse_mode="HTML",
            reply_markup=_main_menu_markup(emp=_get_emp(update), is_admin=True),
        )
        if leave_request.get("telegram_id"):
            try:
                await context.bot.send_message(
                    chat_id=int(leave_request["telegram_id"]),
                    text=(
                        "Maaf, permohonan cuti anda ditolak.\n"
                        f"Jenis: {leave_request['leave_type']}\n"
                        f"Tarikh: {leave_request['date_from']} hingga {leave_request['date_to']}\n"
                        "Sila hubungi penyelia untuk maklumat lanjut."
                    ),
                )
            except Exception:
                pass
    except Exception as exc:
        await update.message.reply_text(
            f"Ralat: {exc}",
            reply_markup=_main_menu_markup(emp=_get_emp(update), is_admin=True),
        )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    emp = _get_emp(update)
    await update.message.reply_text(
        "Dibatalkan. Anda boleh pilih semula daripada menu di bawah.",
        reply_markup=_main_menu_markup(emp=emp, is_admin=_is_admin(update)),
    )
    return ConversationHandler.END


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    emp = _get_emp(update)
    await update.message.reply_text(
        "Pilihan tidak dikenali. Gunakan butang menu di bawah atau taip /help.",
        reply_markup=_main_menu_markup(emp=emp, is_admin=_is_admin(update)),
    )


async def menu_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_hadir(update, context)


async def menu_leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_cuti(update, context)


async def menu_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_status(update, context)


async def menu_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_pending(update, context)


async def _post_init(app_instance):
    commands = [
        BotCommand("start", "Buka menu utama"),
        BotCommand("hadir", "Daftar hadir hari ini"),
        BotCommand("cuti", "Mohon cuti"),
        BotCommand("status", "Semak rekod bulan ini"),
        BotCommand("help", "Lihat bantuan"),
        BotCommand("cancel", "Batalkan proses semasa"),
    ]
    if ADMIN_IDS:
        commands.extend([
            BotCommand("pending", "Lihat permohonan tertangguh"),
            BotCommand("lulus", "Luluskan permohonan cuti"),
            BotCommand("tolak", "Tolak permohonan cuti"),
        ])
    await app_instance.bot.set_my_commands(commands)


def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN tidak ditetapkan dalam .env")
        return

    db.init_db()

    application = Application.builder().token(TELEGRAM_TOKEN).post_init(_post_init).build()

    reg_handler = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            REG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_name)],
            REG_REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_region)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    leave_handler = ConversationHandler(
        entry_points=[CommandHandler("cuti", cmd_cuti)],
        states={
            LEAVE_TYPE: [CallbackQueryHandler(leave_type_chosen)],
            LEAVE_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, leave_from)],
            LEAVE_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, leave_to)],
            LEAVE_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, leave_reason)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    application.add_handler(reg_handler)
    application.add_handler(leave_handler)
    application.add_handler(CommandHandler("hadir", cmd_hadir))
    application.add_handler(CommandHandler("baki", cmd_baki))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("pending", cmd_pending))
    application.add_handler(CommandHandler("lulus", cmd_lulus))
    application.add_handler(CommandHandler("tolak", cmd_tolak))
    application.add_handler(CommandHandler("cancel", cmd_cancel))
    application.add_handler(MessageHandler(filters.Regex(f"^{MENU_CHECKIN}$"), menu_checkin))
    application.add_handler(MessageHandler(filters.Regex(f"^{MENU_LEAVE}$"), menu_leave))
    application.add_handler(MessageHandler(filters.Regex(f"^{MENU_STATUS}$"), menu_status))
    application.add_handler(MessageHandler(filters.Regex(f"^{MENU_HELP}$"), cmd_help))
    application.add_handler(MessageHandler(filters.Regex(f"^{MENU_PENDING}$"), menu_pending))
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Bot dimulakan - menunggu mesej...")
    if application.job_queue is None:
        logger.warning(
            "Job queue tidak tersedia. Pasang dependency baru untuk aktifkan "
            "peringatan check-in automatik."
        )
    else:
        application.job_queue.run_daily(
            _send_daily_checkin_reminder,
            time=REMINDER_TIME,
            days=(0, 1, 2, 3, 4),
            name="daily-checkin-reminder",
        )
        logger.info(
            "Peringatan check-in dijadualkan pada %s (%s), Isnin hingga Jumaat",
            WORKDAY_START,
            BOT_TIMEZONE,
        )
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
