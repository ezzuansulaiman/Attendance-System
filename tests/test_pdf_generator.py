import pytest

from services.pdf_generator import PDF_COPY, build_monthly_attendance_pdf


def _sample_report() -> dict:
    return {
        "company_name": "KHSAR",
        "site_name": "Sepang Region",
        "year": 2026,
        "month": 2,
        "days_in_month": 28,
        "period_label": "February 2026",
        "generated_at": "07 Apr 2026 16:00",
        "rows": [
            {
                "worker_name": "Worker One With A Long Name",
                "employee_code": "EMP001",
                "site_name": "Sepang",
                "days": ["P", "P"] + [""] * 29,
                "present_days": 2,
                "completed_days": 2,
            }
        ],
    }


def test_pdf_copy_uses_professional_report_labels() -> None:
    assert PDF_COPY["eyebrow"] == "MONTHLY ATTENDANCE"
    assert PDF_COPY["title"] == "Attendance Report"
    assert PDF_COPY["footer_label"] == "Attendance Report"
    assert PDF_COPY["header_generated_label"] == "Generated On"
    assert PDF_COPY["metadata_labels"] == ("Company", "Site", "Period")
    assert "summary_labels" not in PDF_COPY

    rendered_copy = " | ".join(
        [
            PDF_COPY["eyebrow"],
            PDF_COPY["title"],
            PDF_COPY["header_generated_label"],
            PDF_COPY["footer_label"],
            *PDF_COPY["metadata_labels"],
        ]
    )

    assert "ATTENDANCE CLAIM SUBMISSION" not in rendered_copy
    assert "Prepared for client submission" not in rendered_copy
    assert "Computer generated report. No signature is required." not in rendered_copy
    assert "Monthly attendance submission" not in rendered_copy
    assert "Professional monthly workforce attendance register" not in rendered_copy


def test_build_monthly_attendance_pdf_returns_content_without_summary() -> None:
    pdf_bytes = build_monthly_attendance_pdf(report=_sample_report())

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


def test_build_monthly_attendance_pdf_accepts_existing_report_shape_with_summary() -> None:
    report = _sample_report()
    report["summary"] = {
        "total_workers": 1,
        "total_present_days": 2,
        "total_completed_days": 2,
        "average_present_days": 2,
        "completion_rate": 100,
    }

    pdf_bytes = build_monthly_attendance_pdf(report=report)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


@pytest.mark.parametrize(
    ("field_name", "row_scoped"),
    [
        ("worker_name", True),
        ("employee_code", True),
        ("company_name", False),
        ("site_name", False),
    ],
)
def test_build_monthly_attendance_pdf_handles_long_unbroken_text_fields(
    field_name: str,
    row_scoped: bool,
) -> None:
    report = _sample_report()
    long_value = "X" * 5000

    if row_scoped:
        report["rows"][0][field_name] = long_value
    else:
        report[field_name] = long_value

    pdf_bytes = build_monthly_attendance_pdf(report=report)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000
