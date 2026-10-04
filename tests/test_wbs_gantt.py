# -*- coding: utf-8 -*-
"""WBS 甘特图交付物（deliverables/WBS_Gantt_ZeyuJin.xlsx）的结构锁定。

与其它交付物一样：**文件由 tools/make_wbs_gantt.py 生成，测试只读文件**。
这样如果有人改了脚本里的数据却忘了重新生成，或者手工改了 Excel，测试会红。

样式用语对齐 MS Project：Project Summary（顶层黑条）/ Summary（深蓝条）/
Task（浅蓝条）/ Milestone（红菱形）/ External Task（灰条）。
图例只列这 5 种 —— 本项目没有 Inactive Task / Split / Deadline 之类，不照抄样例。

（本模块与幕墙工具的业务测试无关，是这份 PM 交付物的自检。）
"""

from __future__ import annotations

import pytest

pytest.importorskip("openpyxl", reason="需要开发依赖 openpyxl")

from datetime import date                                                  # noqa: E402

from openpyxl import load_workbook                                         # noqa: E402

from tools.make_wbs_gantt import (BASELINE_TEXT, CHART_END, CHART_FIRST_COL,  # noqa: E402
                                  CHART_START, COL_BASELINE, COL_DURATION,
                                  COL_FINISH, COL_ID, COL_MODE, COL_NAME, COL_PRED,
                                  COL_RESOURCE, COL_START, DEFAULT_OUTPUT,
                                  FIRST_TASK_ROW, LEGEND, TASK_MODE, TABLE_HEADERS,
                                  TASKS, bar_fill, chart_days, is_external, kind_of,
                                  ms_date, parse_date, resource_for)

BLACK = "000000"
DARK = "1F4E79"
LIGHT = "9DC3E6"
GREY = "A6A6A6"


@pytest.fixture(scope="module")
def sheet():
    assert DEFAULT_OUTPUT.exists(), (
        "缺少交付物，请先运行：python tools/make_wbs_gantt.py"
    )
    return load_workbook(DEFAULT_OUTPUT).active


@pytest.fixture(scope="module")
def days():
    return chart_days()


@pytest.fixture(scope="module")
def all_ids():
    return {row[0] for row in TASKS}


def _rgb(cell) -> str:
    """填充色（后 6 位）；**没有填充时返回空串**。

    注意不能只比颜色：未填充单元格的 ``fgColor`` 默认值也是 ``000000``，
    只比颜色会把"根本没画条"误判成"画了黑色 Project Summary 条"，
    所以必须先看 ``patternType``。
    """
    fill = cell.fill
    if fill is None or fill.patternType is None:
        return ""
    return str(fill.fgColor.rgb or "")[-6:].upper()


def _row_of(task_id: str) -> int:
    return FIRST_TASK_ROW + [row[0] for row in TASKS].index(task_id)


def _index(days):
    return {day: index for index, day in enumerate(days)}


# --------------------------------------------------------------------------
# 版面
# --------------------------------------------------------------------------
def test_axis_covers_every_calendar_day(sheet, days):
    assert CHART_START.isoformat() == "2026-09-10"
    assert CHART_END.isoformat() == "2026-12-05"
    assert len(days) == 87
    assert sheet.max_column == CHART_FIRST_COL + len(days) - 1


def test_table_has_nine_columns_with_task_mode_after_id(sheet):
    assert [sheet.cell(row=3, column=i).value for i in range(1, COL_RESOURCE + 1)] == \
        TABLE_HEADERS
    assert TABLE_HEADERS == ["ID", "Task Mode", "Task Name", "Duration", "Start",
                             "Finish", "Predecessors", "Baseline Start", "Resource Names"]
    assert COL_MODE == COL_ID + 1                       # Task Mode 紧跟 ID


def test_baseline_start_column_sits_between_predecessors_and_resource(sheet):
    """Baseline Start 插在 Predecessors 与 Resource Names 之间。"""
    assert COL_BASELINE == COL_PRED + 1
    assert COL_RESOURCE == COL_BASELINE + 1
    assert sheet.cell(row=3, column=COL_BASELINE).value == "Baseline Start"


def test_baseline_start_is_na_for_every_row(sheet):
    """本项目没有正式的基线管理，Baseline Start 全为 NA。"""
    assert BASELINE_TEXT == "NA"
    for offset, row_spec in enumerate(TASKS):
        cell = sheet.cell(row=FIRST_TASK_ROW + offset, column=COL_BASELINE)
        assert cell.value == "NA", "%s 的 Baseline Start 应为 NA" % row_spec[0]


def test_all_source_rows_are_present_verbatim(sheet):
    for offset, (task_id, name, duration, start, finish, predecessors) in enumerate(TASKS):
        row = FIRST_TASK_ROW + offset
        assert sheet.cell(row=row, column=COL_ID).value == task_id
        assert sheet.cell(row=row, column=COL_MODE).value == TASK_MODE
        assert sheet.cell(row=row, column=COL_NAME).value == name
        assert sheet.cell(row=row, column=COL_DURATION).value == duration
        assert sheet.cell(row=row, column=COL_START).value == ms_date(parse_date(start))
        assert sheet.cell(row=row, column=COL_FINISH).value == ms_date(parse_date(finish))
        assert sheet.cell(row=row, column=COL_PRED).value == predecessors


def test_task_mode_is_auto_scheduled_for_every_row(sheet):
    for offset in range(len(TASKS)):
        assert sheet.cell(row=FIRST_TASK_ROW + offset, column=COL_MODE).value == "Auto Scheduled"


def test_dates_use_ms_project_text_format(sheet):
    """`Thu 9/10/26` 这种格式：周几 + 月/日/年，且是**文本**（不随 Excel 语言变）。"""
    row = _row_of("1.1.1")
    start = sheet.cell(row=row, column=COL_START)
    finish = sheet.cell(row=row, column=COL_FINISH)
    assert start.value == "Thu 9/10/26"
    assert finish.value == "Fri 9/11/26"
    assert isinstance(start.value, str)               # 不是 datetime

    # 抽查几个跨月/跨周的日期，确认星期几算对了
    assert sheet.cell(row=_row_of("1.9"), column=COL_START).value == "Sat 12/5/26"
    assert sheet.cell(row=_row_of("1.5.3"), column=COL_START).value == "Tue 10/13/26"
    assert sheet.cell(row=_row_of("1.8.2"), column=COL_FINISH).value == "Wed 12/2/26"


def test_month_band_labels(sheet, days):
    index = _index(days)
    assert sheet.cell(row=1, column=CHART_FIRST_COL).value == "Sep 2026"
    for month, name in ((10, "Oct"), (11, "Nov"), (12, "Dec")):
        column = CHART_FIRST_COL + index[date(2026, month, 1)]
        assert sheet.cell(row=1, column=column).value == "%s 2026" % name


def test_weekends_are_normal_working_days_so_not_shaded(sheet, days):
    """周末按正常工作日处理、不扣节假日 —— 所以周末列没有特殊底色。"""
    index = _index(days)
    for day in (date(2026, 9, 12), date(2026, 9, 13), date(2026, 10, 3)):   # 六、日、六
        assert day.weekday() >= 5
        cell = sheet.cell(row=2, column=CHART_FIRST_COL + index[day])
        assert _rgb(cell) == "", "%s 不该有填充" % day


def test_date_numbers_appear_on_mondays_and_month_starts(sheet, days):
    index = _index(days)
    assert sheet.cell(row=2, column=CHART_FIRST_COL + index[date(2026, 9, 14)]).value == 14
    assert sheet.cell(row=2, column=CHART_FIRST_COL + index[date(2026, 9, 15)]).value is None


# --------------------------------------------------------------------------
# 表格样式：层级、加粗、缩进
# --------------------------------------------------------------------------
def test_kind_classification(all_ids):
    assert kind_of("1", "62 days", all_ids) == "project"          # 顶层 = Project Summary
    for task_id in ("1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8"):
        assert kind_of(task_id, "5 days", all_ids) == "summary"
    assert kind_of("1.9", "0 days", all_ids) == "milestone"
    assert kind_of("1.10", "7 days", all_ids) == "task"            # External Task
    assert is_external("1.10") and not is_external("1.5.3")


def test_project_summary_row_is_bold_and_black(sheet):
    row = _row_of("1")
    assert sheet.cell(row=row, column=COL_NAME).font.b
    assert sheet.cell(row=row, column=COL_NAME).font.color.rgb.endswith(BLACK)
    assert sheet.cell(row=row, column=COL_NAME).alignment.indent in (0, None)


def test_summary_rows_are_bold_and_not_indented(sheet, all_ids):
    summaries = [row[0] for row in TASKS
                 if kind_of(row[0], row[2], all_ids) == "summary"]
    assert summaries == ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8"]

    for task_id in summaries:
        cell = sheet.cell(row=_row_of(task_id), column=COL_NAME)
        assert cell.font.b, "%s 汇总行应加粗" % task_id
        assert cell.alignment.indent in (0, None), "%s 汇总行不应缩进" % task_id


def test_leaf_tasks_are_indented_by_wbs_level(sheet, all_ids):
    checked = 0
    for task_id, _name, duration, _s, _f, _p in TASKS:
        if kind_of(task_id, duration, all_ids) != "task":
            continue
        indent = sheet.cell(row=_row_of(task_id), column=COL_NAME).alignment.indent
        assert indent == task_id.count("."), "%s 缩进应为 %d" % (task_id, task_id.count("."))
        checked += 1
    assert checked == 30


# --------------------------------------------------------------------------
# 横条：4 种颜色 + 1 种菱形
# --------------------------------------------------------------------------
def test_bar_fill_helper_maps_each_kind(all_ids):
    assert bar_fill("1", "project").fgColor.rgb.endswith(BLACK)
    assert bar_fill("1.1", "summary").fgColor.rgb.endswith(DARK)
    assert bar_fill("1.1.1", "task").fgColor.rgb.endswith(LIGHT)
    assert bar_fill("1.10", "task").fgColor.rgb.endswith(GREY)     # External Task
    assert bar_fill("1.9", "milestone") is None                     # 菱形，无填充


def test_project_summary_bar_is_a_black_band(sheet, days):
    row = _row_of("1")
    for offset in range(len(days)):
        assert _rgb(sheet.cell(row=row, column=CHART_FIRST_COL + offset)) == BLACK


def test_summary_bars_are_dark_and_cover_their_range(sheet, days, all_ids):
    index = _index(days)
    for task_id, _name, duration, start, finish, _p in TASKS:
        if kind_of(task_id, duration, all_ids) != "summary":
            continue
        row = _row_of(task_id)
        first, last = index[parse_date(start)], index[parse_date(finish)]
        for offset in range(first, last + 1):
            assert _rgb(sheet.cell(row=row, column=CHART_FIRST_COL + offset)) == DARK, \
                "%s 第 %d 列应为深蓝汇总条" % (task_id, offset)
        leftover = [offset for offset in range(len(days)) if offset < first or offset > last
                    if _rgb(sheet.cell(row=row, column=CHART_FIRST_COL + offset)) == DARK]
        assert leftover == [], "%s 横条溢出 %s" % (task_id, leftover)


def test_task_bars_are_light_and_cover_their_range(sheet, days, all_ids):
    index = _index(days)
    for task_id, _name, duration, start, finish, _p in TASKS:
        if kind_of(task_id, duration, all_ids) != "task" or is_external(task_id):
            continue
        row = _row_of(task_id)
        first, last = index[parse_date(start)], index[parse_date(finish)]
        for offset in range(first, last + 1):
            assert _rgb(sheet.cell(row=row, column=CHART_FIRST_COL + offset)) == LIGHT, \
                "%s 第 %d 列应为浅蓝子任务条" % (task_id, offset)


def test_external_task_bar_is_grey_not_blue(sheet, days):
    """1.10 是对客户的外部依赖，与主线并行，用灰色条区别于内部任务。"""
    index = _index(days)
    row = _row_of("1.10")
    first, last = index[parse_date("10/1/26")], index[parse_date("10/9/26")]
    for offset in range(first, last + 1):
        assert _rgb(sheet.cell(row=row, column=CHART_FIRST_COL + offset)) == GREY

    # 同区间的内部任务仍是浅蓝，两种样式并存
    other = _row_of("1.4.3")                     # 10/1–10/2
    assert _rgb(sheet.cell(row=other, column=CHART_FIRST_COL + first)) == LIGHT


def test_milestone_is_a_diamond(sheet, days):
    index = _index(days)
    row = _row_of("1.9")
    cell = sheet.cell(row=row, column=CHART_FIRST_COL + index[parse_date("12/5/26")])
    assert cell.value == "◆"
    assert sheet.cell(row=row, column=COL_DURATION).value == "0 days"


def test_resource_names_column_fills_every_row(sheet):
    assert sheet.cell(row=3, column=COL_RESOURCE).value == "Resource Names"
    for task_id, _n, _d, _s, _f, _p in TASKS:
        assert sheet.cell(row=_row_of(task_id), column=COL_RESOURCE).value == \
            resource_for(task_id)
    assert resource_for("1.10") == "Client"
    assert resource_for("1.5.3") == "Zeyu Jin"


# --------------------------------------------------------------------------
# 图例：恰好 5 种，且都是本项目用到的
# --------------------------------------------------------------------------
def test_legend_lists_exactly_the_five_used_types(sheet):
    legend_rows = [row for row in range(FIRST_TASK_ROW, sheet.max_row + 1)
                   if sheet.cell(row=row, column=1).value == "Legend / 图例"]
    assert len(legend_rows) == 1

    row = legend_rows[0] + 1
    labels = [sheet.cell(row=row, column=1 + 4 * index + 1).value for index in range(5)]
    assert labels == ["Task", "Summary", "Project Summary", "Milestone", "External Task"]
    assert len(LEGEND) == 5

    # 样例里有、本项目没用到的类型不能出现
    text = " ".join(str(cell) for cell in labels)
    for unused in ("Inactive Task", "Inactive Milestone", "Split", "Deadline",
                   "Manual Task", "Duration Only", "Baseline"):
        assert unused not in text


def test_legend_swatches_match_the_bars(sheet):
    legend_row = [row for row in range(FIRST_TASK_ROW, sheet.max_row + 1)
                  if sheet.cell(row=row, column=1).value == "Legend / 图例"][0] + 1
    assert _rgb(sheet.cell(row=legend_row, column=1)) == LIGHT        # Task
    assert _rgb(sheet.cell(row=legend_row, column=5)) == DARK         # Summary
    assert _rgb(sheet.cell(row=legend_row, column=9)) == BLACK        # Project Summary
    assert sheet.cell(row=legend_row, column=13).value == "◆"          # Milestone
    assert _rgb(sheet.cell(row=legend_row, column=17)) == GREY        # External Task


def test_subtitle_states_the_contingency_range(sheet):
    """副标题写清 310h identified + 20–40h contingency = 330–350h total。"""
    subtitle = str(sheet.cell(row=2, column=1).value)
    assert "310h identified" in subtitle
    assert "20–40h contingency" in subtitle
    assert "330–350h total" in subtitle


def test_notes_explain_axis_dates_and_missing_columns(sheet):
    text = " ".join(str(sheet.cell(row=row, column=1).value or "")
                    for row in range(FIRST_TASK_ROW, sheet.max_row + 1))
    assert "Thu 9/10/26" in text                    # 日期格式说明
    assert "Weekends are treated as" in text
    assert "no formal baseline management" in text  # 说明为何 Baseline Start 全是 NA
    assert "Baseline Start is NA" in text
    assert "Resource Names was not in the source list" in text
    assert "External Task, grey bar" in text


def test_freeze_panes_keeps_header_and_table_visible(sheet):
    from openpyxl.utils import get_column_letter
    assert sheet.freeze_panes == "%s4" % get_column_letter(CHART_FIRST_COL) == "J4"
