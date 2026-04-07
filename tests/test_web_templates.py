from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from fastapi import Request

from web.app import create_app
from web.dependencies import templates


def _request_for_path(path: str) -> Request:
    app = create_app()
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "app": app,
        "session": {"is_admin": True, "csrf_token": "test-token"},
    }
    return Request(scope)


def _render(template_name: str, path: str, **context: object) -> str:
    template = templates.get_template(template_name)
    return template.render(request=_request_for_path(path), **context)


def test_dashboard_template_renders_primary_actions() -> None:
    site = SimpleNamespace(id=1, name="Sepang")
    worker = SimpleNamespace(full_name="Worker One", site=site)
    leave = SimpleNamespace(
        id=1,
        worker=worker,
        leave_type="annual",
        start_date=date(2026, 4, 8),
        end_date=date(2026, 4, 9),
        status="pending",
    )
    html = _render(
        "dashboard.html",
        "/",
        summary={"total_workers": 3, "checked_in": 2, "checked_out": 1, "pending_leaves": 1},
        today=date(2026, 4, 7),
        recent_records=[],
        leave_requests=[leave],
        sites=[site],
        selected_site_id=1,
    )

    assert "Manage Attendance" in html
    assert "Current Excel" in html
    assert "/leaves/1/approve" in html
    assert 'target="_blank"' not in html
    assert ' download' not in html


def test_attendance_template_renders_submission_actions() -> None:
    site = SimpleNamespace(id=1, name="Sepang")
    worker = SimpleNamespace(id=1, full_name="Worker One", employee_code="EMP001", site=site)
    html = _render(
        "attendance.html",
        "/attendance",
        error=None,
        record=None,
        attendance_grid={
            "days": [{"day": 1, "weekday_label": "Mon", "is_weekend": False}],
            "rows": [
                {
                    "worker": worker,
                    "cells": [
                        {
                            "record": None,
                            "leave_request": None,
                            "day": 1,
                            "date_iso": "2026-04-01",
                            "status_class": "is-empty",
                            "symbol": "-",
                            "has_note": False,
                            "status_label": "Empty",
                            "time_summary": "",
                            "day_label": "1 Mon",
                            "is_weekend": False,
                            "entry_mode": "attendance",
                            "notes_value": "",
                            "leave_locked": False,
                            "leave_message": "",
                        }
                    ],
                    "present_days": 0,
                    "completed_days": 0,
                }
            ],
        },
        records=[],
        workers=[worker],
        sites=[site],
        selected_month=4,
        selected_year=2026,
        selected_site_id=1,
        form_data={},
    )

    assert "Submission PDF" in html
    assert "Submission Excel" in html
    assert "Monthly Grid" in html
    assert "Spreadsheet-style editing" in html
    assert "grid-checkin-1-1" in html
    assert "Annual Leave" in html
    assert "MC" in html
    assert "Public Holiday" in html
    assert "EMP001" in html
    assert "/reports/monthly" in html
    assert "site_id=1" in html
    assert 'target="_blank"' not in html
    assert ' download' not in html


def test_attendance_template_renders_leave_grid_cells() -> None:
    site = SimpleNamespace(id=1, name="Sepang")
    worker = SimpleNamespace(id=1, full_name="Worker One", employee_code="EMP001", site=site)
    html = _render(
        "attendance.html",
        "/attendance",
        error=None,
        record=None,
        attendance_grid={
            "days": [{"day": 2, "weekday_label": "Tue", "is_weekend": False}],
            "rows": [
                {
                    "worker": worker,
                    "cells": [
                        {
                            "record": None,
                            "leave_request": SimpleNamespace(id=9, leave_type="mc"),
                            "day": 2,
                            "date_iso": "2026-04-02",
                            "status_class": "is-leave is-mc",
                            "symbol": "MC",
                            "has_note": True,
                            "status_label": "Cuti Sakit",
                            "time_summary": "Approved leave",
                            "day_label": "2 Tue",
                            "is_weekend": False,
                            "entry_mode": "mc",
                            "notes_value": "Medical leave",
                            "leave_locked": False,
                            "leave_message": "",
                        }
                    ],
                    "present_days": 0,
                    "completed_days": 0,
                }
            ],
        },
        records=[],
        workers=[worker],
        sites=[site],
        selected_month=4,
        selected_year=2026,
        selected_site_id=1,
        form_data={},
    )

    assert "Cuti Sakit" in html
    assert "Approved leave" in html
    assert "attendance/grid/save" in html


def test_workers_sites_and_leaves_templates_render_navigation_actions() -> None:
    site = SimpleNamespace(id=1, name="Sepang")
    worker = SimpleNamespace(
        id=1,
        full_name="Worker One",
        telegram_user_id=12345,
        ic_number="901010-10-1010",
        employee_code="EMP001",
        site=site,
        site_id=1,
        is_active=True,
    )
    leave = SimpleNamespace(
        id=1,
        worker=worker,
        leave_type="annual",
        start_date=date(2026, 4, 8),
        end_date=date(2026, 4, 9),
        reason="Family matter",
        telegram_file_id=None,
        status="pending",
    )

    workers_html = _render(
        "workers.html",
        "/workers",
        error=None,
        worker=None,
        workers=[worker],
        sites=[site],
    )
    sites_html = _render(
        "sites.html",
        "/sites",
        error=None,
        site=None,
        sites=[site],
    )
    leaves_html = _render(
        "leaves.html",
        "/leaves",
        error=None,
        leaves=[leave],
        sites=[site],
        selected_site_id=1,
    )

    assert "Create Worker" in workers_html
    assert "/workers/1/edit" in workers_html
    assert "Create Site" in sites_html
    assert "/sites/1/edit" in sites_html
    assert "Apply Filter" in leaves_html
    assert "/leaves/1/reject" in leaves_html
