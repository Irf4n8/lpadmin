"""Create a single-sheet manager report containing live and original MAM rows."""
import json
from pathlib import Path

import xlsxwriter

from qa_manager_workbook import HEADERS, ROOT, formats, live_rows, original_rows, row_height

OUTPUT = ROOT / "MAM_COMBINED_SINGLE_SHEET_REPORT.xlsx"


def main():
    live = live_rows()
    original = original_rows()

    # Make the source of every row explicit without adding a non-reference column.
    for row in live:
        row[10] = "Report section: Executed live MAM test. " + row[10]
    for row in original:
        row[10] = "Report section: Original 165-case coverage. " + row[10]
    combined = live + original

    workbook = xlsxwriter.Workbook(OUTPUT)
    workbook.set_properties({
        "title": "Combined MAM Test Execution Report",
        "subject": "81 executed live tests and 165 original coverage requirements",
        "author": "QA Team",
        "comments": "Single-sheet report generated from recorded evidence. Tooling defects excluded by request.",
    })
    fmt = formats(workbook)
    sheet = workbook.add_worksheet("Combined MAM Report")
    sheet.hide_gridlines(2)
    sheet.freeze_panes(1, 2)
    sheet.set_tab_color("#32678F")
    widths = [18, 40, 44, 57, 35, 52, 52, 15, 12, 14, 58]
    for column, width in enumerate(widths):
        sheet.set_column(column, column, width)
    sheet.set_row(0, 42)
    for column, header in enumerate(HEADERS):
        sheet.write(0, column, header, fmt["header"])

    for index, row in enumerate(combined, start=1):
        base = fmt["even"] if index % 2 == 0 else fmt["odd"]
        identifier = fmt["id_even"] if index % 2 == 0 else fmt["id_odd"]
        sheet.set_row(index, row_height(row))
        for column, value in enumerate(row):
            cell_format = identifier if column == 0 else base
            if column == 7:
                cell_format = fmt.get(str(value).lower(), fmt["neutral"])
            elif column == 8:
                cell_format = fmt.get(str(value).lower(), fmt["neutral"])
            elif column == 9:
                cell_format = fmt["neutral"]
            sheet.write(index, column, value, cell_format)

    sheet.autofilter(0, 0, len(combined), len(HEADERS) - 1)
    sheet.set_landscape()
    sheet.fit_to_pages(1, 0)
    sheet.repeat_rows(0)
    sheet.set_margins(0.25, 0.25, 0.5, 0.5)
    workbook.close()

    assert len(live) == 81
    assert len(original) == 165
    assert len(combined) == 246
    print(json.dumps({
        "workbook": str(OUTPUT),
        "sheets": ["Combined MAM Report"],
        "live_tests": len(live),
        "original_coverage": len(original),
        "combined_rows": len(combined),
        "tooling_defects_included": False,
    }, indent=2))


if __name__ == "__main__":
    main()
