from __future__ import annotations

import calendar
import io
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PAGE_WIDTH, _ = landscape(A4)
PDF_COPY = {
    "eyebrow": "MONTHLY ATTENDANCE",
    "title": "Attendance Report",
    "subtitle": "Professional monthly workforce attendance register",
    "footer_label": "Attendance Report",
    "metadata_labels": ("Company", "Site", "Period", "Generated On"),
}


def _paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(value)), style)


def _build_styles() -> dict[str, ParagraphStyle]:
    sample_styles = getSampleStyleSheet()
    return {
        "eyebrow": ParagraphStyle(
            "ReportEyebrow",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.4,
            leading=9,
            textColor=colors.HexColor("#bfdbfe"),
            alignment=TA_LEFT,
            spaceAfter=0,
        ),
        "title": ParagraphStyle(
            "ReportTitle",
            parent=sample_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=23,
            textColor=colors.white,
            alignment=TA_LEFT,
            spaceAfter=0,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=sample_styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.6,
            leading=11,
            textColor=colors.HexColor("#dbeafe"),
            alignment=TA_LEFT,
            spaceAfter=0,
        ),
        "header_meta_label": ParagraphStyle(
            "HeaderMetaLabel",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=6.9,
            leading=8.5,
            textColor=colors.HexColor("#93c5fd"),
            alignment=TA_RIGHT,
            spaceAfter=0,
        ),
        "header_meta_value": ParagraphStyle(
            "HeaderMetaValue",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9.2,
            leading=11,
            textColor=colors.white,
            alignment=TA_RIGHT,
            spaceAfter=0,
        ),
        "meta_label": ParagraphStyle(
            "MetaLabel",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=6.8,
            leading=8,
            textColor=colors.HexColor("#64748b"),
            alignment=TA_LEFT,
            spaceAfter=0,
        ),
        "meta_value": ParagraphStyle(
            "MetaValue",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9.6,
            leading=11.5,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_LEFT,
            spaceAfter=0,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=6.3,
            leading=7.2,
            textColor=colors.white,
            alignment=TA_CENTER,
            spaceAfter=0,
        ),
        "table_cell": ParagraphStyle(
            "TableCell",
            parent=sample_styles["BodyText"],
            fontName="Helvetica",
            fontSize=6.3,
            leading=7.4,
            textColor=colors.HexColor("#1e293b"),
            alignment=TA_CENTER,
            spaceAfter=0,
        ),
        "table_name": ParagraphStyle(
            "TableName",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=6.5,
            leading=7.6,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_LEFT,
            spaceAfter=0,
        ),
        "table_total": ParagraphStyle(
            "TableTotal",
            parent=sample_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=6.4,
            leading=7.4,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_CENTER,
            spaceAfter=0,
        ),
    }


def _build_header_band(*, report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    period_value = _paragraph(report["period_label"], styles["header_meta_value"])
    site_value = _paragraph(report["site_name"], styles["header_meta_value"])
    left_column = [
        _paragraph(PDF_COPY["eyebrow"], styles["eyebrow"]),
        _paragraph(PDF_COPY["title"], styles["title"]),
        _paragraph(PDF_COPY["subtitle"], styles["subtitle"]),
    ]
    right_column = [
        _paragraph("Reporting Period", styles["header_meta_label"]),
        period_value,
        Spacer(1, 4),
        _paragraph("Site", styles["header_meta_label"]),
        site_value,
    ]
    header = Table([[left_column, right_column]], colWidths=[163 * mm, 92 * mm])
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f2744")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#0b1f34")),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return header


def _build_metadata_table(*, report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    company_label, site_label, period_label, generated_label = PDF_COPY["metadata_labels"]
    metadata_cells = [
        [
            _paragraph(company_label, styles["meta_label"]),
            _paragraph(report["company_name"], styles["meta_value"]),
        ],
        [
            _paragraph(site_label, styles["meta_label"]),
            _paragraph(report["site_name"], styles["meta_value"]),
        ],
        [
            _paragraph(period_label, styles["meta_label"]),
            _paragraph(report["period_label"], styles["meta_value"]),
        ],
        [
            _paragraph(generated_label, styles["meta_label"]),
            _paragraph(report["generated_at"], styles["meta_value"]),
        ],
    ]
    metadata_table = Table([metadata_cells], colWidths=[63 * mm, 56 * mm, 63 * mm, 73 * mm])
    metadata_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe4ee")),
                ("LINEABOVE", (0, 0), (-1, 0), 1.1, colors.HexColor("#1d4ed8")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return metadata_table


def _build_attendance_table(*, report: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    year = int(report["year"])
    month = int(report["month"])
    days_in_month = calendar.monthrange(year, month)[1]
    rows = list(report["rows"])
    table_data: list[list[Any]] = [
        [
            _paragraph("No", styles["table_header"]),
            _paragraph("Employee Name", styles["table_header"]),
            _paragraph("Code", styles["table_header"]),
            *[_paragraph(str(day), styles["table_header"]) for day in range(1, 32)],
            _paragraph("Present", styles["table_header"]),
            _paragraph("Complete", styles["table_header"]),
        ]
    ]

    for index, row in enumerate(rows, start=1):
        table_data.append(
            [
                _paragraph(index, styles["table_cell"]),
                _paragraph(row["worker_name"], styles["table_name"]),
                _paragraph(row["employee_code"], styles["table_cell"]),
                *[_paragraph(value or "", styles["table_cell"]) for value in row["days"]],
                _paragraph(row["present_days"], styles["table_total"]),
                _paragraph(row["completed_days"], styles["table_total"]),
            ]
        )

    if not rows:
        table_data.append(
            [
                "",
                _paragraph("No active workers were found for the selected period.", styles["table_name"]),
                "",
                *([""] * 31),
                "",
                "",
            ]
        )

    table = Table(table_data, colWidths=[21, 158, 48] + [12.6] * 31 + [34, 38], repeatRows=1)
    style_commands: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12304f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.22, colors.HexColor("#dde5ee")),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("TOPPADDING", (0, 0), (-1, 0), 6.5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6.5),
        ("TOPPADDING", (0, 1), (-1, -1), 4.8),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4.8),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("LEFTPADDING", (1, 1), (1, -1), 5.5),
        ("BACKGROUND", (0, 1), (2, -1), colors.HexColor("#f8fafc")),
        ("BACKGROUND", (-2, 1), (-1, -1), colors.HexColor("#eff6ff")),
    ]

    for row_index in range(1, len(table_data)):
        row_background = "#ffffff" if row_index % 2 else "#f8fbff"
        style_commands.append(("BACKGROUND", (3, row_index), (-3, row_index), colors.HexColor(row_background)))

    for day in range(1, 32):
        column_index = 2 + day
        if day > days_in_month:
            style_commands.extend(
                [
                    ("BACKGROUND", (column_index, 1), (column_index, -1), colors.HexColor("#e5e7eb")),
                    ("TEXTCOLOR", (column_index, 1), (column_index, -1), colors.HexColor("#94a3b8")),
                    ("BACKGROUND", (column_index, 0), (column_index, 0), colors.HexColor("#64748b")),
                ]
            )
            continue
        if calendar.weekday(year, month, day) >= 5:
            style_commands.append(
                ("BACKGROUND", (column_index, 1), (column_index, -1), colors.HexColor("#f1f5f9"))
            )

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
        _build_header_band(report=report, styles=styles),
        Spacer(1, 8),
        _build_metadata_table(report=report, styles=styles),
        Spacer(1, 10),
        _build_attendance_table(report=report, styles=styles),
    ]
    document.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()
