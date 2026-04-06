from services.pdf_generator import build_monthly_attendance_pdf


def test_build_monthly_attendance_pdf_returns_content() -> None:
    pdf_bytes = build_monthly_attendance_pdf(
        company_name="KHSAR - Sepang",
        year=2026,
        month=2,
        rows=[
            {
                "worker_name": "Worker One",
                "employee_code": "EMP001",
                "days": ["P", "P"] + [""] * 29,
            }
        ],
    )

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000
