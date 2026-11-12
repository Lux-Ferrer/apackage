#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Current WBS（带完成状态）→ Excel + PDF，给「Project Status Update Meeting」上传用。

为什么**不直接改** `deliverables/WBS_Gantt_ZeyuJin.xlsx`
--------------------------------------------------------
那份是"批准的基线 WBS"，而且 `tests/test_wbs_gantt.py` 把它**逐列逐色**锁住了
（12 列、每种条形的填充色都断言过）。基线是交付物，不能为了汇报去动它 ——
所以这里用**同一份任务数据**（`tools/make_wbs_gantt.py::TASKS`）+ 一张状态表
另生成两份"当前快照"：

    deliverables/WBS_Gantt_ZeyuJin_Current.xlsx   表格 + 状态列 + 按状态着色的甘特条
    deliverables/Current_WBS_Update.pdf           一页 A3 横版：表格 + 甘特图全貌

两者都从 `TASKS` + `STATUS_BY_ID` 渲染，改一处两边同时变，不会出现"PDF 与 Excel 对不上"。

状态口径（截至 2026-11-12）
---------------------------
* Completed  ：已完成并验证（含两轮真实浏览器 + 安卓模拟器验证）
* In Progress：正在做（交付文档与最终报告）
* Planned    ：还没开始（收尾与验收）

用法::

    python tools/make_current_wbs.py             # 两份产物都生成
    python tools/make_current_wbs.py --pdf-only
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")                                   # 无界面渲染
import matplotlib.pyplot as plt                          # noqa: E402
from matplotlib.patches import Polygon, Rectangle        # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from make_wbs_gantt import (                             # noqa: E402
    CHART_END, CHART_START, TASKS, is_external, is_milestone, is_project_summary,
    is_summary, parse_date,
)
from openpyxl import Workbook                            # noqa: E402
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: E402
from openpyxl.utils import get_column_letter              # noqa: E402

XLSX_OUT = ROOT / "deliverables" / "WBS_Gantt_ZeyuJin_Current.xlsx"
PDF_OUT = ROOT / "deliverables" / "Current_WBS_Update.pdf"

# 状态口径：截至 2026-11-12（v1.0.1 已交付、两轮 E2E 全绿）
COMPLETED = "Completed"
IN_PROGRESS = "In Progress"
PLANNED = "Planned"

STATUS_BY_ID = {
    # 1 启动与规划
    "1": COMPLETED, "1.1": COMPLETED, "1.1.1": COMPLETED, "1.1.2": COMPLETED, "1.1.3": COMPLETED,
    # 2 核心开发（含 Word 导出与附页）
    "1.2": COMPLETED, "1.2.1": COMPLETED, "1.2.2": COMPLETED, "1.2.3": COMPLETED,
    "1.2.4": COMPLETED, "1.2.5": COMPLETED,
    # 3 报告管理
    "1.3": COMPLETED, "1.3.1": COMPLETED, "1.3.2": COMPLETED,
    # 4 移动优先 UI
    "1.4": COMPLETED, "1.4.1": COMPLETED, "1.4.2": COMPLETED, "1.4.3": COMPLETED, "1.4.4": COMPLETED,
    # 5 纯前端化（IndexedDB + docx JS + PWA）
    "1.5": COMPLETED, "1.5.1": COMPLETED, "1.5.2": COMPLETED, "1.5.3": COMPLETED,
    "1.5.4": COMPLETED, "1.5.5": COMPLETED,
    # 6 测试与打磨（两轮真实浏览器 + 安卓模拟器验证都归这里）
    "1.6": COMPLETED, "1.6.1": COMPLETED, "1.6.2": COMPLETED, "1.6.3": COMPLETED, "1.6.4": COMPLETED,
    # 7 文档与交付：手册与样例已完成，演示材料与最终报告在写
    "1.7": IN_PROGRESS, "1.7.1": COMPLETED, "1.7.2": COMPLETED,
    "1.7.3": IN_PROGRESS, "1.7.4": IN_PROGRESS,
    # 8 收尾
    "1.8": PLANNED, "1.8.1": PLANNED, "1.8.2": PLANNED,
    # 9 项目完成（里程碑）
    "1.9": PLANNED,
    # 10 客户提供 Word 模板（外部依赖）——已收到并用作对拍基准
    "1.10": COMPLETED,
}

STATUS_COLORS = {
    COMPLETED: "#2E7D32",       # 绿：已完成
    IN_PROGRESS: "#E8A33D",     # 琥珀：进行中
    PLANNED: "#9DB2CE",         # 浅蓝灰：计划中
}
TODAY = date(2026, 11, 12)
AS_OF_LABEL = "as of Nov 12, 2026"

# --------------------------------------------------------------------------
# 派生
# --------------------------------------------------------------------------


def status_of(task_id: str) -> str:
    return STATUS_BY_ID[task_id]


def summarize() -> dict:
    counts = {COMPLETED: 0, IN_PROGRESS: 0, PLANNED: 0}
    for task_id, *_rest in TASKS:
        counts[status_of(task_id)] += 1
    counts["total"] = len(TASKS)
    counts["percent"] = round(counts[COMPLETED] / counts["total"] * 100)
    return counts


def days_of(task: tuple) -> tuple:
    start = parse_date(task[3])
    finish = parse_date(task[4])
    return start, finish


def clean_name(task: tuple) -> str:
    """去掉任务名里的工时备注（汇报表里更干净；工时在源表里保留）。"""
    name = task[1]
    if name.endswith(")") and "(" in name:
        head, _, tail = name.rpartition(" (")
        if any(char.isdigit() for char in tail):
            return head
    return name


# --------------------------------------------------------------------------
# Excel：表格 + 状态列 + 按状态着色的甘特条
# --------------------------------------------------------------------------
INK = "1F2937"
MUTED = "6B7280"
LINE = "BFC7D1"
HEADERS = ["ID", "Task Name", "Duration", "Start", "Finish", "Status", "Predecessors"]
WIDTHS = [7, 52, 10, 13, 13, 14, 14]
FIRST_ROW = 5
DAY_WIDTH = 2.4

THIN = Side(style="thin", color=LINE)
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def write_xlsx(path: Path) -> Path:
    days = []
    current = CHART_START
    while current <= CHART_END:
        days.append(current)
        current += timedelta(days=1)

    wb = Workbook()
    ws = wb.active
    ws.title = "Current WBS"
    ws.sheet_view.showGridLines = False

    last_col = len(HEADERS) + len(days)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(row=1, column=1, value="Current WBS & Gantt — Curtain Wall Inspection Report Tool").font = Font(
        name="Calibri", size=15, bold=True, color="1F4E79")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    counts = summarize()
    ws.cell(row=2, column=1, value=(
        f"{AS_OF_LABEL} · delivery v1.0.1 (53 files, sha256 245f5c9…) · "
        f"Completed {counts[COMPLETED]}/{counts['total']} ({counts['percent']}%) · "
        f"In Progress {counts[IN_PROGRESS]} · Planned {counts[PLANNED]}"
    )).font = Font(name="Calibri", size=10, color=MUTED)

    # 表头
    for index, header in enumerate(HEADERS, start=1):
        cell = ws.cell(row=4, column=index, value=header)
        cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E79")
        cell.alignment = Alignment(horizontal="center" if index != 2 else "left", vertical="center")
        cell.border = BOX
        ws.column_dimensions[get_column_letter(index)].width = WIDTHS[index - 1]
    for index in range(len(HEADERS) + 1, last_col + 1):
        ws.column_dimensions[get_column_letter(index)].width = DAY_WIDTH / 6

    # 日期刻度（每 7 天一个标签，避免糊成一片）
    for offset, day in enumerate(days):
        column = len(HEADERS) + 1 + offset
        cell = ws.cell(row=4, column=column, value=day.day if day.weekday() == 0 or day.day == 1 else None)
        cell.font = Font(name="Calibri", size=7, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E79")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    day_index = {day: index for index, day in enumerate(days)}
    all_ids = {row[0] for row in TASKS}

    for offset, task in enumerate(TASKS):
        row = FIRST_ROW + offset
        task_id, name, duration, start_text, finish_text, predecessors = task
        start, finish = days_of(task)
        status = status_of(task_id)
        is_sum = is_summary(task_id, all_ids)

        values = [task_id, clean_name(task), duration, start_text, finish_text, status, predecessors]
        for index, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=index, value=value)
            cell.font = Font(name="Calibri", size=10,
                             bold=is_sum or is_project_summary(task_id),
                             color=INK if status != COMPLETED else "1F3864")
            cell.alignment = Alignment(horizontal="left" if index == 2 else "center", vertical="center")
            cell.border = BOX
            if offset % 2 == 1:
                cell.fill = PatternFill("solid", fgColor="F7F9FC")
        status_cell = ws.cell(row=row, column=6)
        status_cell.fill = PatternFill("solid", fgColor=STATUS_COLORS[status].lstrip("#"))
        status_cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")

        # 甘特条
        if is_milestone(duration):
            column = len(HEADERS) + 1 + day_index[start]
            cell = ws.cell(row=row, column=column, value="◆")
            cell.font = Font(name="Calibri", size=11, bold=True, color="C00000")
            cell.alignment = Alignment(horizontal="center", vertical="center")
            continue
        fill = PatternFill("solid", fgColor=STATUS_COLORS[status].lstrip("#"))
        for day in range(day_index[start], day_index[finish] + 1):
            cell = ws.cell(row=row, column=len(HEADERS) + 1 + day)
            cell.fill = fill

    # 今天所在列加一条淡红线（表头上标记）
    today_col = len(HEADERS) + 1 + day_index[TODAY] if TODAY in day_index else None
    if today_col:
        ws.cell(row=3, column=today_col, value="▲ today").font = Font(
            name="Calibri", size=8, bold=True, color="C00000")

    # 图例
    legend_row = FIRST_ROW + len(TASKS) + 1
    ws.cell(row=legend_row, column=1, value="Legend").font = Font(
        name="Calibri", size=10, bold=True, color="1F4E79")
    for offset, (label, color) in enumerate(STATUS_COLORS.items()):
        cell = ws.cell(row=legend_row, column=2 + offset * 2, value=label)
        cell.fill = PatternFill("solid", fgColor=color.lstrip("#"))
        cell.font = Font(name="Calibri", size=9, bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    note = ws.cell(row=legend_row + 1, column=1, value=(
        "Source: tools/make_wbs_gantt.py::TASKS (approved baseline, locked by tests) + "
        "STATUS_BY_ID in tools/make_current_wbs.py. Baseline WBS file is left untouched."))
    note.font = Font(name="Calibri", size=8, color=MUTED)

    ws.freeze_panes = "C5"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


# --------------------------------------------------------------------------
# PDF：一页 A3 横版，表格 + 甘特图全貌
# --------------------------------------------------------------------------
FONT_SCALE = 7.4
ROW_TOP = 0.900
ROW_BOTTOM = 0.088
TABLE_X = 0.020
COLUMNS = [
    ("id", 0.020, 0.058),
    ("name", 0.058, 0.352),
    ("start", 0.352, 0.408),
    ("finish", 0.408, 0.464),
    ("status", 0.464, 0.520),
]
GANTT_LEFT = 0.532
GANTT_RIGHT = 0.988


def draw_pdf(path: Path) -> Path:
    days = []
    current = CHART_START
    while current <= CHART_END:
        days.append(current)
        current += timedelta(days=1)
    day_index = {day: index for index, day in enumerate(days)}
    span = len(days)
    counts = summarize()
    all_ids = {row[0] for row in TASKS}

    fig = plt.figure(figsize=(16.54, 11.69))
    fig.patch.set_facecolor("white")

    # ---- 标题区 ----
    fig.text(0.020, 0.968, "Current WBS & Gantt — Curtain Wall Inspection Report Tool",
             fontsize=21, fontweight="bold", color="#1F4E79", va="top")
    fig.text(0.020, 0.940,
             f"Project Status Update · {AS_OF_LABEL} · delivered package v1.0.1 "
             f"(53 files, 465 KB, sha256 245f5c9…)",
             fontsize=10.5, color="#4B5563", va="top")
    fig.text(0.988, 0.940,
             f"Completed {counts[COMPLETED]}/{counts['total']} ({counts['percent']}%)   "
             f"In Progress {counts[IN_PROGRESS]}   Planned {counts[PLANNED]}",
             fontsize=10.5, color="#1F2937", va="top", ha="right", fontweight="bold")

    # ---- 表头 ----
    header_y = ROW_TOP + 0.012
    header_band = Rectangle((TABLE_X, ROW_TOP + 0.004), GANTT_RIGHT - TABLE_X, 0.020,
                            facecolor="#1F4E79", edgecolor="none", transform=fig.transFigure)
    fig.patches.append(header_band)
    for key, x0, x1 in COLUMNS:
        label = {"id": "ID", "name": "Task Name", "start": "Start",
                 "finish": "Finish", "status": "Status"}[key]
        fig.text((x0 + x1) / 2 if key != "name" else x0 + 0.004, header_y - 0.003, label,
                 fontsize=FONT_SCALE + 0.6, fontweight="bold", color="white",
                 ha="center" if key != "name" else "left", va="bottom")
    fig.text((GANTT_LEFT + GANTT_RIGHT) / 2, header_y - 0.003, "Sep 10 – Dec 5, 2026",
             fontsize=FONT_SCALE + 0.6, fontweight="bold", color="white",
             ha="center", va="bottom")

    # ---- 月份带 ----
    month_spans = []
    pointer = 0
    while pointer < span:
        month = days[pointer].month
        end = pointer
        while end + 1 < span and days[end + 1].month == month:
            end += 1
        month_spans.append((pointer, end, days[pointer].strftime("%b")))
        pointer = end + 1
    band_top = ROW_TOP - 0.001
    band_bottom = ROW_TOP - 0.016
    for start_index, end_index, label in month_spans:
        x0 = GANTT_LEFT + (GANTT_RIGHT - GANTT_LEFT) * start_index / span
        x1 = GANTT_LEFT + (GANTT_RIGHT - GANTT_LEFT) * (end_index + 1) / span
        fig.patches.append(Rectangle((x0, band_bottom), x1 - x0, band_top - band_bottom,
                                     facecolor="#E8EDF5", edgecolor="#C7D2E0",
                                     linewidth=0.5, transform=fig.transFigure))
        fig.text((x0 + x1) / 2, band_bottom + 0.003, label, fontsize=FONT_SCALE,
                 color="#1F4E79", ha="center", va="bottom", fontweight="bold")

    # ---- 行 ----
    table_top = band_bottom - 0.004
    row_height = (table_top - ROW_BOTTOM) / len(TASKS)
    for offset, task in enumerate(TASKS):
        task_id, name, duration, start_text, finish_text, _predecessors = task
        start, finish = days_of(task)
        status = status_of(task_id)
        y_text = table_top - row_height * (offset + 0.5)
        if offset % 2 == 1:
            fig.patches.append(Rectangle((TABLE_X, y_text - row_height / 2), GANTT_RIGHT - TABLE_X,
                                         row_height, facecolor="#F7F9FC", edgecolor="none",
                                         transform=fig.transFigure))
        is_sum = is_summary(task_id, all_ids)
        weight = "bold" if (is_sum or is_project_summary(task_id)) else "normal"
        indent = 0.0065 * task_id.count(".")
        fig.text(COLUMNS[0][1] + 0.003, y_text, task_id, fontsize=FONT_SCALE, color="#374151",
                 va="center", ha="left", fontweight=weight)
        fig.text(COLUMNS[1][1] + indent + 0.003, y_text, clean_name(task), fontsize=FONT_SCALE,
                 color="#111827", va="center", ha="left", fontweight=weight)
        for key, text in (("start", start_text), ("finish", finish_text)):
            x0, x1 = dict((item[0], (item[1], item[2])) for item in COLUMNS)[key]
            fig.text((x0 + x1) / 2, y_text, text, fontsize=FONT_SCALE - 0.4, color="#4B5563",
                     va="center", ha="center")
        # 状态徽标
        x0, x1 = COLUMNS[4][1], COLUMNS[4][2]
        badge_width = 0.054
        badge_x = (x0 + x1) / 2 - badge_width / 2
        badge_height = row_height * 0.62
        fig.patches.append(Rectangle((badge_x, y_text - badge_height / 2), badge_width, badge_height,
                                     facecolor=STATUS_COLORS[status], edgecolor="none",
                                     transform=fig.transFigure, clip_on=False))
        fig.text((x0 + x1) / 2, y_text, status, fontsize=FONT_SCALE - 0.8, color="white",
                 va="center", ha="center", fontweight="bold")

        # 甘特条
        if is_milestone(duration):
            x = GANTT_LEFT + (GANTT_RIGHT - GANTT_LEFT) * (day_index[start] + 0.5) / span
            fig.patches.append(Polygon([[x - 0.006, y_text], [x, y_text + 0.0055],
                                        [x + 0.006, y_text], [x, y_text - 0.0055]],
                                       closed=True, facecolor="#C00000", edgecolor="none",
                                       transform=fig.transFigure))
            continue
        x0 = GANTT_LEFT + (GANTT_RIGHT - GANTT_LEFT) * day_index[start] / span
        x1 = GANTT_LEFT + (GANTT_RIGHT - GANTT_LEFT) * (day_index[finish] + 1) / span
        bar_height = row_height * (0.52 if not is_sum else 0.34)
        fig.patches.append(Rectangle((x0, y_text - bar_height / 2), x1 - x0, bar_height,
                                     facecolor=STATUS_COLORS[status], edgecolor="none",
                                     transform=fig.transFigure))

    # ---- 今天线 ----
    if TODAY in day_index:
        x = GANTT_LEFT + (GANTT_RIGHT - GANTT_LEFT) * (day_index[TODAY] + 0.5) / span
        fig.lines.append(plt.Line2D([x, x], [ROW_BOTTOM, band_top], color="#C00000",
                                    linewidth=1.1, linestyle=(0, (3, 2)),
                                    transform=fig.transFigure))
        fig.text(x, band_top + 0.003, "today", fontsize=FONT_SCALE - 0.6, color="#C00000",
                 ha="center", va="bottom", fontweight="bold")

    # ---- 图例与脚注 ----
    legend_y = ROW_BOTTOM - 0.026
    fig.text(TABLE_X, legend_y, "Legend", fontsize=FONT_SCALE + 1, fontweight="bold",
             color="#1F4E79", va="center")
    cursor = TABLE_X + 0.055
    for label, color in STATUS_COLORS.items():
        fig.patches.append(Rectangle((cursor, legend_y - 0.006), 0.022, 0.012,
                                     facecolor=color, edgecolor="none", transform=fig.transFigure))
        fig.text(cursor + 0.026, legend_y, label, fontsize=FONT_SCALE + 0.2, color="#1F2937",
                 va="center")
        cursor += 0.150
    x_legend = cursor + 0.010
    fig.patches.append(Polygon([[x_legend + 0.006, legend_y - 0.006], [x_legend + 0.012, legend_y],
                                [x_legend + 0.006, legend_y + 0.006], [x_legend, legend_y]],
                               closed=True, facecolor="#C00000", edgecolor="none",
                               transform=fig.transFigure))
    fig.text(x_legend + 0.018, legend_y, "Milestone", fontsize=FONT_SCALE + 0.2, color="#1F2937",
             va="center")
    fig.text(TABLE_X, legend_y - 0.030,
             "Scope: 40 WBS tasks from the approved baseline (tools/make_wbs_gantt.py), "
             "status as of Nov 12, 2026 after two rounds of real-browser and Android E2E verification. "
             "The baseline workbook is left untouched; this snapshot is generated from the same task data.",
             fontsize=FONT_SCALE - 0.6, color="#6B7280", va="center")

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="pdf", facecolor="white")
    plt.close(fig)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Current WBS（Excel + PDF）")
    parser.add_argument("--pdf-only", action="store_true", help="只重出 PDF")
    args = parser.parse_args()

    counts = summarize()
    print(f"状态统计：Completed {counts[COMPLETED]} / In Progress {counts[IN_PROGRESS]} / "
          f"Planned {counts[PLANNED]}（共 {counts['total']}，完成 {counts['percent']}%）")
    missing = [row[0] for row in TASKS if row[0] not in STATUS_BY_ID]
    if missing:
        raise SystemExit(f"这些任务没有状态：{missing}")

    if not args.pdf_only:
        print(f"✅ Excel：{write_xlsx(XLSX_OUT).relative_to(ROOT)}")
    print(f"✅ PDF  ：{draw_pdf(PDF_OUT).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
