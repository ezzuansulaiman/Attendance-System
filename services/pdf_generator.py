from __future__ import annotations

import calendar
import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


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
        leftMargin=20,
        rightMargin=20,
        topMargin=24,
        bottomMargin=24,
    )
    styles = getSampleStyleSheet()
    title = f"{company_name} - {calendar.month_name[month].upper()} {year}"
    subtitle = "Daily attendance report with 31-day grid"

    header = [
        Paragraph(f"<b>{title}</b>", styles["Title"]),
        Paragraph(subtitle, styles["BodyText"]),
        Spacer(1, 12),
    ]

    table_data: list[list[str]] = [
        ["No", "Worker", "Code"] + [str(day) for day in range(1, 32)] + ["P", "L"]
    ]

    for index, row in enumerate(rows, start=1):
        table_data.append(
            [
                str(index),
                str(row["worker_name"]),
                str(row["employee_code"]),
                *[str(value) for value in row["days"]],
                str(row["present_total"]),
                str(row["leave_total"]),
            ]
        )

    column_widths = [24, 120, 48] + [16] * 31 + [22, 22]
    table = Table(table_data, colWidths=column_widths, repeatRows=1)
    style_commands: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16324f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#94a3b8")),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for row_index in range(1, len(table_data)):
        background = "#f8fafc" if row_index % 2 else "#e2e8f0"
        style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor(background)))
    table.setStyle(TableStyle(style_commands))

    signatures = Table(
        [
            ["Prepared by", "Verified by", "Approved by"],
            ["\n\n________________________", "\n\n________________________", "\n\n________________________"],
        ],
        colWidths=[250, 250, 250],
    )
    signatures.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    document.build([*header, table, Spacer(1, 20), signatures])
    return buffer.getvalue()
