from __future__ import annotations

import calendar
import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)


def _build_styles() -> dict[str, ParagraphStyle]:
    sample_styles = getSampleStyleSheet()
    return {
        "eyebrow": ParagraphStyle(
            "ReportEyebrow",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=colors.HexColor("#6b7280"),
            leading=10,
            alignment=TA_LEFT,
        ),
        "title": ParagraphStyle(
            "ReportTitle",
            parent=sample_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=sample_styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#475569"),
            alignment=TA_LEFT,
        ),
        "meta_label": ParagraphStyle(
            "MetaLabel",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#64748b"),
            alignment=TA_LEFT,
        ),
        "meta_value": ParagraphStyle(
            "MetaValue",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_LEFT,
        ),
        "signature_label": ParagraphStyle(
            "SignatureLabel",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#334155"),
            alignment=TA_CENTER,
        ),
    }


def _build_metadata_table(
    *,
    company_name: str,
    year: int,
    month: int,
    styles: dict[str, ParagraphStyle],
) -> Table:
    period_label = f"{calendar.month_name[month]} {year}"
    generated_at = datetime.now().strftime("%d %b %Y %H:%M")
    metadata_rows = [
        [
            Paragraph("COMPANY", styles["meta_label"]),
            Paragraph("REPORT PERIOD", styles["meta_label"]),
            Paragraph("GENERATED", styles["meta_label"]),
        ],
        [
            Paragraph(company_name, styles["meta_value"]),
            Paragraph(period_label, styles["meta_value"]),
            Paragraph(generated_at, styles["meta_value"]),
        ],
    ]
    metadata_table = Table(metadata_rows, colWidths=[88 * mm, 55 * mm, 45 * mm])
    metadata_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return metadata_table


def _build_attendance_table(
    *,
    year: int,
    month: int,
    rows: list[dict[str, Any]],
) -> Table:
    days_header = ["No", "Employee Name", "Code"] + [str(day) for day in range(1, 32)]
    table_data: list[list[str]] = [days_header]

    for index, row in enumerate(rows, start=1):
        table_data.append(
            [
                str(index),
                str(row["worker_name"]),
                str(row["employee_code"]),
                *[str(value) for value in row["days"]],
            ]
        )

    column_widths = [20, 145, 52] + [14.8] * 31
    table = Table(table_data, colWidths=column_widths, repeatRows=1)

    style_commands: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16324f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 6.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#94a3b8")),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 6.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("LEFTPADDING", (1, 1), (1, -1), 5),
    ]

    for row_index in range(1, len(table_data)):
        row_background = "#ffffff" if row_index % 2 else "#f8fafc"
        style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor(row_background)))

    for day in range(1, 32):
        column_index = 2 + day
        if day > calendar.monthrange(year, month)[1]:
            style_commands.append(("BACKGROUND", (column_index, 0), (column_index, -1), colors.HexColor("#e5e7eb")))
            style_commands.append(("TEXTCOLOR", (column_index, 1), (column_index, -1), colors.HexColor("#94a3b8")))
            continue
        weekday = calendar.weekday(year, month, day)
        if weekday >= 5:
            style_commands.append(("BACKGROUND", (column_index, 0), (column_index, -1), colors.HexColor("#edf2f7")))

    table.setStyle(TableStyle(style_commands))
    return table


def _build_signatures(styles: dict[str, ParagraphStyle]) -> Table:
    signature_table = Table(
        [
            [
                Paragraph("Prepared By", styles["signature_label"]),
                Paragraph("Checked By", styles["signature_label"]),
                Paragraph("Verified By", styles["signature_label"]),
            ],
            [
                "\n\n____________________________",
                "\n\n____________________________",
                "\n\n____________________________",
            ],
            [
                "Name:",
                "Name:",
                "Name:",
            ],
            [
                "Date:",
                "Date:",
                "Date:",
            ],
        ],
        colWidths=[85 * mm, 85 * mm, 85 * mm],
    )
    signature_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#334155")),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return signature_table


def _draw_footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
    canvas.line(document.leftMargin, 11 * mm, PAGE_WIDTH - document.rightMargin, 11 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(document.leftMargin, 7 * mm, "Monthly attendance submission")
    canvas.drawRightString(PAGE_WIDTH - document.rightMargin, 7 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def build_monthly_attendance_pdf(
    *,
    company_name: str,
    year: int,
    month: int,
    rows: list[dict[str, Any]],
) -> bytes:
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=16 * mm,
        title=f"Attendance Submission - {calendar.month_name[month]} {year}",
    )
    styles = _build_styles()

    story = [
        Paragraph("ATTENDANCE CLAIM SUBMISSION", styles["eyebrow"]),
        Spacer(1, 3),
        Paragraph("Monthly Attendance Report", styles["title"]),
        Spacer(1, 3),
        Paragraph(
            "Prepared for submission and record confirmation. Internal leave classifications are omitted from this export.",
            styles["subtitle"],
        ),
        Spacer(1, 8),
        _build_metadata_table(company_name=company_name, year=year, month=month, styles=styles),
        Spacer(1, 10),
        _build_attendance_table(year=year, month=month, rows=rows),
        Spacer(1, 14),
        _build_signatures(styles),
    ]

    document.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()
