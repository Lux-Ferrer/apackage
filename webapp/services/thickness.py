# -*- coding: utf-8 -*-
"""厚度读数计算：每面 5 个读数 -> 最小值。

已确认范围：截面尺寸检测，5 个厚度值自动计算最小值。
最小值是派生值，不落库；导出/展示统一走这里，保证单一数据来源。
"""

from __future__ import annotations

import math

# 现场未测的点，表单/导入可能出现的空占位符
_EMPTY_TOKENS = {"", "-", "/", "—", "－", "null", "none"}

VALUE_DIGITS = 2  # 导出保留两位小数


def normalize_value(raw):
    """把原始读数转成 float 或 None（未填）。无法识别时抛 ValueError。"""
    if raw is None:
        return None
    if isinstance(raw, bool):                      # bool 是 int 子类，先挡掉
        raise ValueError("厚度读数无法识别：%r" % (raw,))
    if isinstance(raw, (int, float)):
        value = float(raw)
        return None if math.isnan(value) else value
    text = str(raw).strip()
    if text.lower() in _EMPTY_TOKENS:
        return None
    try:
        return float(text)
    except ValueError:
        raise ValueError("厚度读数无法识别：%r" % (raw,))


def face_min(values):
    """一个检测面 5 个读数的最小值；全部未填时返回 None。"""
    numbers = [v for v in (normalize_value(raw) for raw in values) if v is not None]
    return min(numbers) if numbers else None


def format_mm(value, digits: int = VALUE_DIGITS) -> str:
    """数值 -> 定点小数字符串（默认两位）；None -> 空串。"""
    if value is None:
        return ""
    return f"{float(value):.{digits}f}"


def face_min_text(values, digits: int = VALUE_DIGITS) -> str:
    """一个检测面的最小值文本，直接用于表格"最小"列。"""
    return format_mm(face_min(values), digits)


def readings_of_row(row) -> list:
    """从 thickness_readings 行取出 value_1..value_5。"""
    return [row["value_%d" % i] for i in range(1, 6)]
