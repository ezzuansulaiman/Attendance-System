from __future__ import annotations

import calendar
import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
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
        "system_note": ParagraphStyle(
            "SystemNote",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#475569"),
            alignment=TA_LEFT,
        ),
    }


def _build_metadata_table(*, report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    metadata_rows = [
        [
            Paragraph("COMPANY", styles["meta_label"]),
            Paragraph("SITE", styles["meta_label"]),
            Paragraph("REPORT PERIOD", styles["meta_label"]),
            Paragraph("GENERATED", styles["meta_label"]),
        ],
        [
            Paragraph(str(report["company_name"]), styles["meta_value"]),
            Paragraph(str(report["site_name"]), styles["meta_value"]),
            Paragraph(str(report["period_label"]), styles["meta_value"]),
            Paragraph(str(report["generated_at"]), styles["meta_value"]),
        ],
    ]
    metadata_table = Table(metadata_rows, colWidths=[74 * mm, 54 * mm, 54 * mm, 44 * mm])
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


def _build_summary_table(*, summary: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    summary_rows = [
        [
            Paragraph("ACTIVE WORKERS", styles["meta_label"]),
            Paragraph("ATTENDANCE DAYS", styles["meta_label"]),
            Paragraph("CHECKED-OUT DAYS", styles["meta_label"]),
            Paragraph("AVG DAYS / WORKER", styles["meta_label"]),
            Paragraph("COMPLETION RATE", styles["meta_label"]),
        ],
        [
            Paragraph(str(summary["total_workers"]), styles["meta_value"]),
            Paragraph(str(summary["total_present_days"]), styles["meta_value"]),
            Paragraph(str(summary["total_completed_days"]), styles["meta_value"]),
            Paragraph(str(summary["average_present_days"]), styles["meta_value"]),
            Paragraph(f'{summary["completion_rate"]}%', styles["meta_value"]),
        ],
    ]
    summary_table = Table(summary_rows, colWidths=[48 * mm, 48 * mm, 48 * mm, 48 * mm, 48 * mm])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16324f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    return summary_table


def _build_attendance_table(*, report: dict[str, Any]) -> Table:
    year = int(report["year"])
    month = int(report["month"])
    rows = list(report["rows"])
    table_data: list[list[str]] = [
        ["No", "Employee Name", "Code", "Site"] + [str(day) for day in range(1, 32)] + ["P", "Out"]
    ]

    for index, row in enumerate(rows, start=1):
        table_data.append(
            [
                str(index),
                str(row["worker_name"]),
                str(row["employee_code"]),
                str(row["site_name"]),
                *[str(value) for value in row["days"]],
                str(row["present_days"]),
                str(row["completed_days"]),
            ]
        )

    table = Table(table_data, colWidths=[18, 120, 42, 60] + [12.7] * 31 + [24, 24], repeatRows=1)
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
        ("ALIGN", (3, 1), (3, -1), "LEFT"),
        ("LEFTPADDING", (1, 1), (1, -1), 5),
        ("LEFTPADDING", (3, 1), (3, -1), 5),
    ]

    for row_index in range(1, len(table_data)):
        row_background = "#ffffff" if row_index % 2 else "#f8fafc"
        style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor(row_background)))

    for day in range(1, 32):
        column_index = 3 + day
        if day > calendar.monthrange(year, month)[1]:
            style_commands.append(("BACKGROUND", (column_index, 0), (column_index, -1), colors.HexColor("#e5e7eb")))
            style_commands.append(("TEXTCOLOR", (column_index, 1), (column_index, -1), colors.HexColor("#94a3b8")))
            continue
        if calendar.weekday(year, month, day) >= 5:
            style_commands.append(("BACKGROUND", (column_index, 0), (column_index, -1), colors.HexColor("#edf2f7")))

    table.setStyle(TableStyle(style_commands))
    return table


def _build_system_generated_note(styles: dict[str, ParagraphStyle]) -> Table:
    note_table = Table(
        [[Paragraph("Computer generated report. No signature is required.", styles["system_note"])]],
        colWidths=[261 * mm],
    )
    note_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return note_table


def _draw_footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
    canvas.line(document.leftMargin, 11 * mm, PAGE_WIDTH - document.rightMargin, 11 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(document.leftMargin, 7 * mm, "Monthly attendance submission")
    canvas.drawRightString(PAGE_WIDTH - document.rightMargin, 7 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def build_monthly_attendance_pdf(*, report: dict[str, Any]) -> bytes:
    year = int(report["year"])
    month = int(report["month"])
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
            "Prepared for client submission, reconciliation, and attendance confirmation. Use P to indicate a recorded presence for the day.",
            styles["subtitle"],
        ),
        Spacer(1, 8),
        _build_metadata_table(report=report, styles=styles),
        Spacer(1, 10),
        _build_summary_table(summary=report["summary"], styles=styles),
        Spacer(1, 10),
        _build_attendance_table(report=report),
        Spacer(1, 14),
        _build_system_generated_note(styles),
    ]
    document.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()
