# -*- coding: utf-8 -*-
"""案例数据工具（tools/case_data.py）与导出物对拍时的"期望行"构造。

这里锁的是**合并语义**：`expected_rows` 造出来的期望网格必须与 Word 表格的数据行
一一对应，否则 verify_case_data.py 会因为"引擎按连续相同条文合并、而期望按构件去重"
而误报失败（这个 bug 真实发生过一次）。
"""

from __future__ import annotations

import pytest

pytest.importorskip("openpyxl", reason="案例工具依赖开发依赖 openpyxl")

from tools.case_data import expected_rows, group_by_member   # noqa: E402


CLAUSE_A = "立柱铝型材开口部位的厚度不应小于3.0mm"
CLAUSE_B = "立柱铝型材闭口部位的厚度不应小于2.5mm"


def _case(clause, size="63×164"):
    return {
        "size": size,
        "readings": [2.99, 3.01, 3.00, 2.98, 3.02],
        "expected_min": "2.98",
        "requirement": clause,
    }


def _fixture(requirements):
    """requirements: [(楼层, 构件位置, [面…], 条文)] → (cases, order)。"""
    cases, order = {}, []
    for floor, position, faces, clause in requirements:
        for face in faces:
            key = (floor, position, face)
            cases[key] = _case(clause)
            order.append(key)
    return cases, order


def test_first_face_of_a_member_carries_the_member_columns():
    """多面构件：只有首个面带 楼层/构件位置/尺寸结果（对应纵向合并 continue 格）。"""
    cases, order = _fixture([("六层", "1", ["B", "H"], CLAUSE_A)])
    rows = expected_rows(cases, order)

    assert len(rows) == 2
    assert rows[0][:4] == ["六层", "1", "63×164", "B"]
    assert rows[1][:4] == ["", "", "", "H"]


def test_clause_is_merged_across_members_with_the_same_text():
    """同一条文横跨多个构件 → 只有第一行的条文列带文本，后面几行是空的。"""
    cases, order = _fixture([
        ("六层", "1", ["B", "H"], CLAUSE_A),
        ("六层", "2", ["B", "H"], CLAUSE_A),
    ])
    rows = expected_rows(cases, order)

    assert [row[10] for row in rows] == [CLAUSE_A, "", "", ""]


def test_clause_starts_a_new_block_when_the_text_changes():
    """条文变了就新起一块 → 该行重新带上文本（与引擎的 restart 规则一致）。"""
    cases, order = _fixture([
        ("六层", "1", ["B"], CLAUSE_A),
        ("六层", "2", ["B"], CLAUSE_B),
    ])
    rows = expected_rows(cases, order)

    assert [row[10] for row in rows] == [CLAUSE_A, CLAUSE_B]


def test_empty_requirement_does_not_swallow_the_next_row():
    """条文为空（显示「无」）的行也要有自己的块，不能把下一行并进去。"""
    cases, order = _fixture([
        ("六层", "1", ["B"], ""),
        ("六层", "2", ["B"], CLAUSE_A),
    ])
    rows = expected_rows(cases, order)

    assert [row[10] for row in rows] == ["", CLAUSE_A]


def test_group_by_member_keeps_face_order():
    cases, order = _fixture([
        ("六层", "1", ["B", "H"], CLAUSE_A),
        ("七层", "2", ["T"], CLAUSE_A),
    ])
    grouped = group_by_member(cases, order)

    assert list(grouped) == [("六层", "1"), ("七层", "2")]
    assert grouped[("六层", "1")] == [("六层", "1", "B"), ("六层", "1", "H")]
