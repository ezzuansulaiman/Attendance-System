"""Excel report builders for the attendance system."""

import calendar
import io
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import db
from constants import DAY_ABBR_MS, REGIONS, STATUS_COLORS

_FILLS = {
    code: PatternFill("solid", fgColor="FF" + color.lstrip("#"))
    for code, color in STATUS_COLORS.items()
}
_FILL_PH = PatternFill("solid", fgColor="FFFFF0C3")
_FILL_HEADER = PatternFill("solid", fgColor="FF1F493C")
_FILL_SUBHDR = PatternFill("solid", fgColor="FF2D6954")
_FILL_DAYROW = PatternFill("solid", fgColor="FFE8EDE5")
_FILL_TOTAL = PatternFill("solid", fgColor="FFDCE8DC")

_FONT_WHITE = Font(name="Calibri", bold=True, color="FFFFFFFF", size=10)
_FONT_BOLD = Font(name="Calibri", bold=True, size=9)
_FONT_BOLD_SM = Font(name="Calibri", bold=True, size=8)
_FONT_SM = Font(name="Calibri", size=8)
_ALIGN_C = Alignment(horizontal="center", vertical="center", wrap_text=True)
_ALIGN_L = Alignment(horizontal="left", vertical="center", wrap_text=True)

_THIN = Side(style="thin", color="FF999999")
_BORDER_ALL = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _month_name_ms(month):
    names = [
        "Januari",
        "Februari",
        "Mac",
        "April",
        "Mei",
        "Jun",
        "Julai",
        "Ogos",
        "September",
        "Oktober",
        "November",
        "Disember",
    ]
    return names[month - 1]


def build_internal_xlsx(region, year, month):
    """Build the detailed internal attendance workbook."""
    employees, grid = db.get_month_grid(region, year, month)
    ph_dates = db.get_public_holiday_dates(year, month)
    num_days = calendar.monthrange(year, month)[1]
    region_name = REGIONS.get(region, region).upper()
    month_label = f"{_month_name_ms(month).upper()} {year}"

    wb = Workbook()
    ws = wb.active
    ws.title = f"{region_name[:12]}_{month:02d}"
    ws.sheet_view.showGridLines = False

    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 18
    for col_i in range(5, 5 + num_days):
        ws.column_dimensions[get_column_letter(col_i)].width = 4.2

    total_start = 5 + num_days
    for offset, width in enumerate([6, 5, 5, 5, 6, 8]):
        ws.column_dimensions[get_column_letter(total_start + offset)].width = width

    total_cols = 4 + num_days + 6
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    title_cell = ws.cell(
        row=1,
        column=1,
        value=f"LAPORAN KEHADIRAN PEKERJA - {region_name} - {month_label}",
    )
    title_cell.font = Font(name="Calibri", bold=True, color="FFFFFFFF", size=13)
    title_cell.fill = _FILL_HEADER
    title_cell.alignment = _ALIGN_C
    ws.row_dimensions[1].height = 26

    headers = ["No", "Nama Penuh", "No. IC", "Jawatan"]
    days_list = list(range(1, num_days + 1))
    day_abbr = [DAY_ABBR_MS[date(year, month, d).weekday()] for d in days_list]
    headers += [str(d) for d in days_list]
    headers += ["P", "AL", "MC", "EML", "OD/RD", "TANDATANGAN"]

    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=col, value=header)
        cell.font = _FONT_WHITE
        cell.fill = _FILL_SUBHDR
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL
    ws.row_dimensions[2].height = 22

    for col in range(1, 5):
        cell = ws.cell(row=3, column=col, value="")
        cell.fill = _FILL_DAYROW
        cell.border = _BORDER_ALL
    for i, abbr in enumerate(day_abbr):
        col = 5 + i
        cell = ws.cell(row=3, column=col, value=abbr)
        cell.font = _FONT_BOLD_SM
        cell.fill = _FILL_DAYROW
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL
    for offset in range(6):
        cell = ws.cell(row=3, column=total_start + offset)
        cell.fill = _FILL_DAYROW
        cell.border = _BORDER_ALL
    ws.row_dimensions[3].height = 16

    for row_i, emp in enumerate(employees, start=1):
        row_no = row_i + 3
        ws.row_dimensions[row_no].height = 18

        cell = ws.cell(row=row_no, column=1, value=row_i)
        cell.font = _FONT_SM
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL

        cell = ws.cell(row=row_no, column=2, value=emp["full_name"])
        cell.font = _FONT_BOLD_SM
        cell.alignment = _ALIGN_L
        cell.border = _BORDER_ALL

        cell = ws.cell(row=row_no, column=3, value=emp.get("ic_number") or "")
        cell.font = _FONT_SM
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL

        cell = ws.cell(row=row_no, column=4, value=emp["designation"])
        cell.font = _FONT_SM
        cell.alignment = _ALIGN_L
        cell.border = _BORDER_ALL

        emp_grid = grid.get(emp["id"], {})
        counts = {status: 0 for status in ["P", "AL", "MC", "EML", "OD", "RD"]}

        for day in days_list:
            col = 4 + day
            date_str = f"{year}-{month:02d}-{day:02d}"
            status = emp_grid.get(day, "")
            cell = ws.cell(row=row_no, column=col, value=status)
            cell.font = _FONT_SM
            cell.alignment = _ALIGN_C
            cell.border = _BORDER_ALL
            if status in _FILLS:
                cell.fill = _FILLS[status]
                counts[status] = counts.get(status, 0) + 1
            elif date_str in ph_dates and not status:
                cell.fill = _FILL_PH

        od_rd = counts.get("OD", 0) + counts.get("RD", 0)
        totals = [counts["P"], counts["AL"], counts["MC"], counts["EML"], od_rd, ""]
        for offset, value in enumerate(totals):
            cell = ws.cell(row=row_no, column=total_start + offset, value=value)
            cell.font = _FONT_BOLD_SM
            cell.alignment = _ALIGN_C
            cell.border = _BORDER_ALL
            cell.fill = _FILL_TOTAL

    legend_row = len(employees) + 4
    ws.row_dimensions[legend_row].height = 14
    legend = (
        "LEGENDA: P=Hadir  OD=Hari Rehat  RD=Berehat  PH=Cuti Umum  "
        "AL=Cuti Tahunan  MC=Cuti Sakit  EML=Cuti Kecemasan"
    )
    ws.merge_cells(start_row=legend_row, start_column=1, end_row=legend_row, end_column=total_cols)
    cell = ws.cell(row=legend_row, column=1, value=legend)
    cell.font = Font(name="Calibri", italic=True, size=8, color="FF555555")
    cell.alignment = _ALIGN_L

    sig_row = legend_row + 2
    ws.row_dimensions[sig_row].height = 36
    ws.merge_cells(start_row=sig_row, start_column=1, end_row=sig_row, end_column=total_cols // 2)
    ws.merge_cells(
        start_row=sig_row,
        start_column=total_cols // 2 + 1,
        end_row=sig_row,
        end_column=total_cols,
    )
    ws.cell(
        row=sig_row,
        column=1,
        value="Disediakan oleh: _______________________________",
    ).font = _FONT_BOLD_SM
    ws.cell(
        row=sig_row,
        column=total_cols // 2 + 1,
        value="Disahkan oleh: _______________________________",
    ).font = _FONT_BOLD_SM

    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = 9
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_area = f"A1:{get_column_letter(total_cols)}{sig_row}"
    ws.freeze_panes = "E4"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_external_xlsx(region, year, month):
    """Build the monthly claim summary workbook."""
    summary = db.get_month_summary(region, year, month)
    num_days = calendar.monthrange(year, month)[1]
    region_name = REGIONS.get(region, region).upper()
    month_label = f"{_month_name_ms(month).upper()} {year}"

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.sheet_view.showGridLines = False

    col_widths = [5, 28, 20, 14, 8, 8, 8, 10, 10]
    for i, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    ws.merge_cells("A1:I1")
    cell = ws.cell(
        row=1,
        column=1,
        value=f"MONTHLY CLAIM ATTENDANCE SUMMARY - {region_name} - {month_label}",
    )
    cell.font = Font(name="Calibri", bold=True, color="FFFFFFFF", size=13)
    cell.fill = _FILL_HEADER
    cell.alignment = _ALIGN_C
    ws.row_dimensions[1].height = 26

    ws.merge_cells("A2:I2")
    cell = ws.cell(
        row=2,
        column=1,
        value=(
            f"Tarikh Cetak: {date.today().strftime('%d %B %Y')}   |   "
            f"Hari dalam Bulan: {num_days}   |   Kegunaan: Monthly Claim Submission"
        ),
    )
    cell.font = Font(name="Calibri", italic=True, size=9, color="FF444444")
    cell.alignment = _ALIGN_L
    ws.row_dimensions[2].height = 16

    headers = [
        "No",
        "Nama Penuh",
        "Jawatan",
        "Hari Hadir (P)",
        "AL",
        "MC",
        "EML",
        "Cuti Umum (PH)",
        "Rehat (OD+RD)",
    ]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col, value=header)
        cell.font = _FONT_WHITE
        cell.fill = _FILL_SUBHDR
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL
    ws.row_dimensions[3].height = 22

    for i, emp in enumerate(summary, start=1):
        row_no = i + 3
        ws.row_dimensions[row_no].height = 18
        od_rd = emp.get("OD", 0) + emp.get("RD", 0)
        values = [
            i,
            emp["full_name"],
            emp["designation"],
            emp.get("P", 0),
            emp.get("AL", 0),
            emp.get("MC", 0),
            emp.get("EML", 0),
            emp.get("PH", 0),
            od_rd,
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row_no, column=col, value=value)
            cell.font = _FONT_SM if col > 2 else _FONT_BOLD_SM
            cell.alignment = _ALIGN_C if col != 2 else _ALIGN_L
            cell.border = _BORDER_ALL

    total_row = len(summary) + 4
    ws.row_dimensions[total_row].height = 20
    for col in range(1, 10):
        cell = ws.cell(row=total_row, column=col)
        cell.fill = _FILL_TOTAL
        cell.border = _BORDER_ALL
    ws.cell(row=total_row, column=1, value="JUMLAH").font = _FONT_BOLD
    ws.cell(row=total_row, column=1).alignment = _ALIGN_C

    for col in range(4, 10):
        cell = ws.cell(row=total_row, column=col)
        start = 4
        end = total_row - 1
        if end >= start:
            col_letter = get_column_letter(col)
            cell.value = f"=SUM({col_letter}{start}:{col_letter}{end})"
        else:
            cell.value = 0
        cell.font = _FONT_BOLD
        cell.alignment = _ALIGN_C

    sig_row = total_row + 3
    ws.merge_cells(f"A{sig_row}:D{sig_row}")
    ws.merge_cells(f"F{sig_row}:I{sig_row}")
    ws.cell(
        row=sig_row,
        column=1,
        value="Disediakan oleh: ____________________",
    ).font = _FONT_BOLD_SM
    ws.cell(
        row=sig_row,
        column=6,
        value="Disahkan oleh: ____________________",
    ).font = _FONT_BOLD_SM

    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = 9
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.freeze_panes = "A4"
    ws.print_area = f"A1:I{sig_row}"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
