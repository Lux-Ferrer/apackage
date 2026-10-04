# -*- coding: utf-8 -*-
"""WBS 甘特图交付物（deliverables/WBS_Gantt_ZeyuJin.xlsx）的结构锁定。

与其它交付物一样：**文件由 tools/make_wbs_gantt.py 生成，测试只读文件**。
这样如果有人改了脚本里的数据却忘了重新生成，或者手工改了 Excel，测试会红。

（本模块与幕墙工具的业务测试无关，是这份 PM 交付物的自检。）
"""

from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("openpyxl", reason="需要开发依赖 openpyxl")

from openpyxl import load_workbook                                    # noqa: E402

from tools.make_wbs_gantt import (CHART_END, CHART_FIRST_COL, CHART_START,  # noqa: E402
                                  DEFAULT_OUTPUT, FIRST_TASK_ROW, TASKS,
                                  chart_days, kind_of, parse_date, resource_for)

DARK = "1F4E79"
LIGHT = "9DC3E6"

TABLE_HEADERS = ["ID", "Task Name", "Duration", "Start", "Finish", "Predecessors", "Resource"]


@pytest.fixture(scope="module")
def sheet():
    assert DEFAULT_OUTPUT.exists(), (
        "缺少交付物，请先运行：python tools/make_wbs_gantt.py"
    )
    return load_workbook(DEFAULT_OUTPUT).active


@pytest.fixture(scope="module")
def days():
    return chart_days()


def _rgb(cell) -> str:
    """openpyxl 回读颜色是 8 位 ARGB，统一取后 6 位。"""
    return str(cell.fill.fgColor.rgb or "")[-6:].upper()


def _row_of(task_id: str) -> int:
    return FIRST_TASK_ROW + [row[0] for row in TASKS].index(task_id)


# --------------------------------------------------------------------------
# 版面
# --------------------------------------------------------------------------
def test_axis_covers_every_calendar_day(sheet, days):
    assert CHART_START.isoformat() == "2026-09-10"
    assert CHART_END.isoformat() == "2026-12-05"
    assert len(days) == 87
    assert sheet.max_column == CHART_FIRST_COL + len(days) - 1


def test_table_headers(sheet):
    assert [sheet.cell(row=3, column=i).value for i in range(1, 8)] == TABLE_HEADERS


def test_all_source_rows_are_present_verbatim(sheet):
    for offset, (task_id, name, duration, start, finish, predecessors) in enumerate(TASKS):
        row = FIRST_TASK_ROW + offset
        assert sheet.cell(row=row, column=1).value == task_id
        assert sheet.cell(row=row, column=2).value == name
        assert sheet.cell(row=row, column=3).value == duration
        assert sheet.cell(row=row, column=4).value.date() == parse_date(start)
        assert sheet.cell(row=row, column=5).value.date() == parse_date(finish)
        assert sheet.cell(row=row, column=6).value == predecessors


def test_month_band_labels(sheet, days):
    index = {day: i for i, day in enumerate(days)}
    from datetime import date
    assert sheet.cell(row=1, column=CHART_FIRST_COL).value == "Sep 2026"
    for month in (10, 11, 12):
        column = CHART_FIRST_COL + index[date(2026, month, 1)]
        assert sheet.cell(row=1, column=column).value == "%s 2026" % \
            {10: "Oct", 11: "Nov", 12: "Dec"}[month]


def test_weekends_are_normal_working_days_so_not_shaded(sheet, days):
    """周末按正常工作日处理、不扣节假日 —— 所以周末列没有特殊底色。"""
    index = {day: i for i, day in enumerate(days)}
    from datetime import date
    for day in (date(2026, 9, 12), date(2026, 9, 13), date(2026, 10, 3)):   # 六、日、六
        assert day.weekday() >= 5
        cell = sheet.cell(row=2, column=CHART_FIRST_COL + index[day])
        assert _rgb(cell) in ("", "000000"), "%s 不该有底色" % day


def test_date_numbers_appear_on_mondays_and_month_starts(sheet, days):
    from datetime import date
    index = {day: i for i, day in enumerate(days)}
    monday = sheet.cell(row=2, column=CHART_FIRST_COL + index[date(2026, 9, 14)])
    tuesday = sheet.cell(row=2, column=CHART_FIRST_COL + index[date(2026, 9, 15)])
    assert monday.value == 14
    assert tuesday.value is None


# --------------------------------------------------------------------------
# 表格样式：汇总加粗、子任务缩进
# --------------------------------------------------------------------------
def test_summary_rows_are_bold_and_not_indented(sheet):
    summaries = [row[0] for row in TASKS
                 if kind_of(row[0], row[2], {r[0] for r in TASKS}) == "summary"]
    assert summaries == ["1", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8"]

    for task_id in summaries:
        cell = sheet.cell(row=_row_of(task_id), column=2)
        assert cell.font.b, "%s 汇总行应加粗" % task_id
        assert cell.alignment.indent in (0, None), "%s 汇总行不应缩进" % task_id


def test_leaf_tasks_are_indented_by_wbs_level(sheet):
    all_ids = {row[0] for row in TASKS}
    checked = 0
    for task_id, _name, duration, _s, _f, _p in TASKS:
        if kind_of(task_id, duration, all_ids) != "task":
            continue
        indent = sheet.cell(row=_row_of(task_id), column=2).alignment.indent
        assert indent == task_id.count("."), "%s 缩进应为 %d" % (task_id, task_id.count("."))
        checked += 1
    assert checked == 30


# --------------------------------------------------------------------------
# 甘特条
# --------------------------------------------------------------------------
def test_summary_bars_are_dark_and_cover_their_range(sheet, days):
    index = {day: i for i, day in enumerate(days)}
    for task_id, _name, duration, start, finish, _p in TASKS:
        if kind_of(task_id, duration, {r[0] for r in TASKS}) != "summary":
            continue
        row = _row_of(task_id)
        first, last = index[parse_date(start)], index[parse_date(finish)]
        for offset in range(first, last + 1):
            cell = sheet.cell(row=row, column=CHART_FIRST_COL + offset)
            assert _rgb(cell) == DARK, "%s 第 %d 列应为深色汇总条" % (task_id, offset)
        # 区间之外不能有深色残留
        leftover = [offset for offset in range(len(days)) if offset < first or offset > last
                    if _rgb(sheet.cell(row=row, column=CHART_FIRST_COL + offset)) == DARK]
        assert leftover == [], "%s 横条溢出 %s" % (task_id, leftover)


def test_task_bars_are_light_and_cover_their_range(sheet, days):
    index = {day: i for i, day in enumerate(days)}
    for task_id, _name, duration, start, finish, _p in TASKS:
        if kind_of(task_id, duration, {r[0] for r in TASKS}) != "task":
            continue
        row = _row_of(task_id)
        first, last = index[parse_date(start)], index[parse_date(finish)]
        for offset in range(first, last + 1):
            cell = sheet.cell(row=row, column=CHART_FIRST_COL + offset)
            assert _rgb(cell) == LIGHT, "%s 第 %d 列应为浅色子任务条" % (task_id, offset)


def test_milestone_is_a_diamond(sheet, days):
    index = {day: i for i, day in enumerate(days)}
    row = _row_of("1.9")
    cell = sheet.cell(row=row, column=CHART_FIRST_COL + index[parse_date("12/5/26")])
    assert cell.value == "◆"
    assert sheet.cell(row=row, column=3).value == "0 days"


def test_external_dependency_has_its_own_bar(sheet, days):
    """1.10 是对客户的外部依赖，与主线并行，必须画出来。"""
    index = {day: i for i, day in enumerate(days)}
    row = _row_of("1.10")
    first, last = index[parse_date("10/1/26")], index[parse_date("10/9/26")]
    for offset in (first, last, (first + last) // 2):
        assert _rgb(sheet.cell(row=row, column=CHART_FIRST_COL + offset)) == LIGHT


def test_resource_column_fills_every_row(sheet):
    for task_id, _n, _d, _s, _f, _p in TASKS:
        assert sheet.cell(row=_row_of(task_id), column=7).value == resource_for(task_id)
    assert resource_for("1.10") == "Client"
    assert resource_for("1.5.3") == "Zeyu Jin"


# --------------------------------------------------------------------------
# 图例
# --------------------------------------------------------------------------
def test_legend_has_three_entries(sheet):
    legend_rows = [row for row in range(FIRST_TASK_ROW, sheet.max_row + 1)
                   if sheet.cell(row=row, column=1).value == "Legend / 图例"]
    assert len(legend_rows) == 1

    row = legend_rows[0] + 1
    assert [sheet.cell(row=row, column=column).value for column in (2, 6, 10)] == \
        ["Summary", "Task", "Milestone"]
    assert _rgb(sheet.cell(row=row, column=1)) == DARK        # Summary 色块
    assert _rgb(sheet.cell(row=row, column=5)) == LIGHT       # Task 色块
    assert sheet.cell(row=row, column=9).value == "◆"          # Milestone 菱形


def test_notes_explain_the_axis_and_the_inferred_resource(sheet):
    text = " ".join(str(sheet.cell(row=row, column=1).value or "")
                    for row in range(FIRST_TASK_ROW, sheet.max_row + 1))
    assert "Weekends are treated as" in text
    assert "Resource column was not in the source list" in text
    assert "milestones" in text


def test_freeze_panes_keeps_header_and_table_visible(sheet):
    assert sheet.freeze_panes == "H4"
