"""
app.py — Flask web application for the KHSAR Attendance System.

Admin dashboard:  /              (login required, role=admin)
Staff portal:     /portal        (login required, role=staff)
"""

import calendar
import asyncio
import io
import os
import secrets
from datetime import date, datetime
from functools import wraps
from html import escape

from flask import (Flask, flash, redirect, render_template, request,
                   abort, send_file, send_from_directory, session, url_for)

import db
import reports
from constants import (DAY_ABBR_MS, DESIGNATIONS, LEAVE_TYPES, REGIONS,
                       STATUS_CODES, STATUS_COLORS, STATUS_LABELS,
                       STATUS_TEXT_COLORS)
from supporting_docs import (build_telegram_supporting_doc,
                             get_absolute_supporting_doc_path,
                             is_allowed_image,
                             leave_type_requires_supporting_doc,
                             parse_supporting_doc)
from telegram_helpers import admin_chat_ids_from_env, leave_approval_markup
from workflow import (ANNUAL_LEAVE_NOTICE_DAYS, build_checkin_note,
                      parse_checkin_note)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv(
    "SESSION_COOKIE_SECURE", ""
).lower() in ("1", "true")
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_UPLOAD_MB", "5")) * 1024 * 1024


def _csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": _csrf_token}


@app.before_request
def validate_csrf():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    sent_token = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
    session_token = session.get("_csrf_token")
    if not session_token or sent_token != session_token:
        flash("Sesi borang tidak sah. Sila cuba semula.", "error")
        return redirect(request.referrer or url_for("login"))
    return None


def _save_supporting_doc(file_storage, leave_type, employee_id):
    if not file_storage or not file_storage.filename:
        return None
    if not is_allowed_image(file_storage.filename, file_storage.mimetype):
        raise ValueError("Hanya fail gambar JPG, PNG, atau WEBP dibenarkan.")
    return asyncio.run(
        _upload_supporting_doc_to_telegram(file_storage, leave_type, employee_id)
    )


async def _upload_supporting_doc_to_telegram(file_storage, leave_type, employee_id):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    admin_ids = admin_chat_ids_from_env()
    if not token or not admin_ids:
        raise ValueError(
            "Tetapan Telegram belum lengkap. Isi TELEGRAM_BOT_TOKEN dan "
            "ADMIN_TELEGRAM_IDS atau ADMIN_TELEGRAM_GROUP_IDS."
        )

    from telegram import Bot

    caption = (
        f"Simpanan bukti sokongan\n"
        f"Pekerja ID: {employee_id}\n"
        f"Jenis cuti: {leave_type}"
    )
    proof_stream = file_storage.stream
    try:
        proof_stream.seek(0)
    except Exception:
        pass

    bot = Bot(token=token)
    try:
        message = await bot.send_document(
            chat_id=admin_ids[0],
            document=proof_stream,
            caption=caption,
            filename=file_storage.filename or "proof.jpg",
        )
        if not message.document:
            raise ValueError("Telegram tidak memulangkan maklumat dokumen bukti.")
        document = message.document
        return build_telegram_supporting_doc(
            kind="document",
            file_id=document.file_id,
            file_unique_id=document.file_unique_id,
            chat_id=message.chat.id,
            message_id=message.message_id,
            file_name=file_storage.filename or "proof.jpg",
            mime_type=file_storage.mimetype or "image/jpeg",
        )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            "Gagal memuat naik gambar bukti ke Telegram. Sila cuba lagi."
        ) from exc
    finally:
        await bot.close()


def _build_leave_admin_message(leave_request):
    leave_label = STATUS_LABELS.get(
        leave_request["leave_type"], leave_request["leave_type"]
    )
    safe_name = escape(leave_request["full_name"])
    safe_region = escape(REGIONS.get(leave_request["region"], leave_request["region"]))
    safe_leave = escape(leave_label)
    safe_reason = escape(leave_request.get("reason") or "-")
    safe_support = "Ada" if leave_request.get("supporting_doc") else "Tiada"
    return (
        f"Permohonan cuti baharu (ID #{leave_request['id']})\n"
        f"<b>{safe_name}</b> - {safe_region}\n"
        f"Jenis: {safe_leave}\n"
        f"Tarikh: {leave_request['date_from']} hingga {leave_request['date_to']}\n"
        f"Bukti gambar: {safe_support}\n"
        f"Sebab: {safe_reason}\n\n"
        f"Lulus: /lulus {leave_request['id']}   Tolak: /tolak {leave_request['id']}"
    )


def _notify_admins_via_telegram(leave_request):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    admin_ids = admin_chat_ids_from_env()
    if not token or not admin_ids:
        return

    async def _send():
        from telegram import Bot

        bot = Bot(token=token)
        message = _build_leave_admin_message(leave_request)
        supporting_doc = parse_supporting_doc(leave_request.get("supporting_doc"))

        for chat_id in admin_ids:
            try:
                if supporting_doc and supporting_doc.get("storage") == "telegram":
                    media_kind = supporting_doc.get("kind")
                    if media_kind == "document":
                        await bot.send_document(
                            chat_id=chat_id,
                            document=supporting_doc["file_id"],
                            caption=message,
                            parse_mode="HTML",
                            reply_markup=leave_approval_markup(leave_request["id"]),
                        )
                    else:
                        await bot.send_photo(
                            chat_id=chat_id,
                            photo=supporting_doc["file_id"],
                            caption=message,
                            parse_mode="HTML",
                            reply_markup=leave_approval_markup(leave_request["id"]),
                        )
                elif leave_request.get("supporting_doc"):
                    try:
                        photo_path = get_absolute_supporting_doc_path(
                            leave_request["supporting_doc"]
                        )
                    except ValueError:
                        photo_path = None
                    if photo_path and os.path.exists(photo_path):
                        with open(photo_path, "rb") as proof_stream:
                            await bot.send_photo(
                                chat_id=chat_id,
                                photo=proof_stream,
                                caption=message,
                                parse_mode="HTML",
                                reply_markup=leave_approval_markup(
                                    leave_request["id"]
                                ),
                            )
                    else:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            parse_mode="HTML",
                            reply_markup=leave_approval_markup(leave_request["id"]),
                        )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode="HTML",
                        reply_markup=leave_approval_markup(leave_request["id"]),
                    )
            except Exception:
                continue
        await bot.close()

    try:
        asyncio.run(_send())
    except Exception:
        return


# ─── Auth helpers ─────────────────────────────────────────────────────────────

def login_required(role=None):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("login", next=request.full_path))
            if session.get("user_role") == "staff":
                emp_id = session.get("employee_id")
                emp = db.get_employee(emp_id) if emp_id else None
                if not emp or not emp.get("is_active"):
                    session.clear()
                    flash("Akaun pekerja tidak aktif. Hubungi admin.", "error")
                    return redirect(url_for("login"))
            if role and session.get("user_role") != role:
                if session.get("user_role") == "staff":
                    return redirect(url_for("staff_portal"))
                return redirect(url_for("dashboard"))
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


def admin_required(f):
    return login_required(role="admin")(f)


def staff_required(f):
    return login_required(role="staff")(f)


# ─── Utility ──────────────────────────────────────────────────────────────────

def _current_month():
    today = date.today()
    return today.year, today.month


def _parse_month(month_str):
    """Parse 'YYYY-MM' into (year, month) ints, default to current month."""
    try:
        y, m = month_str.split("-")
        return int(y), int(m)
    except Exception:
        return _current_month()


def _month_days(year, month):
    """Return number of days in the given month."""
    return calendar.monthrange(year, month)[1]


def _day_of_week(year, month, day):
    """Return Malay day-of-week abbreviation."""
    return DAY_ABBR_MS[date(year, month, day).weekday()]


# ─── Auth routes ──────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    # First-run: create admin if no admin exists
    if not db.admin_exists():
        admin_pw = os.getenv("ADMIN_PASSWORD", "").strip()
        if admin_pw and admin_pw != "admin123":
            db.create_user("admin", admin_pw, role="admin")
            flash("Akaun admin pertama telah diwujudkan. Sila log masuk.", "success")
        else:
            flash("Tetapkan ADMIN_PASSWORD yang kuat sebelum log masuk pertama.", "error")

    next_url = request.args.get("next") or request.form.get("next") or ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.verify_user(username, password)
        if user:
            session["user_id"] = user["id"]
            session["user_role"] = user["role"]
            session["username"] = user["username"]
            session["employee_id"] = user.get("employee_id")
            if user["role"] == "admin":
                return redirect(next_url or url_for("dashboard"))
            return redirect(next_url or url_for("staff_portal"))
        flash("Nama pengguna atau kata laluan tidak betul.", "error")
    return render_template("login.html", next_url=next_url)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/healthz")
def healthz():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


# ─── Admin: Dashboard ─────────────────────────────────────────────────────────

@app.route("/")
@admin_required
def dashboard():
    today = date.today()
    month_str = request.args.get("month", today.strftime("%Y-%m"))
    year, month = _parse_month(month_str)

    pending = db.count_pending_leaves()
    present_total = {r: db.count_present_today(r) for r in REGIONS}
    active_total = {r: len(db.get_employees(region=r, active_only=True)) for r in REGIONS}

    recent_leaves = db.get_leave_requests(status="pending", limit=5)

    return render_template("dashboard.html",
        today=today,
        pending=pending,
        present_total=present_total,
        active_total=active_total,
        recent_leaves=recent_leaves,
        regions=REGIONS,
        year=year,
        month=month,
        month_str=f"{year}-{month:02d}",
    )


# ─── Admin: Attendance grid ───────────────────────────────────────────────────

@app.route("/attendance/grid")
@admin_required
def attendance_grid():
    region = request.args.get("region", list(REGIONS)[0])
    month_str = request.args.get("month", date.today().strftime("%Y-%m"))
    year, month = _parse_month(month_str)
    num_days = _month_days(year, month)

    employees, grid = db.get_month_grid(region, year, month)
    ph_dates = db.get_public_holiday_dates(year, month)

    days = list(range(1, num_days + 1))
    day_names = [_day_of_week(year, month, d) for d in days]

    return render_template("attendance/grid.html",
        region=region,
        region_name=REGIONS.get(region, region),
        year=year, month=month,
        month_str=month_str,
        employees=employees,
        grid=grid,
        days=days,
        day_names=day_names,
        ph_dates=ph_dates,
        status_colors=STATUS_COLORS,
        status_text=STATUS_TEXT_COLORS,
        status_labels=STATUS_LABELS,
        regions=REGIONS,
        num_days=num_days,
    )


# ─── Admin: Attendance entry ──────────────────────────────────────────────────

@app.route("/attendance/entry", methods=["GET", "POST"])
@admin_required
def attendance_entry():
    region = request.args.get("region", list(REGIONS)[0])
    entry_date = request.args.get("date", date.today().isoformat())

    # Pre-load existing statuses for the selected date
    if request.method == "POST":
        entry_date = request.form.get("entry_date", entry_date)
        region = request.form.get("region", region)
    employees = db.get_employees(region=region, active_only=True)
    existing = {}
    for emp in employees:
        row = db.get_attendance(emp["id"], entry_date)
        existing[emp["id"]] = row["status"] if row else ""

    if request.method == "POST":
        saved = 0
        for emp in employees:
            status = request.form.get(f"status_{emp['id']}", "").strip().upper()
            if status in STATUS_CODES:
                db.upsert_attendance(emp["id"], entry_date, status,
                                     entered_by=session["username"])
                saved += 1
        flash(f"Kehadiran disimpan untuk {saved} pekerja pada {entry_date}.", "success")
        return redirect(url_for("attendance_entry",
                                region=region, date=entry_date))

    return render_template("attendance/entry.html",
        region=region,
        region_name=REGIONS.get(region, region),
        entry_date=entry_date,
        employees=employees,
        existing=existing,
        status_codes=sorted(STATUS_CODES),
        status_labels=STATUS_LABELS,
        regions=REGIONS,
    )


@app.route("/attendance/<int:emp_id>/<string:att_date>", methods=["GET", "POST"])
@admin_required
def attendance_edit(emp_id, att_date):
    emp = db.get_employee(emp_id)
    if not emp:
        flash("Pekerja tidak dijumpai.", "error")
        return redirect(url_for("attendance_entry"))

    current = db.get_attendance(emp_id, att_date)
    if request.method == "POST":
        status = request.form.get("status", "").strip().upper()
        if status in STATUS_CODES:
            db.upsert_attendance(emp_id, att_date, status,
                                entered_by=session["username"])
            flash("Kehadiran dikemaskini.", "success")
        return redirect(url_for("attendance_grid",
                                region=emp["region"],
                                month=att_date[:7]))

    return render_template("attendance/edit.html",
        emp=emp,
        att_date=att_date,
        current=current,
        status_codes=sorted(STATUS_CODES),
        status_labels=STATUS_LABELS,
    )


# ─── Admin: Leave management ──────────────────────────────────────────────────

@app.route("/leaves")
@admin_required
def leaves_list():
    status_filter = request.args.get("status", "")
    region_filter = request.args.get("region", "")
    leave_reqs = db.get_leave_requests(
        status=status_filter or None,
        region=region_filter or None,
    )
    return render_template("leaves/list.html",
        leave_reqs=leave_reqs,
        status_filter=status_filter,
        region_filter=region_filter,
        regions=REGIONS,
    )


@app.route("/leaves/<int:lr_id>")
@admin_required
def leave_detail(lr_id):
    lr = db.get_leave_request(lr_id)
    if not lr:
        flash("Permohonan tidak dijumpai.", "error")
        return redirect(url_for("leaves_list"))
    return render_template("leaves/detail.html", lr=lr,
                           status_labels=STATUS_LABELS)


async def _download_supporting_doc_from_telegram(stored_value):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    supporting_doc = parse_supporting_doc(stored_value)
    if not token or not supporting_doc or supporting_doc.get("storage") != "telegram":
        return None, None

    from telegram import Bot

    bot = Bot(token=token)
    try:
        telegram_file = await bot.get_file(supporting_doc["file_id"])
        payload = await telegram_file.download_as_bytearray()
        return bytes(payload), supporting_doc
    finally:
        await bot.close()


@app.route("/leaves/docs/<int:lr_id>")
@admin_required
def leave_supporting_doc(lr_id):
    lr = db.get_leave_request(lr_id)
    if not lr or not lr.get("supporting_doc"):
        abort(404)

    supporting_doc = parse_supporting_doc(lr["supporting_doc"])
    if supporting_doc and supporting_doc.get("storage") == "telegram":
        payload, metadata = asyncio.run(
            _download_supporting_doc_from_telegram(lr["supporting_doc"])
        )
        if not payload or not metadata:
            abort(404)
        return send_file(
            io.BytesIO(payload),
            mimetype=metadata.get("mime_type") or "image/jpeg",
            download_name=metadata.get("file_name") or "proof.jpg",
        )

    if supporting_doc and supporting_doc.get("storage") == "legacy_local":
        filepath = get_absolute_supporting_doc_path(supporting_doc["stored_name"])
        directory = os.path.dirname(filepath)
        filename = os.path.basename(filepath)
        return send_from_directory(directory, filename)

    abort(404)


@app.route("/leaves/<int:lr_id>/approve", methods=["POST"])
@admin_required
def leave_approve(lr_id):
    notes = request.form.get("reviewer_notes", "")
    try:
        db.approve_leave(lr_id, reviewed_by=session["username"], notes=notes)
        flash("Permohonan cuti diluluskan.", "success")
    except Exception as e:
        flash(f"Ralat: {e}", "error")
    return redirect(url_for("leave_detail", lr_id=lr_id))


@app.route("/leaves/<int:lr_id>/reject", methods=["POST"])
@admin_required
def leave_reject(lr_id):
    notes = request.form.get("reviewer_notes", "")
    try:
        db.reject_leave(lr_id, reviewed_by=session["username"], notes=notes)
        flash("Permohonan cuti ditolak.", "success")
    except Exception as e:
        flash(f"Ralat: {e}", "error")
    return redirect(url_for("leave_detail", lr_id=lr_id))


@app.route("/leaves/<int:lr_id>/delete", methods=["POST"])
@admin_required
def leave_delete(lr_id):
    db.delete_leave_request(lr_id)
    flash("Permohonan dihapuskan.", "success")
    return redirect(url_for("leaves_list"))


@app.route("/leaves/new", methods=["GET", "POST"])
@admin_required
def leave_new():
    employees = db.get_employees()
    if request.method == "POST":
        try:
            emp_id = int(request.form["employee_id"])
            leave_type = request.form["leave_type"]
            date_from = request.form["date_from"]
            date_to = request.form["date_to"]
            reason = request.form.get("reason", "").strip()
            supporting_doc = _save_supporting_doc(
                request.files.get("supporting_doc"),
                leave_type,
                emp_id,
            )
            if leave_type_requires_supporting_doc(leave_type) and not supporting_doc:
                raise ValueError("Sila muat naik gambar bukti untuk MC atau Cuti Kecemasan.")
            lr_id = db.insert_leave_request(
                emp_id,
                leave_type,
                date_from,
                date_to,
                reason,
                supporting_doc,
            )
            flash("Permohonan cuti dikemukakan.", "success")
            return redirect(url_for("leave_detail", lr_id=lr_id))
        except Exception as e:
            flash(f"Ralat: {e}", "error")
    return render_template("leaves/form.html",
        employees=employees,
        leave_types=LEAVE_TYPES,
        regions=REGIONS,
        status_labels=STATUS_LABELS,
        annual_leave_notice_days=ANNUAL_LEAVE_NOTICE_DAYS,
        absence_mode=False,
        today=date.today().isoformat(),
    )


# ─── Admin: Employees ─────────────────────────────────────────────────────────

@app.route("/employees")
@admin_required
def employees_list():
    region = request.args.get("region", "")
    show_inactive = request.args.get("show_inactive", "")
    emps = db.get_employees(
        region=region or None,
        active_only=not show_inactive,
    )
    return render_template("employees/list.html",
        employees=emps,
        region=region,
        show_inactive=show_inactive,
        regions=REGIONS,
    )


@app.route("/employees/new", methods=["GET", "POST"])
@admin_required
def employee_new():
    if request.method == "POST":
        try:
            emp_id = db.insert_employee(
                full_name=request.form["full_name"],
                designation=request.form["designation"],
                region=request.form["region"],
                ic_number=request.form.get("ic_number") or None,
                department=request.form.get("department") or None,
                telegram_id=request.form.get("telegram_id") or None,
                joined_date=request.form.get("joined_date") or None,
                al_entitlement=int(request.form.get("al_entitlement", 8)),
            )
            # Optionally create web login
            web_pw = request.form.get("web_password", "").strip()
            if web_pw:
                uname = request.form.get("username", "").strip().lower()
                if uname:
                    db.create_user(uname, web_pw, role="staff",
                                   employee_id=emp_id)
            flash("Pekerja berjaya ditambah.", "success")
            return redirect(url_for("employees_list"))
        except Exception as e:
            flash(f"Ralat: {e}", "error")
    return render_template("employees/form.html",
        emp=None,
        regions=REGIONS,
        designations=DESIGNATIONS,
        action_url=url_for("employee_new"),
    )


@app.route("/employees/<int:emp_id>/edit", methods=["GET", "POST"])
@admin_required
def employee_edit(emp_id):
    emp = db.get_employee(emp_id)
    if not emp:
        flash("Pekerja tidak dijumpai.", "error")
        return redirect(url_for("employees_list"))
    if request.method == "POST":
        try:
            db.update_employee(
                emp_id=emp_id,
                full_name=request.form["full_name"],
                designation=request.form["designation"],
                region=request.form["region"],
                ic_number=request.form.get("ic_number") or None,
                department=request.form.get("department") or None,
                telegram_id=request.form.get("telegram_id") or None,
                joined_date=request.form.get("joined_date") or None,
                al_entitlement=int(request.form.get("al_entitlement", 8)),
            )
            flash("Maklumat pekerja dikemaskini.", "success")
            return redirect(url_for("employees_list"))
        except Exception as e:
            flash(f"Ralat: {e}", "error")
    return render_template("employees/form.html",
        emp=emp,
        regions=REGIONS,
        designations=DESIGNATIONS,
        action_url=url_for("employee_edit", emp_id=emp_id),
    )


@app.route("/employees/<int:emp_id>/deactivate", methods=["POST"])
@admin_required
def employee_deactivate(emp_id):
    db.toggle_employee_active(emp_id, False)
    flash("Pekerja dinyahaktifkan.", "success")
    return redirect(url_for("employees_list"))


@app.route("/employees/<int:emp_id>/reactivate", methods=["POST"])
@admin_required
def employee_reactivate(emp_id):
    db.toggle_employee_active(emp_id, True)
    flash("Pekerja diaktifkan semula.", "success")
    return redirect(url_for("employees_list"))


# ─── Admin: Public Holidays ───────────────────────────────────────────────────

@app.route("/holidays")
@admin_required
def holidays_list():
    year = int(request.args.get("year", date.today().year))
    holidays = db.get_holidays(year)
    return render_template("holidays/list.html",
        holidays=holidays, year=year)


@app.route("/holidays/new", methods=["GET", "POST"])
@admin_required
def holiday_new():
    if request.method == "POST":
        try:
            db.insert_holiday(
                holiday_date=request.form["holiday_date"],
                name=request.form["name"],
                scope=request.form.get("scope", "national"),
            )
            flash("Cuti umum ditambah.", "success")
            return redirect(url_for("holidays_list"))
        except Exception as e:
            flash(f"Ralat: {e}", "error")
    return render_template("holidays/form.html", holiday=None)


@app.route("/holidays/<int:ph_id>/edit", methods=["GET", "POST"])
@admin_required
def holiday_edit(ph_id):
    holiday = db.get_holiday(ph_id)
    if not holiday:
        flash("Cuti umum tidak dijumpai.", "error")
        return redirect(url_for("holidays_list"))
    if request.method == "POST":
        try:
            db.update_holiday(
                ph_id=ph_id,
                holiday_date=request.form["holiday_date"],
                name=request.form["name"],
                scope=request.form.get("scope", "national"),
            )
            flash("Cuti umum dikemaskini.", "success")
            return redirect(url_for("holidays_list"))
        except Exception as e:
            flash(f"Ralat: {e}", "error")
    return render_template("holidays/form.html", holiday=holiday)


@app.route("/holidays/<int:ph_id>/delete", methods=["POST"])
@admin_required
def holiday_delete(ph_id):
    db.delete_holiday(ph_id)
    flash("Cuti umum dihapuskan.", "success")
    return redirect(url_for("holidays_list"))


@app.route("/holidays/bulk-apply", methods=["POST"])
@admin_required
def holiday_bulk_apply():
    h_date = request.form.get("holiday_date")
    h_name = request.form.get("name", "Cuti Umum")
    region = request.form.get("region", "")
    if not h_date:
        flash("Tarikh diperlukan.", "error")
        return redirect(url_for("holidays_list"))

    db.insert_holiday(h_date, h_name)
    employees = db.get_employees(region=region or None, active_only=True)
    for emp in employees:
        db.upsert_attendance(emp["id"], h_date, "PH",
                             notes=h_name, entered_by=session["username"])
    flash(f"PH ditanda untuk {len(employees)} pekerja pada {h_date}.", "success")
    return redirect(url_for("holidays_list"))


# ─── Reports ──────────────────────────────────────────────────────────────────

@app.route("/reports/internal.xlsx")
@admin_required
def report_internal_xlsx():
    region = request.args.get("region", list(REGIONS)[0])
    month_str = request.args.get("month", date.today().strftime("%Y-%m"))
    year, month = _parse_month(month_str)
    buf = reports.build_internal_xlsx(region, year, month)
    region_name = REGIONS.get(region, region).replace(" ", "_")
    filename = f"Laporan_Kehadiran_{region_name}_{year}-{month:02d}.xlsx"
    return send_file(buf, as_attachment=True,
                     download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/reports/internal/print")
@admin_required
def report_internal_print():
    region = request.args.get("region", list(REGIONS)[0])
    month_str = request.args.get("month", date.today().strftime("%Y-%m"))
    year, month = _parse_month(month_str)
    num_days = _month_days(year, month)
    employees, grid = db.get_month_grid(region, year, month)
    days = list(range(1, num_days + 1))
    day_names = [_day_of_week(year, month, d) for d in days]
    ph_dates = db.get_public_holiday_dates(year, month)

    return render_template("reports/internal.html",
        region=region,
        region_name=REGIONS.get(region, region),
        year=year, month=month,
        employees=employees,
        grid=grid,
        days=days,
        day_names=day_names,
        ph_dates=ph_dates,
        status_colors=STATUS_COLORS,
        status_labels=STATUS_LABELS,
        num_days=num_days,
        print_date=date.today().strftime("%d %B %Y"),
    )


@app.route("/reports/external/print")
@admin_required
def report_external_print():
    region = request.args.get("region", list(REGIONS)[0])
    month_str = request.args.get("month", date.today().strftime("%Y-%m"))
    year, month = _parse_month(month_str)
    num_days = _month_days(year, month)
    employees, grid = db.get_month_grid(region, year, month)
    days = list(range(1, num_days + 1))
    day_names = [_day_of_week(year, month, d) for d in days]
    ph_dates = db.get_public_holiday_dates(year, month)

    return render_template("reports/external.html",
        region=region,
        region_name=REGIONS.get(region, region),
        year=year,
        month=month,
        employees=employees,
        grid=grid,
        days=days,
        day_names=day_names,
        ph_dates=ph_dates,
        status_colors=STATUS_COLORS,
        status_labels=STATUS_LABELS,
        num_days=num_days,
        print_date=date.today().strftime("%d %B %Y"),
    )


# ─── Staff portal ─────────────────────────────────────────────────────────────

@app.route("/portal")
@staff_required
def staff_portal():
    emp_id = session.get("employee_id")
    if not emp_id:
        flash("Akaun tidak dikaitkan dengan pekerja. Hubungi admin.", "error")
        return redirect(url_for("login"))

    emp = db.get_employee(emp_id)
    if not emp or not emp.get("is_active"):
        session.clear()
        flash("Akaun pekerja tidak aktif. Hubungi admin.", "error")
        return redirect(url_for("login"))
    today = date.today()
    today_att = db.get_attendance(emp_id, today)
    today_att_meta = parse_checkin_note(today_att.get("notes")) if today_att else None

    year, month = today.year, today.month
    _, grid = db.get_month_grid(emp["region"], year, month)
    my_grid = grid.get(emp_id, {})
    num_days = _month_days(year, month)

    my_leaves = db.get_leave_requests(employee_id=emp_id, limit=10)

    days = list(range(1, num_days + 1))
    day_names = [_day_of_week(year, month, d) for d in days]

    return render_template("staff_portal.html",
        emp=emp,
        today=today,
        today_att=today_att,
        today_att_meta=today_att_meta,
        my_grid=my_grid,
        days=days,
        day_names=day_names,
        num_days=num_days,
        year=year, month=month,
        my_leaves=my_leaves,
        leave_types=LEAVE_TYPES,
        status_colors=STATUS_COLORS,
        status_text=STATUS_TEXT_COLORS,
        status_labels=STATUS_LABELS,
    )


@app.route("/portal/checkin", methods=["POST"])
@staff_required
def portal_checkin():
    emp_id = session.get("employee_id")
    if emp_id:
        today = date.today()
        existing = db.get_attendance(emp_id, today)
        if existing:
            label = STATUS_LABELS.get(existing["status"], existing["status"])
            flash(f"Kehadiran hari ini sudah direkod sebagai {label}.", "error")
        else:
            checkin = build_checkin_note(datetime.now())
            db.upsert_attendance(
                emp_id,
                today,
                "P",
                notes=checkin["note"],
                entered_by=session["username"],
            )
            flash(
                "Kehadiran hari ini telah direkodkan pada "
                f"{checkin['checkin_time']} ({checkin['timing_label']}).",
                "success",
            )
    return redirect(url_for("staff_portal"))


@app.route("/portal/leave/new", methods=["GET", "POST"])
@staff_required
def portal_leave_new():
    emp_id = session.get("employee_id")
    emp = db.get_employee(emp_id)
    if not emp or not emp.get("is_active"):
        session.clear()
        flash("Akaun pekerja tidak aktif. Hubungi admin.", "error")
        return redirect(url_for("login"))
    today = date.today()
    absence_mode = request.args.get("mode") == "absence"
    leave_types = [lt for lt in LEAVE_TYPES if lt in {"MC", "EML"}] if absence_mode else LEAVE_TYPES
    date_from_default = request.args.get("date_from", today.isoformat())
    date_to_default = request.args.get("date_to", today.isoformat())

    if request.method == "POST":
        try:
            leave_type = request.form["leave_type"]
            date_from = request.form["date_from"]
            date_to = request.form["date_to"]
            reason = request.form.get("reason", "").strip()
            supporting_doc = _save_supporting_doc(
                request.files.get("supporting_doc"),
                leave_type,
                emp_id,
            )
            if leave_type_requires_supporting_doc(leave_type) and not supporting_doc:
                raise ValueError("Sila muat naik gambar bukti untuk MC atau Cuti Kecemasan.")
            lr_id = db.insert_leave_request(
                emp_id,
                leave_type,
                date_from,
                date_to,
                reason,
                supporting_doc,
            )
            _notify_admins_via_telegram(db.get_leave_request(lr_id))
            flash("Permohonan cuti berjaya dihantar. Sila tunggu kelulusan.", "success")
            return redirect(url_for("staff_portal"))
        except Exception as e:
            flash(f"Ralat: {e}", "error")

    return render_template("leaves/form.html",
        emp=emp,
        leave_types=leave_types,
        is_staff=True,
        today=today.isoformat(),
        date_from_default=date_from_default,
        date_to_default=date_to_default,
        status_labels=STATUS_LABELS,
        annual_leave_notice_days=ANNUAL_LEAVE_NOTICE_DAYS,
        absence_mode=absence_mode,
    )


# ─── App entry point ──────────────────────────────────────────────────────────

def run_server():
    db.init_db()
    port = int(os.getenv("PORT", 8080))
    debug = os.getenv("FLASK_DEBUG", "").lower() in ("1", "true")
    if debug:
        app.run(host="0.0.0.0", port=port, debug=True)
    else:
        from waitress import serve
        print(f"Attendance System running on http://localhost:{port}")
        serve(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    run_server()
