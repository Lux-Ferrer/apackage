# -*- coding: utf-8 -*-
"""生成 WBS + 甘特图 Excel（deliverables/WBS_Gantt_ZeyuJin.xlsx）。

版面
----
    左侧 A~L   WBS 表：ID / Task Mode / Task Name / Duration / Start / Finish /
               Predecessors / Baseline Start / Baseline Finish / Baseline Duration /
               Finish Variance / Resource Names
    右侧 M~CU  甘特图：**每个自然日一列**，2026-09-10 → 2026-12-05 共 87 列
    表格下方   图例：Task / Summary / Project Summary / Milestone / External Task

样式对齐 MS Project 的用语
--------------------------
    1        Project Summary  顶层项目汇总，黑色加粗条
    1.1~1.8  Summary          普通汇总，深蓝条
    叶子任务  Task             浅蓝条
    1.9      Milestone        0 工期，菱形 ◆
    1.10     External Task    对客户的外部依赖，灰色条
只列这 5 种 —— 本项目的表里没有 Inactive Task / Split / Deadline 之类，图例里不出现。

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
# Resource Names 未在原表里给出：本项目只有一位执行人，所以内部任务填 Zeyu Jin，
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

# 原表没有 Resource Names 列：本项目只有一位执行人，1.10 是对客户的外部依赖
EXTERNAL_TASK_IDS = {"1.10"}
OWNER = "Zeyu Jin"
TASK_MODE = "Auto Scheduled"
# 本项目无正式变更：baseline 就是当前批准的计划，所以 Finish Variance 恒为 0 days，
# 四个 baseline 列直接照抄当前值。
FINISH_VARIANCE = "0 days"

# --------------------------------------------------------------------------
# 列位置（用具名常量，避免插列之后满屏 magic number 对不上）
# --------------------------------------------------------------------------
TABLE_HEADERS = ["ID", "Task Mode", "Task Name", "Duration", "Start", "Finish",
                 "Predecessors", "Baseline Start", "Baseline Finish",
                 "Baseline Duration", "Finish Variance", "Resource Names"]
TABLE_WIDTHS = [6.5, 15, 46, 9.5, 12.5, 12.5, 13, 14, 16, 17, 15, 15]

(COL_ID, COL_MODE, COL_NAME, COL_DURATION,
 COL_START, COL_FINISH, COL_PRED,
 COL_BASELINE_START, COL_BASELINE_FINISH, COL_BASELINE_DURATION,
 COL_VARIANCE, COL_RESOURCE) = range(1, 13)

HEADER_ROWS = 3          # 1 标题 / 2 月份+副标题 / 3 列头+日期
FIRST_TASK_ROW = HEADER_ROWS + 1
CHART_FIRST_COL = len(TABLE_HEADERS) + 1          # M 列
DAY_WIDTH = 2.4

# --------------------------------------------------------------------------
# 样式
# --------------------------------------------------------------------------
INK = "1F2937"
MUTED = "6B7280"
LINE = "BFC7D1"

FILL_PROJECT_BAR = PatternFill("solid", fgColor="000000")       # Project Summary：黑条
FILL_SUMMARY_BAR = PatternFill("solid", fgColor="1F4E79")       # Summary：深蓝条
FILL_TASK_BAR = PatternFill("solid", fgColor="9DC3E6")          # Task：浅蓝条
FILL_EXTERNAL_BAR = PatternFill("solid", fgColor="A6A6A6")      # External Task：灰条

FILL_SUMMARY_ROW = PatternFill("solid", fgColor="DDEBF7")       # 汇总行底色
FILL_HEADER = PatternFill("solid", fgColor="1F4E79")
FILL_BAND_A = PatternFill("solid", fgColor="FFFFFF")
FILL_BAND_B = PatternFill("solid", fgColor="F7F9FC")

FONT_TITLE = Font(name="Calibri", size=15, bold=True, color="1F4E79")
FONT_SUB = Font(name="Calibri", size=10, color=MUTED)
FONT_HEADER = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
FONT_CELL = Font(name="Calibri", size=10, color=INK)
FONT_SUMMARY = Font(name="Calibri", size=10, bold=True, color="1F3864")
FONT_PROJECT = Font(name="Calibri", size=10, bold=True, color="000000")
FONT_MONTH = Font(name="Calibri", size=9, bold=True, color="1F4E79")
FONT_DAY = Font(name="Calibri", size=7, color=MUTED)
FONT_WEEKDAY = Font(name="Calibri", size=6, color="9AA3AF")
FONT_LEGEND = Font(name="Calibri", size=10, color=INK)
FONT_MILESTONE = Font(name="Calibri", size=11, bold=True, color="C00000")

THIN = Side(style="thin", color=LINE)
HAIR = Side(style="hair", color="D6DBE1")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

LEFT = Alignment(horizontal="left", vertical="center")
CENTER = Alignment(horizontal="center", vertical="center")

# 图例顺序：Task / Summary / Project Summary / Milestone / External Task
LEGEND = (
    ("Task", FILL_TASK_BAR, None),
    ("Summary", FILL_SUMMARY_BAR, None),
    ("Project Summary", FILL_PROJECT_BAR, None),
    ("Milestone", None, "◆"),
    ("External Task", FILL_EXTERNAL_BAR, None),
)

WEEKDAY_ABBR = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


# --------------------------------------------------------------------------
# 派生
# --------------------------------------------------------------------------
def parse_date(text: str) -> date:
    """``"9/10/26"`` → ``date(2026, 9, 10)``（源表是 m/d/yy）。"""
    month, day, year = text.split("/")
    return date(2000 + int(year), int(month), int(day))


def ms_date(value: date) -> str:
    """MS Project 风格的日期文本：``Thu 9/10/26``。

    写成**文本**而不是"日期值 + 数字格式"：``ddd`` 这类格式码会跟随 Excel 的界面语言
    （中文环境显示"周四 9/10/26"），而这份交付物要求固定显示 ``Thu``。文本能保证任何
    环境、任何阅读器打开都是同一个样子。代价是这两列不能按日期排序/筛选 ——
    数据源是静态 WBS，用不上日期运算。
    """
    return "%s %d/%d/%d" % (WEEKDAY_ABBR[value.weekday()], value.month, value.day,
                            value.year % 100)


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


def is_project_summary(task_id: str) -> bool:
    return "." not in task_id


def is_milestone(duration: str) -> bool:
    return duration.strip().startswith("0 ")


def is_external(task_id: str) -> bool:
    return task_id in EXTERNAL_TASK_IDS


def kind_of(task_id: str, duration: str, all_ids: set) -> str:
    """``project`` / ``summary`` / ``milestone`` / ``task``（External Task 是 task 的一种样式）。"""
    if is_project_summary(task_id):
        return "project"
    if is_summary(task_id, all_ids):
        return "summary"
    return "milestone" if is_milestone(duration) else "task"


BAR_FILL_BY_KIND = {
    "project": FILL_PROJECT_BAR,
    "summary": FILL_SUMMARY_BAR,
    "task": FILL_TASK_BAR,
}


def bar_fill(task_id: str, kind: str):
    """该行的横条填充色；里程碑返回 None（用菱形符号）。"""
    if kind == "milestone":
        return None
    return FILL_EXTERNAL_BAR if is_external(task_id) else BAR_FILL_BY_KIND[kind]


def resource_for(task_id: str) -> str:
    return "Client" if is_external(task_id) else OWNER


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

    last_task_row = FIRST_TASK_ROW + len(TASKS) - 1

    # ---- 标题与副标题 ----
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=COL_RESOURCE)
    title = ws.cell(row=1, column=1,
                    value="WBS & Gantt Chart — Curtain Wall Inspection Report Tool")
    title.font = FONT_TITLE
    title.alignment = LEFT
    ws.row_dimensions[1].height = 24

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=COL_RESOURCE)
    subtitle = ws.cell(
        row=2, column=1,
        value="Zeyu Jin · NYU MS in Management and Systems · "
              "310h identified + 20–40h contingency = 330–350h total · "
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
            cell = ws.cell(row=1, column=first_col, value=days[month_start].strftime("%b %Y"))
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
        summary_like = kind in ("project", "summary")
        band = FILL_BAND_A if level_of(task_id) <= 1 else FILL_BAND_B

        values = [
            task_id,                                    # ID
            TASK_MODE,                                  # Task Mode
            name,                                       # Task Name
            duration,                                   # Duration
            ms_date(start),                             # Start（MS Project 文本格式）
            ms_date(finish),                            # Finish
            predecessors,                               # Predecessors
            ms_date(start),                             # Baseline Start = 当前 Start
            ms_date(finish),                            # Baseline Finish = 当前 Finish
            duration,                                   # Baseline Duration = 当前 Duration
            FINISH_VARIANCE,                            # Finish Variance（无变更 → 0 days）
            resource_for(task_id),                      # Resource Names
        ]
        for index, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=index, value=value)
            if kind == "project":
                cell.font = FONT_PROJECT
            elif kind == "summary":
                cell.font = FONT_SUMMARY
            else:
                cell.font = FONT_CELL
            cell.border = BOX
            cell.alignment = LEFT if index in (COL_NAME, COL_RESOURCE) else CENTER

        # 子任务缩进（层级 2 再缩一格），汇总行与里程碑不缩进
        name_cell = ws.cell(row=row, column=COL_NAME)
        name_cell.alignment = Alignment(horizontal="left", vertical="center",
                                        indent=0 if summary_like else level_of(task_id))

        for index in range(1, COL_RESOURCE + 1):
            ws.cell(row=row, column=index).fill = FILL_SUMMARY_ROW if summary_like else band

        # ---- 横条 ----
        fill = bar_fill(task_id, kind)
        if fill is None:                                 # 里程碑：菱形
            column = CHART_FIRST_COL + day_index[start]
            cell = ws.cell(row=row, column=column, value="◆")
            cell.font = FONT_MILESTONE
            cell.alignment = CENTER
        else:
            for column_offset in range(day_index[start], day_index[finish] + 1):
                ws.cell(row=row, column=CHART_FIRST_COL + column_offset).fill = fill

        ws.row_dimensions[row].height = 17

    # ---- 冻结窗格：滚动时表头与左侧 8 列保持可见 ----
    ws.freeze_panes = ws.cell(row=FIRST_TASK_ROW, column=CHART_FIRST_COL)

    # ---- 图例：本项目实际用到的 5 种 ----
    # 标题用纯英文：整份文件的说明行都是英文，保持一致。
    # （原来是 "Legend / 图例"，交付时被手工改成 "Legend"，这里采纳该改动）
    legend_row = last_task_row + 2
    label = ws.cell(row=legend_row, column=1, value="Legend")
    label.font = Font(name="Calibri", size=11, bold=True, color="1F4E79")

    legend_row += 1
    column = 1
    for name, fill, glyph in LEGEND:
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
        "Dates use the MS Project text format (Thu 9/10/26) so they look identical in any "
        "locale; they are stored as text, so these two columns do not sort as dates.",
        "Axis: every calendar day from 9/10/26 to 12/5/26 (87 columns). Weekends are treated as "
        "normal working days and no holidays are excluded, so weekend columns are not shaded; "
        "date numbers are printed on Mondays, on the 1st of each month and on the first column.",
        "Durations, dates and predecessors are copied verbatim from the source WBS "
        "(the 62-day total for 1.0 corresponds to the weekdays in 9/10–12/5). "
        "Task Mode is Auto Scheduled for every row.",
        "There are no formal change requests in this project: the baseline is the currently "
        "approved plan, so the baseline columns mirror the current Start / Finish / Duration "
        "and Finish Variance is 0 days for every row.",
        "Resource Names was not in the source list: internal tasks are assigned to Zeyu Jin; "
        "1.10 is an external dependency on the client (External Task, grey bar).",
        "Bar styles: Project Summary is a bold black bar, Summary a dark blue bar, Task a light "
        "blue bar, Milestone a red diamond, External Task a grey bar.",
    ]
    for index, text in enumerate(notes):
        row = legend_row + 1 + index
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=14)
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
    print("  任务 %d 行；甘特图 %s → %s，共 %d 列（%d 个工作日），起始列 %s"
          % (len(TASKS), CHART_START.isoformat(), CHART_END.isoformat(), len(days),
             sum(1 for d in days if d.weekday() < 5), get_column_letter(CHART_FIRST_COL)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
