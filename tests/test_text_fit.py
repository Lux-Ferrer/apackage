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
    margin = fit.cell_margin_twips()
    for row in rows:
        assert row["width"] == wr.GRID_COLS[row["column"]]
        assert row["usable"] == row["width"] - margin * 2
        assert row["data_lines"] >= 1 and row["header_lines"] >= 1


def test_cell_margin_falls_back_to_table_level():
    """真实表格不在单元格上设 tcMar，内边距取表级 tblCellMar。"""
    assert wr.CELL_MARGIN_HORIZONTAL is None
    assert fit.cell_margin_twips() == wr.SPEC["table"]["tableCellMargin"]["left"] == 57


def test_all_columns_use_inherited_font_size():
    """真实表格的单元格一律不显式设字号（含要求列），故全部按继承字号度量。"""
    assert wr.REQUIREMENT_PT is None
    assert fit.column_pt("requirement") == wr.INHERITED_TABLE_PT
    assert fit.column_pt("inherited") == wr.INHERITED_TABLE_PT


def test_multiline_header_counts_paragraphs_separately():
    """表头里的 \\n 是真实表格的多个段落，段落之间不共享行。"""
    measure = fit.make_measurer()
    # 足够宽时：两段 = 两行，一段 = 一行
    assert fit.lines_needed("a\nb", measure, 10, 10000) == 2
    assert fit.lines_needed("ab", measure, 10, 10000) == 1
    # 换行成两段后，总行数不会少于合并成一段
    single = fit.lines_needed("检测构件位置", measure, 10, 736)
    split = fit.lines_needed("检测构件\n位置", measure, 10, 736)
    assert split > single


def test_markdown_renders():
    text = fit.render_markdown(_rows())
    assert "列宽适配分析" in text
    assert "| 列 |" in text
