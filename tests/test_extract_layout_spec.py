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
    """对当前基准 fixture 提取出来的规格，必须与 report_layout.json **逐键一致**。

    基准就是真实报告裁剪版，因此不允许任何"有意偏离"——提取器读到的值 = 引擎用的值。
    """
    candidate = extract(config.GOLDEN_SAMPLE)
    diffs = compare(wr.SPEC, candidate)
    assert diffs == [], (
        "提取结果与 report_layout.json 不一致：\n"
        + "\n".join("  %s 当前=%r 提取=%r" % item for item in diffs)
    )


def test_extracted_widths_match_the_sample():
    """基准即真实报告：提取器读到的列宽与生效列宽逐列相同，不存在宽度偏离。"""
    candidate = extract(config.GOLDEN_SAMPLE)
    assert candidate["columns"]["widths"] == list(wr.GRID_COLS)
    assert wr.SPEC["columns"]["_widthOverrides"] == {}


def test_extractor_handles_both_detection_tables():
    """立柱表与横梁表的版式规格相同，只有列宽有 ≤4 twips 的 Word 重算偏差。"""
    column = extract(config.GOLDEN_SAMPLE, table_ordinal=1)
    beam = extract(config.GOLDEN_SAMPLE, table_ordinal=2)

    assert column["headers"]["fixed"] == beam["headers"]["fixed"]
    assert column["headers"]["thicknessSub"] == beam["headers"]["thicknessSub"]
    assert column["spans"] == beam["spans"]
    assert column["table"]["border"] == beam["table"]["border"]
    assert column["cell"]["headerLineSpacing"] == beam["cell"]["headerLineSpacing"]
    assert column["rows"]["dataHeightByTemplate"] == beam["rows"]["dataHeightByTemplate"]

    deviations = [abs(a - b) for a, b in zip(column["columns"]["widths"], beam["columns"]["widths"])]
    assert max(deviations) <= 4                              # 0.2mm，Word 自动重算

    # 两张表的「截面尺寸要求」表头文案不同（立柱 / 横梁），因此数据行高也不同
    assert column["_extraHeaderColumns"] != beam["_extraHeaderColumns"]
    assert column["rows"]["dataHeightTwips"] == 522          # 立柱
    assert beam["rows"]["dataHeightTwips"] == 567            # 横梁


def test_extractor_detects_structure_generically():
    """结构靠 gridSpan / vMerge 泛化识别，而不是写死 11 列。"""
    spec = extract(config.GOLDEN_SAMPLE)
    assert spec["spans"]["thickness"] == 7
    assert spec["columns"]["index"]["face"] == 3
    assert spec["columns"]["index"]["readingCount"] == 5
    assert spec["columns"]["index"]["requirement"] == 10
    assert spec["headers"]["fixed"] == ["楼层", "检测构件\n位置", "尺寸检测结果m×n\n（mm×mm）"]
    assert spec["headers"]["thickness"] == "厚度检测结果（mm）"
    assert spec["headers"]["thicknessSub"] == ["检测面", "1", "2", "3", "4", "5", "最小值"]
    assert spec["columns"]["mergedInBody"] == ["floor", "position", "size", "requirement"]
    assert len(spec["columns"]["widths"]) == 11


def test_extractor_warns_when_structure_cannot_be_confirmed(tmp_path):
    """检测表完全没有纵向合并 → 检不出要合并哪几列，必须给出提示而不是静默留空。

    基准 fixture 里有多面构件（能检出 vMerge），所以这里现造一份只有表头的检测表。
    """
    from webapp.services import word_report as wr

    doc = wr.new_document()
    wr.add_title(doc, "幕墙立柱截面尺寸检测结果")
    wr.build_detection_table(doc, {"template_type": "column", "records": []})
    path = tmp_path / "no_data_rows.docx"
    wr.save(doc, path)

    spec = extract(path)
    warnings = " ".join(spec["_warnings"])
    assert "vMerge" in warnings
    # 检不出时沿用当前规格值，而不是写成空列表
    assert spec["columns"]["mergedInBody"] == list(wr.MERGED_IN_BODY)
