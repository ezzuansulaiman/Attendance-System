from __future__ import annotations

import zipfile
from io import BytesIO

from services.excel_generator import build_monthly_attendance_excel


def test_build_monthly_attendance_excel_returns_valid_workbook() -> None:
    excel_bytes = build_monthly_attendance_excel(
        report={
            "company_name": "KHSAR",
            "site_name": "Sepang",
            "year": 2026,
            "month": 2,
            "days_in_month": 28,
            "period_label": "February 2026",
            "generated_at": "07 Apr 2026 16:00",
            "summary": {
                "total_workers": 1,
                "total_present_days": 2,
                "total_completed_days": 2,
                "average_present_days": 2,
                "completion_rate": 100,
            },
            "rows": [
                {
                    "worker_name": "Worker One",
                    "employee_code": "EMP001",
                    "site_name": "Sepang",
                    "days": ["P", "P"] + [""] * 29,
                    "present_days": 2,
                    "completed_days": 2,
                }
            ],
            "detail_rows": [
                {
                    "attendance_date": "2026-02-01",
                    "weekday": "Sun",
                    "worker_name": "Worker One",
                    "employee_code": "EMP001",
                    "site_name": "Sepang",
                    "status": "Present",
                    "check_in": "2026-02-01 08:00",
                    "check_out": "2026-02-01 17:00",
                    "notes": "-",
                }
            ],
        }
    )

    assert excel_bytes.startswith(b"PK")

    with zipfile.ZipFile(BytesIO(excel_bytes)) as workbook:
        assert "[Content_Types].xml" in workbook.namelist()
        workbook_xml = workbook.read("xl/workbook.xml").decode("utf-8")
        summary_sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        matrix_sheet = workbook.read("xl/worksheets/sheet2.xml").decode("utf-8")
        detail_sheet = workbook.read("xl/worksheets/sheet3.xml").decode("utf-8")

    assert 'name="Summary"' in workbook_xml
    assert 'name="Monthly Register"' in workbook_xml
    assert 'name="Attendance Detail"' in workbook_xml
    assert "MONTHLY ATTENDANCE REPORT" in summary_sheet
    assert "Submission Notes" not in summary_sheet
    assert "Prepared for client submission and internal verification." not in summary_sheet
    assert "Monthly Attendance Register" in matrix_sheet
    assert "Detailed Attendance Log" not in detail_sheet
