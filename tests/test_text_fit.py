# -*- coding: utf-8 -*-
"""排版度量工具的冒烟测试（证据工具同样不能腐烂）。"""

from __future__ import annotations

from tools import analyze_text_fit as fit
from webapp.services import word_report as wr


def _rows():
    return fit.analyze(fit.make_measurer())


def test_analyze_covers_all_columns():
    rows = _rows()
    assert len(rows) == len(fit.COLUMN_SPECS) == 7
    assert [row["column"] for row in rows] == [spec[0] for spec in fit.COLUMN_SPECS]
    for row in rows:
        assert row["width"] == wr.GRID_COLS[row["column"]]
        margin = wr.REQUIREMENT_MARGIN if row["name"] == "截面尺寸要求" else wr.CELL_MARGIN_HORIZONTAL
        assert row["usable"] == row["width"] - margin * 2
        assert row["data_lines"] >= 1 and row["header_lines"] >= 1


def test_requirement_column_uses_8pt():
    """要求列的度量必须按 8pt + 60 边距 —— 这正是样例为长条文挤空间的手法。"""
    row = next(row for row in _rows() if row["name"] == "截面尺寸要求")
    assert row["pt"] == wr.REQUIREMENT_PT == 8
    assert row["usable"] == wr.GRID_COLS[wr.COLUMN_INDEX["requirement"]] - wr.REQUIREMENT_MARGIN * 2


def test_analysis_flags_wrapping():
    """真实数据下必然有列折行 —— 这是拿去跟客户谈列宽的证据，不能被"优化"掉。"""
    wrapped = [row["name"] for row in _rows()
               if row["data_lines"] > 1 or row["header_lines"] > 1]
    assert wrapped, "真实数据应当至少暴露一个会折行的列"


def test_markdown_renders():
    text = fit.render_markdown(_rows())
    assert "列宽适配分析" in text
    assert "| 列 |" in text
