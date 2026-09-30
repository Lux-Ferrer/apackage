# -*- coding: utf-8 -*-
"""厚度最小值计算测试（已确认范围：5 个厚度值自动计算最小值）。"""

from __future__ import annotations

import pytest

from webapp.services import thickness


def test_min_of_five():
    assert thickness.face_min([2.14, 2.12, 2.11, 2.10, 2.10]) == pytest.approx(2.10)


def test_matches_case_spreadsheet_rows():
    """与 docs/samples/检测结果案例.xlsx 的真实行一致。"""
    # 横梁：六层 6°
    assert thickness.face_min_text([2.14, 2.12, 2.11, 2.10, 2.10]) == "2.10"
    # 横梁：六层 7°
    assert thickness.face_min_text([2.15, 2.12, 2.18, 2.19, 2.15]) == "2.12"
    # 立柱：六层 1 号 B 面
    assert thickness.face_min_text([2.99, 3.02, 3.01, 3.01, 2.99]) == "2.99"
    # 立柱：六层 1 号 H 面
    assert thickness.face_min_text([2.55, 2.52, 2.52, 2.53, 2.53]) == "2.52"


def test_accepts_strings_from_forms():
    assert thickness.face_min_text(["2.99", "3.02", "3.01", "3.01", "2.99"]) == "2.99"
    assert thickness.face_min(["2.5", " 2.4 "]) == pytest.approx(2.4)


def test_blank_readings_are_ignored():
    assert thickness.face_min([2.5, None, "", "-", "/"]) == pytest.approx(2.5)
    assert thickness.face_min_text([None, 3.0, ""]) == "3.00"


def test_all_blank_returns_none():
    assert thickness.face_min([None, "", "-"]) is None
    assert thickness.face_min([]) is None
    assert thickness.face_min_text([None]) == ""


def test_two_decimal_formatting():
    assert thickness.format_mm(2.1) == "2.10"
    assert thickness.format_mm(-0.01) == "-0.01"
    assert thickness.format_mm(3) == "3.00"
    assert thickness.format_mm(None) == ""


def test_negative_value_from_sample_is_supported():
    """样例里有 -0.01 这类测试值，不能因符号被误判。"""
    assert thickness.face_min_text([2.00, 2.00, 2.00, 2.00, -0.01]) == "-0.01"


def test_unparseable_value_raises():
    with pytest.raises(ValueError):
        thickness.face_min(["abc"])
    with pytest.raises(ValueError):
        thickness.normalize_value(True)


# --------------------------------------------------------------------------
# 表单回填用的容错版（UI 改造新增）
#
# 契约被拆成两个函数，因为两种场景对"非法值"的态度相反：
#   - 校验流程（normalize_value / face_min）必须**严格**：非法就是错误；
#   - 表单回填（face_min_text_of_valid）必须**容错**：用户可能留着非法文本，
#     此时要显示"其余有效值的最小值"并让警告灯指出是哪几格，而不是 500。
# --------------------------------------------------------------------------
def test_reading_state_classifies_three_ways():
    assert thickness.reading_state("") == "empty"
    assert thickness.reading_state("  ") == "empty"
    assert thickness.reading_state(None) == "empty"
    assert thickness.reading_state("-") == "empty"
    assert thickness.reading_state("2.99") == "valid"
    assert thickness.reading_state(2.99) == "valid"
    assert thickness.reading_state("abc") == "invalid"


def test_count_readings_separates_valid_from_invalid():
    assert thickness.count_readings(["2.1", "", "abc", "2.3", None]) == (2, 1)
    assert thickness.count_readings(["abc", "def", "", "", ""]) == (0, 2)
    assert thickness.count_readings(["", "", "", "", ""]) == (0, 0)


def test_face_min_text_of_valid_skips_invalid_instead_of_raising():
    assert thickness.face_min_text_of_valid(["abc", "2.50", "", "3.00"]) == "2.50"
    assert thickness.face_min_text_of_valid(["abc", "def"]) == ""      # 全非法 → 空（模板显示 —）
    assert thickness.face_min_text_of_valid(["2.99", "3.02"]) == "2.99"

    # 与严格版的对照：同样的输入，严格版会抛异常
    with pytest.raises(ValueError):
        thickness.face_min(["abc", "2.50"])


def test_readings_of_row():
    row = {"value_1": 2.14, "value_2": 2.12, "value_3": 2.11,
           "value_4": 2.10, "value_5": 2.10}
    assert thickness.readings_of_row(row) == [2.14, 2.12, 2.11, 2.10, 2.10]
    assert thickness.face_min_text(thickness.readings_of_row(row)) == "2.10"
