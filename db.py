"""
db.py — Dual SQLite / PostgreSQL adapter for the attendance system.

SQLite is used locally (no DATABASE_URL set).
Set DATABASE_URL to a postgres:// URI to switch to PostgreSQL.
"""

import hashlib
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta

from constants import LEAVE_DEFAULTS, LEAVE_TYPES, REGIONS, STATUS_CODES
from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith("postgres")


# ─── Connection helpers ───────────────────────────────────────────────────────

def _pg_conn():
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def _sqlite_conn():
    db_path = os.getenv("SQLITE_PATH", "attendance.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def _get_conn():
    conn = _pg_conn() if USE_POSTGRES else _sqlite_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _to_pg(sql):
    return sql.replace("?", "%s")


def _run(conn, sql, params=()):
    """Execute a SQL statement and return the cursor."""
    cur = conn.cursor()
    final_sql = _to_pg(sql) if USE_POSTGRES else sql
    cur.execute(final_sql, params)
    return cur


def _fetchall(conn, sql, params=()):
    cur = _run(conn, sql, params)
    rows = cur.fetchall()
    if USE_POSTGRES:
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]
    return [dict(row) for row in rows]


def _fetchone(conn, sql, params=()):
    cur = _run(conn, sql, params)
    row = cur.fetchone()
    if row is None:
        return None
    if USE_POSTGRES:
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))
    return dict(row)


def _parse_iso_date(value, field_name):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except Exception as exc:
        raise ValueError(f"{field_name} tidak sah") from exc


# ─── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS employees (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL,
    ic_number     TEXT,
    designation   TEXT NOT NULL,
    department    TEXT,
    region        TEXT NOT NULL,
    telegram_id   TEXT UNIQUE,
    is_active     INTEGER NOT NULL DEFAULT 1,
    joined_date   TEXT,
    al_entitlement INTEGER NOT NULL DEFAULT 8,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_emp_region ON employees(region);
CREATE INDEX IF NOT EXISTS idx_emp_active ON employees(is_active);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'staff',
    employee_id   INTEGER,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS attendance (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id   INTEGER NOT NULL,
    record_date   TEXT NOT NULL,
    status        TEXT NOT NULL,
    notes         TEXT,
    entered_by    TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(employee_id, record_date)
);
CREATE INDEX IF NOT EXISTS idx_att_employee ON attendance(employee_id);
CREATE INDEX IF NOT EXISTS idx_att_date     ON attendance(record_date);
CREATE INDEX IF NOT EXISTS idx_att_status   ON attendance(status);

CREATE TABLE IF NOT EXISTS leave_requests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id     INTEGER NOT NULL,
    leave_type      TEXT NOT NULL,
    date_from       TEXT NOT NULL,
    date_to         TEXT NOT NULL,
    reason          TEXT,
    supporting_doc  TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    submitted_at    TEXT NOT NULL DEFAULT (datetime('now')),
    reviewed_by     TEXT,
    reviewed_at     TEXT,
    reviewer_notes  TEXT
);
CREATE INDEX IF NOT EXISTS idx_lr_employee ON leave_requests(employee_id);
CREATE INDEX IF NOT EXISTS idx_lr_status   ON leave_requests(status);

CREATE TABLE IF NOT EXISTS leave_entitlements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id   INTEGER NOT NULL,
    year          INTEGER NOT NULL,
    leave_type    TEXT NOT NULL,
    total_days    INTEGER NOT NULL,
    used_days     INTEGER NOT NULL DEFAULT 0,
    UNIQUE(employee_id, year, leave_type)
);

CREATE TABLE IF NOT EXISTS public_holidays (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    holiday_date  TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    scope         TEXT NOT NULL DEFAULT 'national',
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ph_date ON public_holidays(holiday_date);
"""

SCHEMA_PG = SCHEMA_SQLITE.replace(
    "INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"
).replace(
    "datetime('now')", "NOW()::text"
).replace(
    "INSERT OR REPLACE", "INSERT"
).replace(
    "INSERT OR IGNORE", "INSERT"
)


def init_db():
    schema = SCHEMA_PG if USE_POSTGRES else SCHEMA_SQLITE
    with _get_conn() as conn:
        for stmt in schema.split(";"):
            s = stmt.strip()
            if s:
                _run(conn, s)
    logger.info("DB initialised (backend=%s)", "postgres" if USE_POSTGRES else "sqlite")


# ─── Employees ────────────────────────────────────────────────────────────────

def insert_employee(full_name, designation, region, ic_number=None, department=None,
                    telegram_id=None, joined_date=None, al_entitlement=8):
    if region not in REGIONS:
        raise ValueError(f"Invalid region: {region}")
    with _get_conn() as conn:
        if USE_POSTGRES:
            cur = _run(conn, """
                INSERT INTO employees
                    (full_name, ic_number, designation, department,
                     region, telegram_id, joined_date, al_entitlement)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (full_name.strip(), ic_number, designation, department,
                  region, telegram_id, joined_date, al_entitlement))
            emp_id = cur.fetchone()[0]
        else:
            cur = _run(conn, """
                INSERT INTO employees
                    (full_name, ic_number, designation, department,
                     region, telegram_id, joined_date, al_entitlement)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (full_name.strip(), ic_number, designation, department,
                  region, telegram_id, joined_date, al_entitlement))
            emp_id = cur.lastrowid
    _init_leave_entitlements(emp_id, date.today().year)
    update_entitlement(emp_id, date.today().year, "AL", al_entitlement)
    return emp_id


def get_employees(region=None, active_only=True):
    clauses, params = [], []
    if region:
        clauses.append("region = ?")
        params.append(region)
    if active_only:
        clauses.append("is_active = 1")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _get_conn() as conn:
        return _fetchall(conn,
            f"SELECT * FROM employees {where} ORDER BY full_name",
            tuple(params))


def get_employee(emp_id):
    with _get_conn() as conn:
        return _fetchone(conn, "SELECT * FROM employees WHERE id = ?", (emp_id,))


def get_employee_by_telegram(telegram_id):
    with _get_conn() as conn:
        return _fetchone(conn,
            "SELECT * FROM employees WHERE telegram_id = ? AND is_active = 1",
            (str(telegram_id),))


def update_employee(emp_id, full_name, designation, region, ic_number=None,
                    department=None, telegram_id=None, joined_date=None,
                    al_entitlement=8):
    if region not in REGIONS:
        raise ValueError(f"Invalid region: {region}")
    with _get_conn() as conn:
        _run(conn, """
            UPDATE employees
            SET full_name=?, ic_number=?, designation=?, department=?,
                region=?, telegram_id=?, joined_date=?, al_entitlement=?
            WHERE id=?
        """, (full_name.strip(), ic_number, designation, department,
              region, telegram_id, joined_date, al_entitlement, emp_id))
    update_entitlement(emp_id, date.today().year, "AL", al_entitlement)


def toggle_employee_active(emp_id, active):
    with _get_conn() as conn:
        _run(conn, "UPDATE employees SET is_active=? WHERE id=?",
             (1 if active else 0, emp_id))
        _run(conn, "UPDATE users SET is_active=? WHERE employee_id=?",
             (1 if active else 0, emp_id))


def link_telegram(emp_id, telegram_id):
    with _get_conn() as conn:
        _run(conn, "UPDATE employees SET telegram_id=? WHERE id=?",
             (str(telegram_id), emp_id))


# ─── Users ────────────────────────────────────────────────────────────────────

def _hash_pw(password):
    return generate_password_hash(password)


def _legacy_hash_pw(password):
    return hashlib.sha256(password.encode()).hexdigest()


def _is_modern_hash(password_hash):
    return password_hash.startswith(("scrypt:", "pbkdf2:"))


def set_user_password(user_id, password):
    with _get_conn() as conn:
        _run(conn, "UPDATE users SET password_hash=? WHERE id=?",
             (_hash_pw(password), user_id))


def create_user(username, password, role="staff", employee_id=None):
    with _get_conn() as conn:
        _run(conn, """
            INSERT INTO users (username, password_hash, role, employee_id)
            VALUES (?, ?, ?, ?)
        """, (username.strip().lower(), _hash_pw(password), role, employee_id))


def verify_user(username, password):
    with _get_conn() as conn:
        row = _fetchone(conn,
            """
            SELECT u.*
            FROM users u
            LEFT JOIN employees e ON u.employee_id = e.id
            WHERE u.username=? AND u.is_active=1
              AND (u.role='admin' OR u.employee_id IS NULL OR e.is_active=1)
            """,
            (username.strip().lower(),))
    if row:
        stored_hash = row["password_hash"]
        is_valid = False
        needs_upgrade = False
        if _is_modern_hash(stored_hash):
            is_valid = check_password_hash(stored_hash, password)
        else:
            is_valid = stored_hash == _legacy_hash_pw(password)
            needs_upgrade = is_valid
        if is_valid:
            if needs_upgrade:
                set_user_password(row["id"], password)
            return row
    return None


def get_user_by_id(user_id):
    with _get_conn() as conn:
        return _fetchone(conn, "SELECT * FROM users WHERE id=?", (user_id,))


def admin_exists():
    with _get_conn() as conn:
        return _fetchone(conn,
            "SELECT 1 FROM users WHERE role='admin' LIMIT 1") is not None


# ─── Public Holidays ──────────────────────────────────────────────────────────

def insert_holiday(holiday_date, name, scope="national"):
    with _get_conn() as conn:
        if USE_POSTGRES:
            _run(conn, """
                INSERT INTO public_holidays (holiday_date, name, scope)
                VALUES (%s, %s, %s)
                ON CONFLICT (holiday_date) DO UPDATE SET
                    name=EXCLUDED.name,
                    scope=EXCLUDED.scope
            """, (str(holiday_date), name.strip(), scope))
        else:
            _run(conn,
                "INSERT OR REPLACE INTO public_holidays (holiday_date, name, scope) VALUES (?,?,?)",
                (str(holiday_date), name.strip(), scope))


def update_holiday(ph_id, holiday_date, name, scope="national"):
    with _get_conn() as conn:
        _run(conn, """
            UPDATE public_holidays
            SET holiday_date=?, name=?, scope=?
            WHERE id=?
        """, (str(holiday_date), name.strip(), scope, ph_id))


def get_holidays(year=None):
    if year:
        with _get_conn() as conn:
            return _fetchall(conn,
                "SELECT * FROM public_holidays WHERE holiday_date LIKE ? ORDER BY holiday_date",
                (f"{year}-%",))
    with _get_conn() as conn:
        return _fetchall(conn,
            "SELECT * FROM public_holidays ORDER BY holiday_date")


def get_holiday(ph_id):
    with _get_conn() as conn:
        return _fetchone(conn, "SELECT * FROM public_holidays WHERE id=?", (ph_id,))


def delete_holiday(ph_id):
    with _get_conn() as conn:
        _run(conn, "DELETE FROM public_holidays WHERE id=?", (ph_id,))


def get_public_holiday_dates(year, month):
    prefix = f"{year}-{month:02d}"
    with _get_conn() as conn:
        rows = _fetchall(conn,
            "SELECT holiday_date FROM public_holidays WHERE holiday_date LIKE ?",
            (f"{prefix}-%",))
    return {r["holiday_date"] for r in rows}


# ─── Attendance ───────────────────────────────────────────────────────────────

def upsert_attendance(employee_id, record_date, status, notes=None, entered_by=None):
    if status not in STATUS_CODES:
        raise ValueError(f"Invalid status: {status}")
    record_date = str(record_date)
    if USE_POSTGRES:
        sql = """
            INSERT INTO attendance
                (employee_id, record_date, status, notes, entered_by, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW()::text)
            ON CONFLICT (employee_id, record_date)
            DO UPDATE SET status=EXCLUDED.status, notes=EXCLUDED.notes,
                          entered_by=EXCLUDED.entered_by, updated_at=NOW()::text
        """
    else:
        sql = """
            INSERT INTO attendance
                (employee_id, record_date, status, notes, entered_by, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(employee_id, record_date) DO UPDATE SET
                status=excluded.status, notes=excluded.notes,
                entered_by=excluded.entered_by, updated_at=datetime('now')
        """
    with _get_conn() as conn:
        _run(conn, sql, (employee_id, record_date, status, notes, entered_by))


def get_attendance(employee_id, record_date):
    with _get_conn() as conn:
        return _fetchone(conn,
            "SELECT * FROM attendance WHERE employee_id=? AND record_date=?",
            (employee_id, str(record_date)))


def delete_attendance_by_leave(leave_id):
    tag = f"leave_req:{leave_id}"
    with _get_conn() as conn:
        _run(conn, "DELETE FROM attendance WHERE notes=?", (tag,))


def get_month_grid(region, year, month):
    """Returns (employees list, grid dict {emp_id: {day_int: status}})."""
    employees = get_employees(region=region, active_only=True)
    if not employees:
        return employees, {}

    date_prefix = f"{year}-{month:02d}"
    emp_ids = tuple(e["id"] for e in employees)
    placeholder = ",".join(["?"] * len(emp_ids))

    with _get_conn() as conn:
        rows = _fetchall(conn, f"""
            SELECT employee_id, record_date, status
            FROM attendance
            WHERE record_date LIKE ? AND employee_id IN ({placeholder})
        """, (f"{date_prefix}-%", *emp_ids))

    grid = {e["id"]: {} for e in employees}
    for row in rows:
        day = int(row["record_date"].split("-")[2])
        grid[row["employee_id"]][day] = row["status"]

    return employees, grid


def get_month_summary(region, year, month):
    employees, grid = get_month_grid(region, year, month)
    summary = []
    for emp in employees:
        counts = {s: 0 for s in STATUS_CODES}
        for status in grid.get(emp["id"], {}).values():
            if status in counts:
                counts[status] += 1
        summary.append({**emp, **counts})
    return summary


# ─── Leave Requests ───────────────────────────────────────────────────────────

def insert_leave_request(employee_id, leave_type, date_from, date_to,
                         reason=None, supporting_doc=None):
    if leave_type not in LEAVE_TYPES:
        raise ValueError("Jenis cuti tidak sah")
    start_date = _parse_iso_date(date_from, "Tarikh mula")
    end_date = _parse_iso_date(date_to, "Tarikh akhir")
    if end_date < start_date:
        raise ValueError("Tarikh akhir tidak boleh lebih awal dari tarikh mula")
    with _get_conn() as conn:
        if USE_POSTGRES:
            cur = _run(conn, """
                INSERT INTO leave_requests
                    (employee_id, leave_type, date_from, date_to, reason, supporting_doc)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (employee_id, leave_type, start_date.isoformat(),
                  end_date.isoformat(), reason, supporting_doc))
            return cur.fetchone()[0]
        cur = _run(conn, """
            INSERT INTO leave_requests
                (employee_id, leave_type, date_from, date_to, reason, supporting_doc)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (employee_id, leave_type, start_date.isoformat(),
              end_date.isoformat(), reason, supporting_doc))
        return cur.lastrowid


def get_leave_requests(status=None, region=None, year=None, month=None,
                       employee_id=None, limit=100):
    clauses, params = [], []
    if status:
        clauses.append("lr.status = ?")
        params.append(status)
    if region:
        clauses.append("e.region = ?")
        params.append(region)
    if employee_id:
        clauses.append("lr.employee_id = ?")
        params.append(employee_id)
    if year and month:
        month_start = date(year, month, 1).isoformat()
        next_month = date(year + (month // 12), (month % 12) + 1, 1)
        month_end = (next_month - timedelta(days=1)).isoformat()
        clauses.append("lr.date_from <= ? AND lr.date_to >= ?")
        params.extend([month_end, month_start])
    elif year:
        year_start = date(year, 1, 1).isoformat()
        year_end = date(year, 12, 31).isoformat()
        clauses.append("lr.date_from <= ? AND lr.date_to >= ?")
        params.extend([year_end, year_start])
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _get_conn() as conn:
        return _fetchall(conn, f"""
            SELECT lr.*, e.full_name, e.designation, e.region
            FROM leave_requests lr
            JOIN employees e ON lr.employee_id = e.id
            {where}
            ORDER BY lr.submitted_at DESC
            LIMIT ?
        """, tuple(params) + (limit,))


def get_leave_request(lr_id):
    with _get_conn() as conn:
        return _fetchone(conn, """
            SELECT lr.*, e.full_name, e.designation, e.region, e.telegram_id
            FROM leave_requests lr
            JOIN employees e ON lr.employee_id = e.id
            WHERE lr.id = ?
        """, (lr_id,))


def approve_leave(lr_id, reviewed_by, notes=None):
    lr = get_leave_request(lr_id)
    if not lr:
        raise ValueError("Leave request not found")
    if lr["status"] == "approved":
        raise ValueError("Leave request already approved")
    if lr["status"] == "rejected":
        raise ValueError("Leave request already rejected")

    d = date.fromisoformat(lr["date_from"])
    end = date.fromisoformat(lr["date_to"])
    tag = f"leave_req:{lr_id}"
    days_written = 0
    while d <= end:
        upsert_attendance(lr["employee_id"], d, lr["leave_type"],
                         notes=tag, entered_by=reviewed_by)
        d += timedelta(days=1)
        days_written += 1

    adjust_used_days(lr["employee_id"],
                     date.fromisoformat(lr["date_from"]).year,
                     lr["leave_type"], days_written)

    with _get_conn() as conn:
        if USE_POSTGRES:
            _run(conn, """
                UPDATE leave_requests
                SET status='approved', reviewed_by=%s, reviewed_at=NOW()::text,
                    reviewer_notes=%s
                WHERE id=%s
            """, (reviewed_by, notes, lr_id))
        else:
            _run(conn, """
                UPDATE leave_requests
                SET status='approved', reviewed_by=?, reviewed_at=datetime('now'),
                    reviewer_notes=?
                WHERE id=?
            """, (reviewed_by, notes, lr_id))


def reject_leave(lr_id, reviewed_by, notes=None):
    lr = get_leave_request(lr_id)
    if not lr:
        raise ValueError("Leave request not found")
    if lr["status"] == "rejected":
        raise ValueError("Leave request already rejected")

    if lr["status"] == "approved":
        d = date.fromisoformat(lr["date_from"])
        end = date.fromisoformat(lr["date_to"])
        days = (end - d).days + 1
        adjust_used_days(lr["employee_id"],
                         date.fromisoformat(lr["date_from"]).year,
                         lr["leave_type"], -days)
        delete_attendance_by_leave(lr_id)

    with _get_conn() as conn:
        if USE_POSTGRES:
            _run(conn, """
                UPDATE leave_requests
                SET status='rejected', reviewed_by=%s, reviewed_at=NOW()::text,
                    reviewer_notes=%s
                WHERE id=%s
            """, (reviewed_by, notes, lr_id))
        else:
            _run(conn, """
                UPDATE leave_requests
                SET status='rejected', reviewed_by=?, reviewed_at=datetime('now'),
                    reviewer_notes=?
                WHERE id=?
            """, (reviewed_by, notes, lr_id))


def delete_leave_request(lr_id):
    with _get_conn() as conn:
        _run(conn, "DELETE FROM leave_requests WHERE id=? AND status='pending'",
             (lr_id,))


# ─── Leave Entitlements ───────────────────────────────────────────────────────

def _init_leave_entitlements(emp_id, year):
    with _get_conn() as conn:
        for ltype, total in LEAVE_DEFAULTS.items():
            if USE_POSTGRES:
                _run(conn, """
                    INSERT INTO leave_entitlements
                        (employee_id, year, leave_type, total_days)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (employee_id, year, leave_type) DO NOTHING
                """, (emp_id, year, ltype, total))
            else:
                _run(conn, """
                    INSERT OR IGNORE INTO leave_entitlements
                        (employee_id, year, leave_type, total_days)
                    VALUES (?, ?, ?, ?)
                """, (emp_id, year, ltype, total))


def get_entitlements(emp_id, year):
    with _get_conn() as conn:
        rows = _fetchall(conn, """
            SELECT leave_type, total_days, used_days
            FROM leave_entitlements
            WHERE employee_id=? AND year=?
        """, (emp_id, year))
    return {r["leave_type"]: r for r in rows}


def adjust_used_days(emp_id, year, leave_type, delta):
    _init_leave_entitlements(emp_id, year)
    with _get_conn() as conn:
        _run(conn, """
            UPDATE leave_entitlements
            SET used_days = MAX(0, used_days + ?)
            WHERE employee_id=? AND year=? AND leave_type=?
        """, (delta, emp_id, year, leave_type))


def update_entitlement(emp_id, year, leave_type, total_days):
    _init_leave_entitlements(emp_id, year)
    with _get_conn() as conn:
        _run(conn, """
            UPDATE leave_entitlements SET total_days=?
            WHERE employee_id=? AND year=? AND leave_type=?
        """, (total_days, emp_id, year, leave_type))


# ─── Dashboard helpers ────────────────────────────────────────────────────────

def count_pending_leaves():
    with _get_conn() as conn:
        row = _fetchone(conn,
            "SELECT COUNT(*) AS cnt FROM leave_requests WHERE status='pending'")
    return int((row or {}).get("cnt", 0))


def count_present_today(region=None):
    today = str(date.today())
    clauses = ["a.record_date=?", "a.status='P'"]
    params = [today]
    if region:
        clauses.append("e.region=?")
        params.append(region)
    where = "WHERE " + " AND ".join(clauses)
    with _get_conn() as conn:
        row = _fetchone(conn, f"""
            SELECT COUNT(*) AS cnt FROM attendance a
            JOIN employees e ON a.employee_id=e.id
            {where}
        """, tuple(params))
    return int((row or {}).get("cnt", 0))
