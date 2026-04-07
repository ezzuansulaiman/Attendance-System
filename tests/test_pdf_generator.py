from services.pdf_generator import PDF_COPY, build_monthly_attendance_pdf


def test_pdf_copy_uses_minimal_corporate_labels() -> None:
    assert PDF_COPY["title"] == "Monthly Attendance Report"
    assert PDF_COPY["footer_label"] == "Attendance Report"
    assert PDF_COPY["metadata_labels"] == ("Company", "Name", "Period", "Generated On")
    assert PDF_COPY["summary_labels"] == (
        "Workers",
        "Present Days",
        "Checked-Out Days",
        "Avg. Present Days",
        "Completion Rate",
    )

    rendered_copy = " | ".join(
        [
            str(PDF_COPY["title"]),
            str(PDF_COPY["footer_label"]),
            *PDF_COPY["metadata_labels"],
            *PDF_COPY["summary_labels"],
        ]
    )

    assert "ATTENDANCE CLAIM SUBMISSION" not in rendered_copy
    assert "Prepared for client submission" not in rendered_copy
    assert "Computer generated report. No signature is required." not in rendered_copy
    assert "Monthly attendance submission" not in rendered_copy


def test_build_monthly_attendance_pdf_returns_content() -> None:
    pdf_bytes = build_monthly_attendance_pdf(
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
        },
    )

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000
