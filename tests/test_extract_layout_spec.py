# -*- coding: utf-8 -*-
"""版式规格提取器的契约测试。

提取器是"换对拍基准"时的取证工具：客户给来真实报告后，靠它判断哪些版式数值与现基准不同。
所以它必须与手工维护的 `report_layout.json` 保持一致 —— 二者要改就一起改。
"""

from __future__ import annotations

from tools.extract_layout_spec import compare, extract
from webapp import config
from webapp.services import word_report as wr


def test_extractor_reproduces_current_spec():
    """对当前基准样例提取出来的规格，必须与 report_layout.json 一致。

    唯一允许的差异是**列宽**：楼层列与读数列是对样例的有意偏离，
    已声明在 `columns._widthOverrides`（样例的 492 twips 连「二十三层」都放不下）。
    """
    candidate = extract(config.GOLDEN_SAMPLE)
    diffs = compare(wr.SPEC, candidate)
    assert [key for key, _old, _new in diffs] == ["columns.widths"], (
        "除已声明的列宽偏离外不应有其他差异：\n"
        + "\n".join("  %s 当前=%r 提取=%r" % item for item in diffs)
    )


def test_extracted_width_deviation_matches_declared_overrides():
    """提取器读到的样例列宽，与规格的差异必须恰好等于 _widthOverrides 声明的列。"""
    candidate = extract(config.GOLDEN_SAMPLE)
    sample_widths = candidate["columns"]["widths"]
    differing = [index for index, (old, new) in enumerate(zip(sample_widths, wr.GRID_COLS))
                 if old != new]
    overrides = wr.SPEC["columns"]["_widthOverrides"]
    assert differing == [wr.COLUMN_INDEX["floor"]] + list(overrides["reading"]["columns"])
    assert sample_widths[wr.COLUMN_INDEX["floor"]] == overrides["floor"]["sampleTwips"]


def test_extractor_handles_both_detection_tables():
    """立柱表与横梁表的版式规格相同（换基准时两张表都要看）。"""
    column = extract(config.GOLDEN_SAMPLE, table_ordinal=1)
    beam = extract(config.GOLDEN_SAMPLE, table_ordinal=2)
    assert column["columns"]["widths"] == beam["columns"]["widths"]
    assert column["headers"]["fixed"] == beam["headers"]["fixed"]


def test_extractor_detects_structure_generically():
    """结构靠 gridSpan / vMerge 泛化识别，而不是写死 11 列。"""
    spec = extract(config.GOLDEN_SAMPLE)
    assert spec["spans"]["thickness"] == 7
    assert spec["columns"]["index"]["face"] == 3
    assert spec["columns"]["index"]["readingCount"] == 5
    assert spec["columns"]["index"]["requirement"] == 10
    assert spec["headers"]["thicknessSub"] == ["面", "1", "2", "3", "4", "5", "最小"]
    assert len(spec["columns"]["widths"]) == 11


def test_extractor_warns_when_structure_cannot_be_confirmed():
    """基准样例的构件都只有 1 个面 → 检不出纵向合并列，必须给出提示而不是静默留空。"""
    spec = extract(config.GOLDEN_SAMPLE)
    warnings = " ".join(spec["_warnings"])
    assert "vMerge" in warnings
    # 检不出时沿用当前规格值，而不是写成空列表
    assert spec["columns"]["mergedInBody"] == list(wr.MERGED_IN_BODY)
