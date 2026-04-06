from __future__ import annotations

import calendar
import io
import zipfile
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape


def _column_letter(index: int) -> str:
    result = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell_reference(row_index: int, column_index: int) -> str:
    return f"{_column_letter(column_index)}{row_index}"


def _text_cell(row_index: int, column_index: int, value: Any, style_id: int) -> str:
    cell_ref = _cell_reference(row_index, column_index)
    text = escape("" if value is None else str(value))
    return (
        f'<c r="{cell_ref}" s="{style_id}" t="inlineStr">'
        f'<is><t xml:space="preserve">{text}</t></is></c>'
    )


def _number_cell(row_index: int, column_index: int, value: int | float, style_id: int) -> str:
    cell_ref = _cell_reference(row_index, column_index)
    return f'<c r="{cell_ref}" s="{style_id}"><v>{value}</v></c>'


def _build_row(row_index: int, cells: list[str], height: int | None = None) -> str:
    height_attr = f' ht="{height}" customHeight="1"' if height else ""
    return f'<row r="{row_index}"{height_attr}>{"".join(cells)}</row>'


def _worksheet_xml(
    *,
    rows: list[str],
    column_widths: list[float],
    merges: list[str] | None = None,
    freeze_pane: tuple[int, int, str] | None = None,
    auto_filter: str | None = None,
    last_row: int,
    last_column: int,
) -> str:
    cols_xml = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(column_widths, start=1)
    )
    merge_xml = ""
    if merges:
        merge_xml = "<mergeCells count=\"{}\">{}</mergeCells>".format(
            len(merges),
            "".join(f'<mergeCell ref="{merge_ref}"/>' for merge_ref in merges),
        )
    if freeze_pane:
        x_split, y_split, top_left = freeze_pane
        pane_xml = (
            "<sheetViews><sheetView workbookViewId=\"0\">"
            f'<pane xSplit="{x_split}" ySplit="{y_split}" topLeftCell="{top_left}" '
            'activePane="bottomRight" state="frozen"/>'
            "<selection pane=\"bottomRight\"/>"
            "</sheetView></sheetViews>"
        )
    else:
        pane_xml = "<sheetViews><sheetView workbookViewId=\"0\"/></sheetViews>"

    auto_filter_xml = f'<autoFilter ref="{auto_filter}"/>' if auto_filter else ""
    dimension = f"A1:{_cell_reference(last_row, last_column)}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{dimension}"/>'
        f"{pane_xml}"
        '<sheetFormatPr defaultRowHeight="15"/>'
        f"<cols>{cols_xml}</cols>"
        f"<sheetData>{''.join(rows)}</sheetData>"
        f"{merge_xml}"
        f"{auto_filter_xml}"
        "</worksheet>"
    )


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="5">'
        '<font><sz val="11"/><color theme="1"/><name val="Calibri"/><family val="2"/></font>'
        '<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font>'
        '<font><b/><sz val="16"/><color rgb="FF0F172A"/><name val="Calibri"/><family val="2"/></font>'
        '<font><sz val="10"/><color rgb="FF64748B"/><name val="Calibri"/><family val="2"/></font>'
        '<font><b/><sz val="10"/><color rgb="FF0F172A"/><name val="Calibri"/><family val="2"/></font>'
        "</fonts>"
        '<fills count="7">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF16324F"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFE2E8F0"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFF8FAFC"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFEDF2F7"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFE5E7EB"/><bgColor indexed="64"/></patternFill></fill>'
        "</fills>"
        '<borders count="2">'
        '<border><left/><right/><top/><bottom/><diagonal/></border>'
        '<border>'
        '<left style="thin"><color rgb="FFCBD5E1"/></left>'
        '<right style="thin"><color rgb="FFCBD5E1"/></right>'
        '<top style="thin"><color rgb="FFCBD5E1"/></top>'
        '<bottom style="thin"><color rgb="FFCBD5E1"/></bottom>'
        "<diagonal/>"
        "</border>"
        "</borders>"
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="13">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="4" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="5" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="6" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="4" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="4" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
        "</cellXfs>"
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )


def _content_types_xml(sheet_count: int) -> str:
    sheet_overrides = "".join(
        (
            '<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        ).format(index=index)
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        f"{sheet_overrides}"
        "</Types>"
    )


def _root_relationships_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _workbook_xml(sheet_names: list[str]) -> str:
    sheets_xml = "".join(
        (
            '<sheet name="{name}" sheetId="{sheet_id}" r:id="rId{sheet_id}"/>'
        ).format(name=escape(name), sheet_id=index)
        for index, name in enumerate(sheet_names, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="22000" windowHeight="11000"/></bookViews>'
        f"<sheets>{sheets_xml}</sheets>"
        "</workbook>"
    )


def _workbook_relationships_xml(sheet_count: int) -> str:
    sheet_rels = "".join(
        (
            '<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        ).format(index=index)
        for index in range(1, sheet_count + 1)
    )
    style_rel = (
        '<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    ).format(index=sheet_count + 1)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{sheet_rels}{style_rel}"
        "</Relationships>"
    )


def _build_summary_sheet(report: dict[str, Any]) -> str:
    rows: list[str] = []
    row_index = 1
    last_column = 6

    rows.append(
        _build_row(
            row_index,
            [_text_cell(row_index, 1, "MONTHLY ATTENDANCE SUBMISSION REPORT", 1)],
            height=24,
        )
    )
    row_index += 1
    rows.append(
        _build_row(
            row_index,
            [_text_cell(row_index, 1, "Prepared for client submission and internal verification.", 2)],
        )
    )
    row_index += 2

    metadata = [
        ("Company", report["company_name"]),
        ("Site", report["site_name"]),
        ("Period", report["period_label"]),
        ("Generated", report["generated_at"]),
    ]
    for label, value in metadata:
        cells = [
            _text_cell(row_index, 1, label, 3),
            _text_cell(row_index, 2, value, 4),
        ]
        if label == "Company":
            cells.extend(
                [
                    _text_cell(row_index, 4, "Legend", 3),
                    _text_cell(row_index, 5, "P = Present", 4),
                ]
            )
        rows.append(_build_row(row_index, cells))
        row_index += 1

    row_index += 1
    metric_labels = [
        "Active Workers",
        "Attendance Days",
        "Checked-Out Days",
        "Avg Days / Worker",
        "Completion Rate",
    ]
    metric_values = [
        report["summary"]["total_workers"],
        report["summary"]["total_present_days"],
        report["summary"]["total_completed_days"],
        report["summary"]["average_present_days"],
        f'{report["summary"]["completion_rate"]}%',
    ]
    rows.append(
        _build_row(
            row_index,
            [_text_cell(row_index, index, label, 11) for index, label in enumerate(metric_labels, start=1)],
        )
    )
    row_index += 1

    metric_cells: list[str] = []
    for index, value in enumerate(metric_values, start=1):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metric_cells.append(_number_cell(row_index, index, value, 12))
        else:
            metric_cells.append(_text_cell(row_index, index, value, 12))
    rows.append(_build_row(row_index, metric_cells, height=22))
    row_index += 2

    rows.append(_build_row(row_index, [_text_cell(row_index, 1, "Submission Notes", 3)]))
    row_index += 1
    notes = [
        "Use the Attendance Matrix sheet for the main client-facing monthly schedule.",
        "Use the Detailed Log sheet if the client requests timestamp-level verification.",
        "Weekend columns are shaded for quick review. Non-month days are muted out.",
    ]
    for note in notes:
        rows.append(_build_row(row_index, [_text_cell(row_index, 1, f"- {note}", 4)]))
        row_index += 1

    return _worksheet_xml(
        rows=rows,
        column_widths=[24, 28, 4, 16, 30, 18],
        merges=["A1:F1", "A2:F2", "A12:F12", "A13:F13", "A14:F14", "A15:F15"],
        last_row=row_index - 1,
        last_column=last_column,
    )


def _build_matrix_sheet(report: dict[str, Any]) -> str:
    rows: list[str] = []
    header_row_index = 4
    first_data_row = 5
    day_start_column = 5
    present_column = day_start_column + 31
    completed_column = present_column + 1

    rows.append(_build_row(1, [_text_cell(1, 1, "Attendance Matrix", 1)], height=24))
    rows.append(
        _build_row(
            2,
            [
                _text_cell(
                    2,
                    1,
                    f'{report["company_name"]} | {report["site_name"]} | {report["period_label"]}',
                    2,
                )
            ],
        )
    )

    header_cells = [
        _text_cell(header_row_index, 1, "No", 5),
        _text_cell(header_row_index, 2, "Employee Name", 5),
        _text_cell(header_row_index, 3, "Code", 5),
        _text_cell(header_row_index, 4, "Site", 5),
    ]
    for day in range(1, 32):
        header_style = 5 if day <= report["days_in_month"] else 9
        header_cells.append(_text_cell(header_row_index, day_start_column + day - 1, day, header_style))
    header_cells.extend(
        [
            _text_cell(header_row_index, present_column, "P Days", 5),
            _text_cell(header_row_index, completed_column, "Out", 5),
        ]
    )
    rows.append(_build_row(header_row_index, header_cells, height=22))

    current_row = first_data_row
    for index, item in enumerate(report["rows"], start=1):
        body_cells = [
            _number_cell(current_row, 1, index, 7),
            _text_cell(current_row, 2, item["worker_name"], 6),
            _text_cell(current_row, 3, item["employee_code"], 7),
            _text_cell(current_row, 4, item["site_name"], 6),
        ]
        for day in range(1, 32):
            cell_style = 7
            if day > report["days_in_month"]:
                cell_style = 9
            elif calendar.weekday(report["year"], report["month"], day) >= 5:
                cell_style = 8
            body_cells.append(_text_cell(current_row, day_start_column + day - 1, item["days"][day - 1], cell_style))
        body_cells.extend(
            [
                _number_cell(current_row, present_column, item["present_days"], 10),
                _number_cell(current_row, completed_column, item["completed_days"], 10),
            ]
        )
        rows.append(_build_row(current_row, body_cells))
        current_row += 1

    if not report["rows"]:
        rows.append(
            _build_row(
                first_data_row,
                [
                    _text_cell(first_data_row, 1, "", 6),
                    _text_cell(first_data_row, 2, "No active workers found for the selected period.", 6),
                ],
            )
        )
        current_row = first_data_row + 1

    return _worksheet_xml(
        rows=rows,
        column_widths=[7, 26, 12, 18] + [4.2] * 31 + [10, 8],
        merges=["A1:AK1", "A2:AK2"],
        freeze_pane=(4, 4, "E5"),
        auto_filter=f"A{header_row_index}:AK{max(current_row - 1, first_data_row)}",
        last_row=max(current_row - 1, first_data_row),
        last_column=completed_column,
    )


def _build_detail_sheet(report: dict[str, Any]) -> str:
    rows: list[str] = []
    header_row_index = 4
    first_data_row = 5

    rows.append(_build_row(1, [_text_cell(1, 1, "Detailed Attendance Log", 1)], height=24))
    rows.append(
        _build_row(
            2,
            [
                _text_cell(
                    2,
                    1,
                    f'{report["company_name"]} | {report["site_name"]} | {report["period_label"]}',
                    2,
                )
            ],
        )
    )

    headers = ["No", "Date", "Day", "Employee Name", "Code", "Site", "Status", "Check In", "Check Out", "Notes"]
    rows.append(
        _build_row(
            header_row_index,
            [_text_cell(header_row_index, column, value, 5) for column, value in enumerate(headers, start=1)],
            height=22,
        )
    )

    current_row = first_data_row
    for index, item in enumerate(report["detail_rows"], start=1):
        rows.append(
            _build_row(
                current_row,
                [
                    _number_cell(current_row, 1, index, 7),
                    _text_cell(current_row, 2, item["attendance_date"], 7),
                    _text_cell(current_row, 3, item["weekday"], 7),
                    _text_cell(current_row, 4, item["worker_name"], 6),
                    _text_cell(current_row, 5, item["employee_code"], 7),
                    _text_cell(current_row, 6, item["site_name"], 6),
                    _text_cell(current_row, 7, item["status"], 7),
                    _text_cell(current_row, 8, item["check_in"], 7),
                    _text_cell(current_row, 9, item["check_out"], 7),
                    _text_cell(current_row, 10, item["notes"], 6),
                ],
            )
        )
        current_row += 1

    if not report["detail_rows"]:
        rows.append(
            _build_row(
                first_data_row,
                [
                    _text_cell(first_data_row, 1, "", 6),
                    _text_cell(first_data_row, 2, "No attendance records were found for the selected period.", 6),
                ],
            )
        )
        current_row = first_data_row + 1

    return _worksheet_xml(
        rows=rows,
        column_widths=[7, 14, 10, 26, 12, 18, 18, 16, 16, 32],
        merges=["A1:J1", "A2:J2"],
        freeze_pane=(0, 4, "A5"),
        auto_filter=f"A{header_row_index}:J{max(current_row - 1, first_data_row)}",
        last_row=max(current_row - 1, first_data_row),
        last_column=10,
    )


def build_monthly_attendance_excel(*, report: dict[str, Any]) -> bytes:
    generated_at = datetime.now(timezone.utc)
    worksheets = [
        _build_summary_sheet(report),
        _build_matrix_sheet(report),
        _build_detail_sheet(report),
    ]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", _content_types_xml(len(worksheets)))
        workbook.writestr("_rels/.rels", _root_relationships_xml())
        workbook.writestr("xl/workbook.xml", _workbook_xml(["Summary", "Attendance Matrix", "Detailed Log"]))
        workbook.writestr("xl/_rels/workbook.xml.rels", _workbook_relationships_xml(len(worksheets)))
        workbook.writestr("xl/styles.xml", _styles_xml())
        for index, worksheet_xml in enumerate(worksheets, start=1):
            workbook.writestr(f"xl/worksheets/sheet{index}.xml", worksheet_xml)
        workbook.comment = f"Generated {generated_at.isoformat()}".encode("utf-8")

    return buffer.getvalue()
