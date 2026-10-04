# -*- coding: utf-8 -*-
"""xlsx-gantt 版甘特图（另一种视图）的映射自检。

注意这是一份**派生视图**，不是正式交付物：xlsx-gantt 的表结构里没有
Task Mode / Duration / Predecessors / Baseline Start / Resource Names，
也没有"5 种横条样式 + 红色菱形"。正式交付仍以 ``WBS_Gantt_ZeyuJin.xlsx`` 为准。

同时要说清这个测试的**盲区**：下面那条"两条取数路径等价"只能证明
*读文件*与*用原始数据*走的是同一套映射，**证明不了映射本身对不对** ——
两条路共用 ``build_sections()``，映射写错了两边一起错（写这一版时就真的漏过
1.9 与 1.10 两行）。所以必须另有对**绝对数量**的断言（40 行 / 11 分区 / 310h）。
"""

from __future__ import annotations

import warnings

import pytest

pytest.importorskip("openpyxl", reason="需要开发依赖 openpyxl")
pytest.importorskip("xlsx_gantt", reason="需要实验依赖 xlsx-gantt：pip install xlsx-gantt")

from openpyxl import load_workbook                                        # noqa: E402

from tools.convert_wbs_to_xlsx_gantt import (COLOR_EXTERNAL, COLOR_MILESTONE,  # noqa: E402
                                            COLOR_PROJECT, COLOR_SUMMARY,
                                            COLOR_TASK, DEFAULT_TARGET,
                                            build_sections, rows_from_data)
from tools.make_wbs_gantt import TASKS                                    # noqa: E402
from tools.convert_wbs_to_xlsx_gantt import rows_from_xlsx                # noqa: E402
from tools.make_wbs_gantt import DEFAULT_OUTPUT                           # noqa: E402


@pytest.fixture(scope="module")
def sections():
    return build_sections(rows_from_data())


# --------------------------------------------------------------------------
# 映射（纯函数，快）
# --------------------------------------------------------------------------
def test_every_source_row_is_mapped(sections):
    """绝对数量断言 —— 这是唯一能抓住"漏行"的一类检查。"""
    built, project_row, resources = sections
    mapped = sum(len(section["tasks"]) for section in built)

    assert len(TASKS) == 40
    assert mapped == len(TASKS), "映射后的任务行数必须等于源数据行数"
    assert len(built) == 11                       # 1 个顶层 + 8 个分组 + 1.9 + 1.10
    assert project_row["id"] == "1"
    assert resources == ["Zeyu Jin", "Client"]


def test_total_effort_is_310_hours(sections):
    """分组名里的 (NNh) 被取出来放进 Time Est.，合计应正好 310h。"""
    built, _project, _resources = sections
    estimates = [task["time_estimate"] for section in built for task in section["tasks"]]
    assert sum(value for value in estimates if value) == 310
    assert sorted(value for value in estimates if value) == [15, 15, 20, 25, 35, 40, 60, 100]


def test_milestone_and_external_task_are_present(sections):
    built, _project, _resources = sections
    by_name = {task["name"]: task for section in built for task in section["tasks"]}

    milestone = by_name["Project Completion"]
    rng = milestone["ranges"][0]
    assert rng["start"] == rng["end"]              # start == end → xlsx-gantt 画里程碑
    assert rng["color"] == COLOR_MILESTONE

    external = next(task for name, task in by_name.items()
                    if name.startswith("Client Final Word Template"))
    assert external["ranges"][0]["color"] == COLOR_EXTERNAL


def test_five_bar_colors_match_the_primary_file(sections):
    """横条配色与自建版逐字一致（黑 / 深蓝 / 浅蓝 / 灰 / 红）。"""
    built, _project, _resources = sections
    used = {task["ranges"][0]["color"] for section in built for task in section["tasks"]}
    assert used == {COLOR_PROJECT, COLOR_SUMMARY, COLOR_TASK, COLOR_EXTERNAL,
                    COLOR_MILESTONE}


def test_progress_is_left_empty(sections):
    """源计划没有完成度数据，不编 —— 留空而不是填 0 或 100。"""
    built, _project, _resources = sections
    assert all(task["progress"] is None for section in built for task in section["tasks"])


def test_both_data_paths_agree(sections):
    """读文件与用原始数据必须产出同样的分区与任务（映射共用，所以只证明取数一致）。"""
    from_xlsx = build_sections(rows_from_xlsx(DEFAULT_OUTPUT))
    assert len(from_xlsx[0]) == len(sections[0])
    for expected, actual in zip(sections[0], from_xlsx[0]):
        assert expected["name"] == actual["name"]
        assert [t["name"] for t in expected["tasks"]] == [t["name"] for t in actual["tasks"]]
        assert [t["ranges"][0]["start"] for t in expected["tasks"]] == \
               [t["ranges"][0]["start"] for t in actual["tasks"]]


# --------------------------------------------------------------------------
# 生成物（只读文件，不重新生成）
# --------------------------------------------------------------------------
def test_generated_workbook_has_a_total_row_of_310():
    assert DEFAULT_TARGET.exists(), (
        "缺少 xlsx-gantt 版产物，请先运行：python tools/convert_wbs_to_xlsx_gantt.py"
    )
    with warnings.catch_warnings():
        # 库里注入了 x14 DataBar 扩展 XML，openpyxl 读不懂会警告；只是读，不写回，无影响
        warnings.simplefilter("ignore")
        ws = load_workbook(DEFAULT_TARGET).active

    assert ws.title == "Gantt Chart"
    assert ws.cell(row=3, column=1).value == "Activity"
    assert ws.cell(row=3, column=2).value == "Task"
    assert ws.cell(row=3, column=3).value == "Time Est."

    total_row = ws.max_row
    assert ws.cell(row=total_row, column=1).value == "Total"
    assert ws.cell(row=total_row, column=3).value == 310


def test_generated_workbook_has_no_weekend_shading():
    """周末是正常工作日：周末列的底色被我们改成白色（库不认 weekend_bg=None）。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ws = load_workbook(DEFAULT_TARGET).active

    # 第 1.1.1 行（9/10–9/11）不覆盖周六 9/12，那一格应该是白色而非默认灰 EFEFEF
    saturday_column = 7                            # 9/12 是第 3 个日期列（E=5 起）
    row = 6
    fill = ws.cell(row=row, column=saturday_column).fill
    color = str(fill.fgColor.rgb)[-6:] if fill and fill.patternType else ""
    assert color == "FFFFFF", "周末列不该是默认灰底 %s" % color
