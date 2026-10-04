# -*- coding: utf-8 -*-
"""把 WBS 计划喂给 xlsx-gantt，生成另一种渲染风格的甘特图。

两种取数方式（``--source``）
---------------------------
``data``（默认）
    直接用 :data:`tools.make_wbs_gantt.TASKS` —— 也就是**生成自建 xlsx 用的那份原始数据**。
    日期本来就是 ``date`` 对象，不需要序列化再反解析；计划只有一处真相源，
    自建版与 xlsx-gantt 版永远同源，不会出现"两份文件对不上"。

``xlsx``
    从已经生成的 ``WBS_Gantt_ZeyuJin.xlsx`` 里把表读回来再喂进去。
    用途是验证"文件里的内容"与"原始数据"一致（两条路应该产出同样的分区与任务）。

为什么需要这个脚本
------------------
`xlsx-gantt`（PyPI 0.2.3）**是生成器、不是转换器**：``GanttChart`` 只有
``generate_excel`` / ``generate_excel_bytes``，输入是 Python 的
sections/tasks/ranges（或等价 JSON），**没有读 xlsx 的入口**
（已用 ``inspect`` 在已安装的包上核实）。

映射关系（我们的 WBS → xlsx-gantt）
-----------------------------------
    顶层 1         → 项目名 + "Project Summary" 分区里的黑色长条
    二级 1.1~1.10  → 一个 section（列 A 纵向合并的分区名）
    三级 1.x.y     → 该 section 里的 task 行
    二级行本身     → 该 section 的首行（名字后加 "(phase summary)"），用汇总色；
                     名字里的 (NNh) 取出来放进 Time Est.，于是它的 Total 行合计 310h
    1.9（0 工期）  → start == end → xlsx-gantt 渲染成里程碑
    1.10           → 灰条（External Task），资源记 Client

**会丢失的**：xlsx-gantt 的表只有 Activity / Task / Time Est. / Progress 四列 +
日期列，所以我们的 Task Mode / Duration / Predecessors / Baseline Start /
Resource Names 这 5 列无处安放（资源只能变成最右侧的 R/S 标注列，位置在 87 个日期
列之后，实际不可读）。它也不能表达"5 种横条样式 + 红色菱形 + 每日日期数字"。
所以这个产物定位是**另一种视图**，不是替代品 —— 正式交付仍以
``WBS_Gantt_ZeyuJin.xlsx`` 为准。

已知的库问题（本脚本已规避）
----------------------------
``style.weekend_bg = None``（"不要周末灰底"最自然的写法）会抛
``TypeError: fgColor should be Color but value is NoneType`` ——
库内部 ``_solid()`` 没有判空。改用白色等效关闭；周末填充在横条之前写入
（chart.py:801-804 早于 810），所以不会盖住横条。

用法::

    python tools/convert_wbs_to_xlsx_gantt.py                 # 直接用原始数据
    python tools/convert_wbs_to_xlsx_gantt.py --source xlsx   # 从 xlsx 读回来
    python tools/convert_wbs_to_xlsx_gantt.py --theme midnight
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openpyxl import load_workbook                                          # noqa: E402
from xlsx_gantt import GanttChart, GanttTheme                               # noqa: E402

from tools.make_wbs_gantt import (COL_BASELINE, COL_DURATION, COL_FINISH,   # noqa: E402
                                  COL_ID, COL_NAME, COL_PRED, COL_RESOURCE,
                                  COL_START, DEFAULT_OUTPUT, TASKS,
                                  is_external, kind_of, parse_date,
                                  resource_for)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = ROOT / "deliverables" / "WBS_Gantt_ZeyuJin_xlsxgantt.xlsx"

# 与自建版本逐字一致的横条配色
COLOR_PROJECT = "000000"
COLOR_SUMMARY = "1F4E79"
COLOR_TASK = "9DC3E6"
COLOR_EXTERNAL = "A6A6A6"
COLOR_MILESTONE = "C00000"

_HOURS = re.compile(r"\((\d+(?:\.\d+)?)h\)")


# --------------------------------------------------------------------------
# 取数：两条路都归一到同一个 rows 结构，后续映射逻辑完全共用
# --------------------------------------------------------------------------
def rows_from_data() -> list:
    """直接用生成自建 xlsx 的那份原始数据（TASKS）。日期本来就是 date。"""
    return [{
        "id": task_id,
        "name": name,
        "duration": duration,
        "start": parse_date(start_text),
        "finish": parse_date(finish_text),
        "resource": resource_for(task_id),
    } for task_id, name, duration, start_text, finish_text, _predecessors in TASKS]


def rows_from_xlsx(path: Path) -> list:
    """从已生成的 xlsx 里读回 WBS 表（列位置取自 make_wbs_gantt 的 COL_* 常量）。"""
    ws = load_workbook(path).active
    header_row = next(row for row in range(1, 12)
                      if ws.cell(row=row, column=COL_ID).value == "ID")

    def ms_date_to_date(text: str) -> date:
        """把单元格里的 ``Thu 9/10/26`` 还原成 date。"""
        month, day, year = str(text).split()[-1].split("/")
        return date(2000 + int(year), int(month), int(day))

    rows, row = [], header_row + 1
    while ws.cell(row=row, column=COL_ID).value:
        rows.append({
            "id": str(ws.cell(row=row, column=COL_ID).value).strip(),
            "name": str(ws.cell(row=row, column=COL_NAME).value).strip(),
            "duration": str(ws.cell(row=row, column=COL_DURATION).value).strip(),
            "start": ms_date_to_date(ws.cell(row=row, column=COL_START).value),
            "finish": ms_date_to_date(ws.cell(row=row, column=COL_FINISH).value),
            "resource": str(ws.cell(row=row, column=COL_RESOURCE).value or "").strip(),
        })
        row += 1
    return rows


def hours_of(name: str):
    """从分组名里取出 ``(NNh)`` 工时；没有则 None。"""
    match = _HOURS.search(name)
    return float(match.group(1)) if match else None


# --------------------------------------------------------------------------
# 映射：rows → xlsx-gantt 的 sections
# --------------------------------------------------------------------------
def build_sections(rows: list) -> tuple:
    """返回 ``(sections, project_row, resources)``。两条取数路径共用这一份逻辑。"""
    all_ids = {row["id"] for row in rows}
    project_row = next(row for row in rows
                       if kind_of(row["id"], row["duration"], all_ids) == "project")
    groups = [row for row in rows
              if kind_of(row["id"], row["duration"], all_ids) == "summary"]
    children_of = {group["id"]: [row for row in rows
                                 if row["id"].startswith(group["id"] + ".")
                                 and row["id"] != group["id"]]
                   for group in groups}

    def kind_of_row(row) -> str:
        if is_external(row["id"]):
            return "external"
        return kind_of(row["id"], row["duration"], all_ids)

    color_for = {"project": COLOR_PROJECT, "summary": COLOR_SUMMARY,
                 "task": COLOR_TASK, "external": COLOR_EXTERNAL,
                 "milestone": COLOR_MILESTONE}

    def task_of(row, suffix="") -> dict:
        return {
            "name": "%s%s" % (row["name"], suffix),
            "time_estimate": hours_of(row["name"]),
            "progress": None,                 # 源计划没有完成度，不编
            "ranges": [{
                "start": datetime.combine(row["start"], datetime.min.time()),
                "end": datetime.combine(row["finish"], datetime.min.time()),
                "color": color_for[kind_of_row(row)],
            }],
            "annotations": {row["resource"]: "R"} if row["resource"] else {},
        }

    # 顶层项目：单独一个分区，保住那条黑色长条
    sections = [{
        "name": "%s %s" % (project_row["id"], project_row["name"]),
        "tasks": [task_of(project_row)],
    }]

    for group in groups:
        children = children_of[group["id"]]
        # 分区首行 = 二级分组本身：保留它的横条与工时，Total 行才能合计出 310h
        tasks = [task_of(group, suffix=" (phase summary)")]
        for child in children:
            tasks.append(task_of(child, suffix=" %s" % child["id"]))
        sections.append({"name": "%s %s" % (group["id"], group["name"]), "tasks": tasks})

    # 二级但没有子任务的（1.9 里程碑 / 1.10 外部依赖）各自成一个分区。
    # 注意不能用"遍历 groups 再跳过有子任务的"来写 —— 那两行既不是 summary
    # 也不在 groups 里，会被整个漏掉（写这一版时真的漏过一次）。
    group_ids = {group["id"] for group in groups}
    for row in rows:
        if row["id"].count(".") == 1 and row["id"] not in group_ids:
            sections.append({"name": "%s %s" % (row["id"], row["name"]),
                             "tasks": [task_of(row)]})

    resources = []
    for row in rows:
        if row["resource"] and row["resource"] not in resources:
            resources.append(row["resource"])
    return sections, project_row, resources


# --------------------------------------------------------------------------
# 生成
# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="用 xlsx-gantt 渲染同一份 WBS 计划")
    parser.add_argument("--source", choices=("data", "xlsx"), default="data",
                        help="data = 直接用原始 TASKS（默认）；xlsx = 从生成好的表读回来")
    parser.add_argument("--source-file", default=str(DEFAULT_OUTPUT), help="--source xlsx 时的输入文件")
    parser.add_argument("--output", default=str(DEFAULT_TARGET), help="输出 xlsx")
    parser.add_argument("--theme", default="ocean", help="xlsx-gantt 主题名")
    args = parser.parse_args()

    if args.source == "xlsx":
        rows = rows_from_xlsx(Path(args.source_file))
        origin = "xlsx:%s" % Path(args.source_file).name
    else:
        rows = rows_from_data()
        origin = "TASKS（原始数据）"

    sections, project_row, resources = build_sections(rows)

    style = GanttTheme.get(args.theme)
    # 我们的口径是"周末按正常工作日处理"，所以要去掉默认的周末灰底。
    # **不能写 None**：库内部 _solid(s.weekend_bg) 没有判空，传 None 会抛 TypeError。
    # 用白色等效关闭；周末填充在横条之前写入，不会盖住横条。
    style.weekend_bg = "FFFFFF"
    style.week_label_format = "{year} W{week}"

    chart = GanttChart(
        sections=sections,
        start_date=datetime.combine(min(r["start"] for r in rows), datetime.min.time()),
        end_date=datetime.combine(max(r["finish"] for r in rows), datetime.min.time()),
        project_name=project_row["name"],
        resource_names=resources,
        style=style,
    )

    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    chart.generate_excel(str(target))

    print("取数方式：%s（%d 行）" % (origin, len(rows)))
    print("已生成：%s" % target)
    print("  分区 %d 个 / 任务行 %d 行 / 资源 %s / 主题 %s / 工期合计 %.0fh"
          % (len(sections), sum(len(s["tasks"]) for s in sections), resources, args.theme,
             sum(t["time_estimate"] or 0 for s in sections for t in s["tasks"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
