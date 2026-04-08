from __future__ import annotations

import calendar
import io
import logging
import re
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PAGE_WIDTH, _ = landscape(A4)
logger = logging.getLogger(__name__)
PDF_BREAK_OPPORTUNITY = "\u200b"
CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
WHITESPACE_PATTERN = re.compile(r"\s+")
PARTIAL_LEAVE_CODE_PATTERN = re.compile(r"^(?:AL|MC|EL)[AP]$")
PDF_COPY = {
    "eyebrow": "MONTHLY ATTENDANCE",
    "title": "Attendance Report",
    "footer_label": "Attendance Report",
    "header_generated_label": "Generated On",
    "metadata_labels": ("Company", "Site", "Period"),
}


class PdfExportError(RuntimeError):
    pass


def _normalize_pdf_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = CONTROL_CHARACTER_PATTERN.sub("", text)
    text = WHITESPACE_PATTERN.sub(" ", text).strip()
    return text


def _truncate_pdf_text(text: str, *, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    if max_length <= 3:
        return text[:max_length]
    return f'{text[: max_length - 3].rstrip()}...'


def _insert_break_opportunities(text: str, *, chunk_size: int) -> str:
    if not text:
        return ""

    tokens = text.split(" ")
    wrapped_tokens = []
    for token in tokens:
        if len(token) <= chunk_size:
            wrapped_tokens.append(token)
            continue
        wrapped_tokens.append(PDF_BREAK_OPPORTUNITY.join(token[index : index + chunk_size] for index in range(0, len(token), chunk_size)))
    return " ".join(wrapped_tokens)


def _sanitize_pdf_field(value: Any, *, max_length: int, chunk_size: int) -> str:
    normalized = _normalize_pdf_text(value)
    truncated = _truncate_pdf_text(normalized, max_length=max_length)
    return _insert_break_opportunities(truncated, chunk_size=chunk_size)


def _mask_client_submission_day_value(value: Any) -> str:
    normalized = _normalize_pdf_text(value)
    if not normalized:
        return ""

    tokens = [token.strip() for token in normalized.split("/") if token.strip()]
    if any(PARTIAL_LEAVE_CODE_PATTERN.fullmatch(token) for token in tokens):
        return "P"
    return normalized


def _prepare_report_for_pdf(report: dict[str, Any]) -> dict[str, Any]:
    sanitized_rows: list[dict[str, Any]] = []
    for row in report.get("rows", []):
        sanitized_row = dict(row)
        sanitized_row["worker_name"] = _sanitize_pdf_field(row.get("worker_name"), max_length=240, chunk_size=16)
        sanitized_row["employee_code"] = _sanitize_pdf_field(row.get("employee_code"), max_length=80, chunk_size=8)
        sanitized_row["days"] = [_mask_client_submission_day_value(value) for value in row.get("days", [])]
        sanitized_rows.append(sanitized_row)

    sanitized_report = dict(report)
    sanitized_report["company_name"] = _sanitize_pdf_field(report.get("company_name"), max_length=240, chunk_size=24)
    sanitized_report["site_name"] = _sanitize_pdf_field(report.get("site_name"), max_length=240, chunk_size=24)
    sanitized_report["period_label"] = _sanitize_pdf_field(report.get("period_label"), max_length=80, chunk_size=20)
    sanitized_report["generated_at"] = _sanitize_pdf_field(report.get("generated_at"), max_length=80, chunk_size=20)
    sanitized_report["rows"] = sanitized_rows
    return sanitized_report


def _build_pdf_debug_context(report: dict[str, Any]) -> dict[str, Any]:
    rows = list(report.get("rows", []))
    worker_name_lengths = [_normalize_pdf_text(row.get("worker_name")) for row in rows]
    employee_code_lengths = [_normalize_pdf_text(row.get("employee_code")) for row in rows]
    return {
        "year": report.get("year"),
        "month": report.get("month"),
        "site_scope": _normalize_pdf_text(report.get("site_name")),
        "worker_count": len(rows),
        "max_worker_name_length": max((len(value) for value in worker_name_lengths), default=0),
        "max_employee_code_length": max((len(value) for value in employee_code_lengths), default=0),
        "is_empty": not rows,
    }


def _paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(_normalize_pdf_text(value)), style)


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
    generated_value = _paragraph(report["generated_at"], styles["header_meta_value"])
    left_column = [
        _paragraph(PDF_COPY["eyebrow"], styles["eyebrow"]),
        _paragraph(PDF_COPY["title"], styles["title"]),
    ]
    right_column = [
        _paragraph(PDF_COPY["header_generated_label"], styles["header_meta_label"]),
        generated_value,
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
    company_label, site_label, period_label = PDF_COPY["metadata_labels"]
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
    ]
    metadata_table = Table([metadata_cells], colWidths=[84 * mm, 84 * mm, 87 * mm])
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
        ]
    ]

    for index, row in enumerate(rows, start=1):
        table_data.append(
            [
                _paragraph(index, styles["table_cell"]),
                _paragraph(row["worker_name"], styles["table_name"]),
                _paragraph(row["employee_code"], styles["table_cell"]),
                *[_paragraph(value or "", styles["table_cell"]) for value in row["days"]],
            ]
        )

    if not rows:
        table_data.append(
            [
                "",
                _paragraph("No active workers were found for the selected period.", styles["table_name"]),
                "",
                *([""] * 31),
            ]
        )

    table = Table(table_data, colWidths=[21, 184, 52] + [13.9] * 31, repeatRows=1)
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
    ]

    for row_index in range(1, len(table_data)):
        row_background = "#ffffff" if row_index % 2 else "#f8fbff"
        style_commands.append(("BACKGROUND", (3, row_index), (-1, row_index), colors.HexColor(row_background)))

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
    debug_context = _build_pdf_debug_context(report)
    sanitized_report = _prepare_report_for_pdf(report)
    try:
        year = int(sanitized_report["year"])
        month = int(sanitized_report["month"])
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
            _build_header_band(report=sanitized_report, styles=styles),
            Spacer(1, 8),
            _build_metadata_table(report=sanitized_report, styles=styles),
            Spacer(1, 10),
            _build_attendance_table(report=sanitized_report, styles=styles),
        ]
        document.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
        return buffer.getvalue()
    except Exception as exc:
        logger.exception("Failed to build monthly attendance PDF: %s", debug_context)
        raise PdfExportError("Unable to build monthly attendance PDF.") from exc
