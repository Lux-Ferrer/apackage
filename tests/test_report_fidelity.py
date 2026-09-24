# -*- coding: utf-8 -*-
"""M2 主闸门：生成的报告与客户样例逐属性一致。

方式是从样例回灌它**自己的数据**后重新生成，因此"内容不同所以结构可以不同"
这个借口不成立——结构、样式、合并、正文序列都必须全等。
"""

from __future__ import annotations

import pytest

from tools.compare_report_with_sample import (build_from_sample, diff,
                                              document_fingerprint, render_grid,
                                              run_comparison)
from webapp import config


def test_generated_report_matches_sample():
    result = run_comparison()
    message = "\n".join(
        "  %-46s 期望=%r 实际=%r" % (path, expected, actual)
        for path, expected, actual in result["diffs"][:20]
    )
    assert result["diffs"] == [], "与样例存在 %d 处差异：\n%s" % (len(result["diffs"]), message)


def test_comparison_covers_both_tables():
    result = run_comparison()
    assert result["compared_tables"] == 2          # 立柱 + 横梁
    assert len(result["actual_grids"]) == 2        # 玻璃表不出现在生成物里


def test_merge_grid_identical():
    """合并结构单独断言一次，失败时直接打印两侧网格便于定位。"""
    result = run_comparison()
    for index, (expected, actual) in enumerate(zip(result["expected_grids"], result["actual_grids"])):
        assert expected == actual, (
            "table[%d] 合并网格不一致\n样例：\n%s\n生成：\n%s"
            % (index, render_grid(expected), render_grid(actual))
        )


def test_grid_shape_is_eleven_columns():
    result = run_comparison()
    for grid in result["actual_grids"]:
        for row in grid:
            assert len(row) == 11


def test_generated_report_matches_frozen_baseline(tmp_path):
    """回归基线：M2 验收后冻结的生成物，捕捉后续改动（M3 附页等）的意外偏差。

    注意比对的是**指纹**而不是字节：docx 是 zip，条目时间戳会让字节比较失效。
    基线重新冻结：python tools/compare_report_with_sample.py --bless
    """
    assert config.GENERATED_BASELINE.exists(), (
        "缺少回归基线，请运行：python tools/compare_report_with_sample.py --bless"
    )
    generated = build_from_sample(tmp_path / "generated.docx")
    diffs = diff(document_fingerprint(config.GENERATED_BASELINE),
                 document_fingerprint(generated), "doc")
    assert diffs == [], "生成物与冻结基线存在 %d 处差异：\n%s" % (
        len(diffs),
        "\n".join("  %s 期望=%r 实际=%r" % item for item in diffs[:20]),
    )
