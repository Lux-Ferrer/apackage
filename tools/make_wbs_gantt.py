# -*- coding: utf-8 -*-
"""生成 WBS + 甘特图 Excel（deliverables/WBS_Gantt_ZeyuJin.xlsx）。

版面
----
    左侧 A~G   WBS 表：ID / Task Name / Duration / Start / Finish / Predecessors / Resource
    右侧 H~CP  甘特图：**每个自然日一列**，2026-09-10 → 2026-12-05 共 87 列
    表格下方   图例：Summary / Task / Milestone

为什么按自然日排、且不区分周末
------------------------------
每个自然日一列（9/10/26 → 12/5/26 共 87 列）。**周末按正常工作日处理、不扣节假日**，
所以不给周末列加灰底 —— 那会暗示"周末不干活"。日期靠月份带 + 每周一的日期数字定位。
（源表的 Duration 是"62 days"，对应 9/10→12/5 的工作日数；本文件按原表逐字填入，
不重算工期。）

用法::

    python tools/make_wbs_gantt.py                 # 写到默认路径
    python tools/make_wbs_gantt.py --output x.xlsx # 自定义输出
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openpyxl import Workbook                                          # noqa: E402
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: E402
from openpyxl.utils import get_column_letter                           # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "deliverables" / "WBS_Gantt_ZeyuJin.xlsx"

# --------------------------------------------------------------------------
# 数据（ID / Task Name / Duration / Start / Finish / Predecessors）
#
# Resource 未在原表里给出：本项目只有一位执行人，所以内部任务填 Zeyu Jin，
# 外部依赖（客户提供 Word 模板）填 Client。
# --------------------------------------------------------------------------
TASKS = [
    ("1",     "Curtain Wall Inspection Report Tool (330–350h)",      "62 days", "9/10/26", "12/5/26",  "—"),
    ("1.1",   "Project Initiation and Planning (20h)",               "5 days",  "9/10/26", "9/16/26",  "—"),
    ("1.1.1", "Requirements Confirmation and Scope",                 "2 days",  "9/10/26", "9/11/26",  "—"),
    ("1.1.2", "Technology Selection and Architecture",               "1 day",   "9/12/26", "9/12/26",  "1.1.1"),
    ("1.1.3", "Project Plan and WBS Development",                    "2 days",  "9/15/26", "9/16/26",  "1.1.2"),
    ("1.2",   "Core System Development (60h)",                       "9 days",  "9/17/26", "9/25/26",  "1.1"),
    ("1.2.1", "Foundation Setup and Database Schema",                "3 days",  "9/17/26", "9/19/26",  "1.1.3"),
    ("1.2.2", "Project Management and Record Entry",                 "2 days",  "9/22/26", "9/23/26",  "1.2.1"),
    ("1.2.3", "Project-level Word Export Engine",                    "1 day",   "9/23/26", "9/23/26",  "1.2.2"),
    ("1.2.4", "Defect Reporting and Attachment Export",              "1 day",   "9/24/26", "9/24/26",  "1.2.3"),
    ("1.2.5", "Alignment with Client Report Format",                 "1 day",   "9/24/26", "9/24/26",  "1.2.4"),
    ("1.3",   "Report Management Module (15h)",                      "1 day",   "9/25/26", "9/25/26",  "1.2"),
    ("1.3.1", "Report List and Top Statistics",                      "0.5 day", "9/25/26", "9/25/26",  "1.2.5"),
    ("1.3.2", "Report Detail and Thumbnails",                        "0.5 day", "9/25/26", "9/25/26",  "1.3.1"),
    ("1.4",   "Mobile-First UI Redesign (25h)",                      "7 days",  "9/28/26", "10/4/26",  "1.3"),
    ("1.4.1", "Navigation Shell (Bottom Tabs + Top Bar)",            "1 day",   "9/28/26", "9/28/26",  "1.3.2"),
    ("1.4.2", "Inspection Record Form Rewrite",                      "2 days",  "9/29/26", "9/30/26",  "1.4.1"),
    ("1.4.3", "Remaining Pages and Profile Page",                    "2 days",  "10/1/26", "10/2/26",  "1.4.2"),
    ("1.4.4", "Regression and Real-Device Verification",             "1 day",   "10/3/26", "10/4/26",  "1.4.3"),
    ("1.5",   "Client-Side Architecture Migration (100h)",           "15 days", "10/5/26", "10/23/26", "1.4"),
    ("1.5.1", "M5 Architecture Design",                              "2 days",  "10/5/26", "10/6/26",  "1.4.4"),
    ("1.5.2", "IndexedDB Data Layer Implementation",                 "4 days",  "10/7/26", "10/12/26", "1.5.1"),
    ("1.5.3", "JS Word Export Engine Implementation",                "5 days",  "10/13/26", "10/19/26", "1.5.2"),
    ("1.5.4", "PWA Configuration and Offline Capability",            "2 days",  "10/20/26", "10/21/26", "1.5.3"),
    ("1.5.5", "JS vs Python Export Fidelity Verification",           "2 days",  "10/22/26", "10/23/26", "1.5.4"),
    ("1.6",   "Testing and Refinement (35h)",                        "10 days", "10/26/26", "11/6/26",  "1.5"),
    ("1.6.1", "Full Regression Testing",                             "3 days",  "10/26/26", "10/28/26", "1.5.5"),
    ("1.6.2", "Edge Cases and Exception Handling",                   "3 days",  "10/29/26", "11/2/26",  "1.6.1"),
    ("1.6.3", "Performance and Browser Compatibility",               "2 days",  "11/3/26", "11/4/26",  "1.6.2"),
    ("1.6.4", "Mobile Real-Device Re-verification",                  "2 days",  "11/5/26", "11/6/26",  "1.6.3"),
    ("1.7",   "Documentation and Delivery (40h)",                    "13 days", "11/9/26", "11/25/26", "1.6"),
    ("1.7.1", "User Manual and Installation Guide",                  "3 days",  "11/9/26", "11/11/26", "1.6.4"),
    ("1.7.2", "Deliverable Samples and Fidelity Report",             "3 days",  "11/12/26", "11/16/26", "1.7.1"),
    ("1.7.3", "Final Presentation Materials",                        "3 days",  "11/17/26", "11/19/26", "1.7.2"),
    ("1.7.4", "Final Report Writing",                                "4 days",  "11/20/26", "11/25/26", "1.7.3"),
    ("1.8",   "Project Closure (15h)",                               "4 days",  "11/27/26", "12/2/26",  "1.7"),
    ("1.8.1", "Internal Review and Revision",                        "2 days",  "11/27/26", "11/30/26", "1.7.4"),
    ("1.8.2", "Final Delivery and Acceptance",                       "2 days",  "12/1/26", "12/2/26",  "1.8.1"),
    ("1.9",   "Project Completion",                                  "0 days",  "12/5/26", "12/5/26",  "1.8"),
    ("1.10",  "Client Final Word Template (external dependency)",    "7 days",  "10/1/26", "10/9/26",  "—"),
]

CHART_START = date(2026, 9, 10)
CHART_END = date(2026, 12, 5)

# --------------------------------------------------------------------------
# 样式
# --------------------------------------------------------------------------
INK = "1F2937"
MUTED = "6B7280"
LINE = "BFC7D1"

FILL_SUMMARY_BAR = PatternFill("solid", fgColor="1F4E79")      # 汇总：深色横条
FILL_TASK_BAR = PatternFill("solid", fgColor="9DC3E6")         # 子任务：浅色横条
FILL_SUMMARY_ROW = PatternFill("solid", fgColor="DDEBF7")      # 汇总行底色
FILL_HEADER = PatternFill("solid", fgColor="1F4E79")
FILL_BAND_A = PatternFill("solid", fgColor="FFFFFF")
FILL_BAND_B = PatternFill("solid", fgColor="F7F9FC")

FONT_TITLE = Font(name="Calibri", size=15, bold=True, color="1F4E79")
FONT_SUB = Font(name="Calibri", size=10, color=MUTED)
FONT_HEADER = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
FONT_CELL = Font(name="Calibri", size=10, color=INK)
FONT_SUMMARY = Font(name="Calibri", size=10, bold=True, color="1F3864")
FONT_MONTH = Font(name="Calibri", size=9, bold=True, color="1F4E79")
FONT_DAY = Font(name="Calibri", size=7, color=MUTED)
FONT_WEEKDAY = Font(name="Calibri", size=6, color="9AA3AF")
FONT_LEGEND = Font(name="Calibri", size=10, color=INK)
FONT_MILESTONE = Font(name="Calibri", size=11, bold=True, color="C00000")

THIN = Side(style="thin", color=LINE)
HAIR = Side(style="hair", color="D6DBE1")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
GRID = Border(left=HAIR, right=HAIR, top=HAIR, bottom=HAIR)

LEFT = Alignment(horizontal="left", vertical="center")
CENTER = Alignment(horizontal="center", vertical="center")
RIGHT = Alignment(horizontal="right", vertical="center")

TABLE_HEADERS = ["ID", "Task Name", "Duration", "Start", "Finish", "Predecessors", "Resource"]
TABLE_WIDTHS = [6.5, 52, 9.5, 10.5, 10.5, 13, 15]
DAY_WIDTH = 2.4

HEADER_ROWS = 3          # 1 标题 / 2 月份+副标题 / 3 列头+日期
FIRST_TASK_ROW = HEADER_ROWS + 1
CHART_FIRST_COL = len(TABLE_HEADERS) + 1          # H


# --------------------------------------------------------------------------
# 派生
# --------------------------------------------------------------------------
def parse_date(text: str) -> date:
    month, day, year = text.split("/")
    return date(2000 + int(year), int(month), int(day))


def chart_days() -> list:
    days, current = [], CHART_START
    while current <= CHART_END:
        days.append(current)
        current += timedelta(days=1)
    return days


def level_of(task_id: str) -> int:
    """缩进层级：1 → 0，1.1 → 1，1.1.1 → 2。"""
    return task_id.count(".")


def is_summary(task_id: str, all_ids: set) -> bool:
    prefix = task_id + "."
    return any(other.startswith(prefix) for other in all_ids)


def is_milestone(duration: str) -> bool:
    return duration.strip().startswith("0 ")


def kind_of(task_id: str, duration: str, all_ids: set) -> str:
    if is_summary(task_id, all_ids):
        return "summary"
    return "milestone" if is_milestone(duration) else "task"


# 原表没有 Resource 列：本项目只有一位执行人，1.10 是对客户的外部依赖
EXTERNAL_TASK_IDS = {"1.10"}
OWNER = "Zeyu Jin"


def resource_for(task_id: str) -> str:
    return "Client" if task_id in EXTERNAL_TASK_IDS else OWNER


# --------------------------------------------------------------------------
# 生成
# --------------------------------------------------------------------------
def build(output: Path) -> Path:
    days = chart_days()
    day_index = {day: index for index, day in enumerate(days)}
    all_ids = {row[0] for row in TASKS}

    wb = Workbook()
    ws = wb.active
    ws.title = "WBS & Gantt"
    ws.sheet_view.showGridLines = False

    last_col = CHART_FIRST_COL + len(days) - 1
    last_task_row = FIRST_TASK_ROW + len(TASKS) - 1

    # ---- 标题与副标题 ----
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=7)
    title = ws.cell(row=1, column=1, value="WBS & Gantt Chart — Curtain Wall Inspection Report Tool")
    title.font = FONT_TITLE
    title.alignment = LEFT
    ws.row_dimensions[1].height = 24

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=7)
    subtitle = ws.cell(
        row=2, column=1,
        value="Zeyu Jin · NYU MS in Management and Systems · 310h (330–350h with buffer) · "
              "chart covers 9/10/26–12/5/26 (every calendar day, 87 columns; "
              "weekends are working days, no holidays)",
    )
    subtitle.font = FONT_SUB
    subtitle.alignment = LEFT

    # ---- 表头 ----
    for index, name in enumerate(TABLE_HEADERS, start=1):
        cell = ws.cell(row=HEADER_ROWS, column=index, value=name)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        cell.alignment = CENTER
        cell.border = BOX
    for index, width in enumerate(TABLE_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.row_dimensions[HEADER_ROWS].height = 20

    # ---- 甘特图表头：月份带 + 日期 + 星期首字母 ----
    month_start = 0
    for position in range(1, len(days) + 1):
        is_last = position == len(days)
        if is_last or days[position].month != days[month_start].month:
            first_col = CHART_FIRST_COL + month_start
            end_col = CHART_FIRST_COL + position - 1
            if end_col > first_col:
                ws.merge_cells(start_row=1, start_column=first_col, end_row=1, end_column=end_col)
            label = days[month_start].strftime("%b %Y")
            cell = ws.cell(row=1, column=first_col, value=label)
            cell.font = FONT_MONTH
            cell.alignment = CENTER
            month_start = position

    for index, day in enumerate(days):
        column = CHART_FIRST_COL + index
        ws.column_dimensions[get_column_letter(column)].width = DAY_WIDTH

        # 日期数字只在周一、每月 1 号与首列显示，避免 87 列全是数字看不清。
        # 周末不加底色：周末是正常工作日（不扣节假日），加灰底会暗示"周末不干活"。
        show_number = day.weekday() == 0 or day.day == 1 or index == 0
        number_cell = ws.cell(row=2, column=column, value=day.day if show_number else None)
        number_cell.font = FONT_DAY
        number_cell.alignment = CENTER

        weekday_cell = ws.cell(row=3, column=column, value="MTWTFSS"[day.weekday()])
        weekday_cell.font = FONT_WEEKDAY
        weekday_cell.alignment = CENTER

    ws.row_dimensions[2].height = 14
    ws.row_dimensions[3].height = 13

    # ---- 任务行 ----
    for offset, (task_id, name, duration, start_text, finish_text, predecessors) in enumerate(TASKS):
        row = FIRST_TASK_ROW + offset
        start, finish = parse_date(start_text), parse_date(finish_text)
        kind = kind_of(task_id, duration, all_ids)
        level = level_of(task_id)
        band = FILL_BAND_A if level == 0 or level == 1 else FILL_BAND_B

        values = [task_id, name, duration, start, finish, predecessors, resource_for(task_id)]
        for index, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=index, value=value)
            cell.font = FONT_SUMMARY if kind == "summary" else FONT_CELL
            cell.border = BOX
            cell.alignment = CENTER if index in (1, 3, 4, 5, 6) else LEFT
        ws.cell(row=row, column=4).number_format = "m/d/yy"
        ws.cell(row=row, column=5).number_format = "m/d/yy"

        # 子任务缩进（层级 2 再缩一格），汇总行与里程碑不缩进
        name_cell = ws.cell(row=row, column=2)
        name_cell.alignment = Alignment(horizontal="left", vertical="center",
                                        indent=0 if kind != "task" else level)
        if kind == "summary":
            for index in range(1, 8):
                ws.cell(row=row, column=index).fill = FILL_SUMMARY_ROW
        else:
            for index in range(1, 8):
                ws.cell(row=row, column=index).fill = band

        # ---- 横条 ----
        if kind == "milestone":
            column = CHART_FIRST_COL + day_index[start]
            cell = ws.cell(row=row, column=column, value="◆")
            cell.font = FONT_MILESTONE
            cell.alignment = CENTER
        else:
            fill = FILL_SUMMARY_BAR if kind == "summary" else FILL_TASK_BAR
            for column_offset in range(day_index[start], day_index[finish] + 1):
                ws.cell(row=row, column=CHART_FIRST_COL + column_offset).fill = fill

        ws.row_dimensions[row].height = 17

    # ---- 冻结窗格：滚动时表头与左侧 7 列保持可见 ----
    ws.freeze_panes = ws.cell(row=FIRST_TASK_ROW, column=CHART_FIRST_COL)

    # ---- 图例 ----
    legend_row = last_task_row + 2
    label = ws.cell(row=legend_row, column=1, value="Legend / 图例")
    label.font = Font(name="Calibri", size=11, bold=True, color="1F4E79")

    legend_row += 1
    entries = [
        ("Summary", FILL_SUMMARY_BAR, None),
        ("Task", FILL_TASK_BAR, None),
        ("Milestone", None, "◆"),
    ]
    column = 1
    for name, fill, glyph in entries:
        swatch = ws.cell(row=legend_row, column=column)
        swatch.border = BOX
        if fill is not None:
            swatch.fill = fill
        if glyph:
            swatch.value = glyph
            swatch.font = FONT_MILESTONE
            swatch.alignment = CENTER
        ws.cell(row=legend_row, column=column + 1, value=name).font = FONT_LEGEND
        ws.merge_cells(start_row=legend_row, start_column=column + 1,
                       end_row=legend_row, end_column=column + 2)
        column += 4

    notes = [
        "Axis: every calendar day from 9/10/26 to 12/5/26 (87 columns). Weekends are treated as "
        "normal working days and no holidays are excluded, so weekend columns are not shaded; "
        "date numbers are printed on Mondays, on the 1st of each month and on the first column.",
        "Durations, dates and predecessors are copied verbatim from the source WBS "
        "(the 62-day total for 1.0 corresponds to the weekdays in 9/10–12/5).",
        "Resource column was not in the source list: internal tasks are assigned to Zeyu Jin; "
        "1.10 is an external dependency on the client.",
        "Summary rows are bold with a dark bar; leaf tasks are indented with a light bar; "
        "0-day items are milestones (◆).",
    ]
    for index, text in enumerate(notes):
        row = legend_row + 1 + index
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=12)
        cell = ws.cell(row=row, column=1, value=("· " + text))
        cell.font = FONT_SUB
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=False)

    # ---- 打印设置：横向、缩到一页宽 ----
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "%d:%d" % (HEADER_ROWS, HEADER_ROWS)

    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 WBS + 甘特图 Excel")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="输出路径")
    args = parser.parse_args()

    path = build(Path(args.output))
    days = chart_days()
    print("已生成：%s" % path)
    print("  任务 %d 行；甘特图 %s → %s，共 %d 列（%d 个工作日）"
          % (len(TASKS), CHART_START.isoformat(), CHART_END.isoformat(),
             len(days), sum(1 for d in days if d.weekday() < 5)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
