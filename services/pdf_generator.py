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
PDF_COPY = {
    "title": "Monthly Attendance Report",
    "footer_label": "Attendance Report",
    "metadata_labels": ("Company", "Site", "Period", "Generated On"),
    "summary_labels": (
        "Workers",
        "Present Days",
        "Checked-Out Days",
        "Avg. Present Days",
        "Completion Rate",
    ),
}


def _build_styles() -> dict[str, ParagraphStyle]:
    sample_styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=sample_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_LEFT,
        ),
        "meta_label": ParagraphStyle(
            "MetaLabel",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=9,
            textColor=colors.HexColor("#64748b"),
            alignment=TA_LEFT,
        ),
        "meta_value": ParagraphStyle(
            "MetaValue",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9.2,
            leading=11,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_LEFT,
        ),
        "summary_label": ParagraphStyle(
            "SummaryLabel",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=9,
            textColor=colors.white,
            alignment=TA_LEFT,
        ),
        "summary_value": ParagraphStyle(
            "SummaryValue",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9.2,
            leading=11,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_LEFT,
        ),
    }


def _build_metadata_table(*, report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    company_label, site_label, period_label, generated_label = PDF_COPY["metadata_labels"]
    metadata_rows = [
        [
            Paragraph(company_label, styles["meta_label"]),
            Paragraph(site_label, styles["meta_label"]),
            Paragraph(period_label, styles["meta_label"]),
            Paragraph(generated_label, styles["meta_label"]),
        ],
        [
            Paragraph(str(report["company_name"]), styles["meta_value"]),
            Paragraph(str(report["site_name"]), styles["meta_value"]),
            Paragraph(str(report["period_label"]), styles["meta_value"]),
            Paragraph(str(report["generated_at"]), styles["meta_value"]),
        ],
    ]
    metadata_table = Table(metadata_rows, colWidths=[72 * mm, 52 * mm, 56 * mm, 46 * mm])
    metadata_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dbe4ee")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 5),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                ("TOPPADDING", (0, 1), (-1, 1), 7),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return metadata_table


def _build_summary_table(*, summary: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    workers_label, present_label, checked_out_label, avg_label, completion_label = PDF_COPY["summary_labels"]
    summary_rows = [
        [
            Paragraph(workers_label, styles["summary_label"]),
            Paragraph(present_label, styles["summary_label"]),
            Paragraph(checked_out_label, styles["summary_label"]),
            Paragraph(avg_label, styles["summary_label"]),
            Paragraph(completion_label, styles["summary_label"]),
        ],
        [
            Paragraph(str(summary["total_workers"]), styles["summary_value"]),
            Paragraph(str(summary["total_present_days"]), styles["summary_value"]),
            Paragraph(str(summary["total_completed_days"]), styles["summary_value"]),
            Paragraph(str(summary["average_present_days"]), styles["summary_value"]),
            Paragraph(f'{summary["completion_rate"]}%', styles["summary_value"]),
        ],
    ]
    summary_table = Table(summary_rows, colWidths=[45.2 * mm] * 5)
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dbe4ee")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 5),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                ("TOPPADDING", (0, 1), (-1, 1), 7),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
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
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 6.4),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#dbe4ee")),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 6.3),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
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
            style_commands.append(("BACKGROUND", (column_index, 0), (column_index, -1), colors.HexColor("#f3f4f6")))

    table.setStyle(TableStyle(style_commands))
    return table


def _draw_footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
    canvas.line(document.leftMargin, 11 * mm, PAGE_WIDTH - document.rightMargin, 11 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(document.leftMargin, 7 * mm, str(PDF_COPY["footer_label"]))
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
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f'{PDF_COPY["title"]} - {calendar.month_name[month]} {year}',
    )
    styles = _build_styles()
    story = [
        Paragraph(str(PDF_COPY["title"]), styles["title"]),
        Spacer(1, 8),
        _build_metadata_table(report=report, styles=styles),
        Spacer(1, 10),
        _build_summary_table(summary=report["summary"], styles=styles),
        Spacer(1, 10),
        _build_attendance_table(report=report),
    ]
    document.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()
