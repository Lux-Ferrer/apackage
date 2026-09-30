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


def face_min_text_of_valid(values, digits: int = VALUE_DIGITS) -> str:
    """容错版最小值文本：**跳过**非法文本，只按有效读数算。

    专门给表单回填用：用户可能在某些格子里留下非数字文本，那时应当显示
    "其余有效值的最小值"并由警告灯提示是哪几格，而不是抛异常把页面打成 500。
    校验流程仍旧走 :func:`normalize_value`（严格，非法即报错）。
    """
    numbers = []
    for raw in values:
        try:
            value = normalize_value(raw)
        except ValueError:
            continue
        if value is not None:
            numbers.append(value)
    return format_mm(min(numbers) if numbers else None, digits)


def readings_of_row(row) -> list:
    """从 thickness_readings 行取出 value_1..value_5。"""
    return [row["value_%d" % i] for i in range(1, 6)]


# --------------------------------------------------------------------------
# 读数状态（供表单视图模型使用）
#
# 与 :func:`normalize_value` 的分工：那个用异常表达"非法"，适合校验流程；
# 这里的调用方需要"有多少格填了、有多少格是错的"这类**计数**，
# 用异常控制流会写出很别扭的循环，所以单独提供不抛异常的版本。
# --------------------------------------------------------------------------
def reading_state(raw) -> str:
    """一个读数的状态：``'empty'``（未填）/ ``'valid'`` / ``'invalid'``（非空非数字）。"""
    try:
        return "empty" if normalize_value(raw) is None else "valid"
    except ValueError:
        return "invalid"


def count_readings(values) -> tuple:
    """返回 ``(有效个数, 非法个数)``；空值不计入任何一边。

    UI 设计里这两个数分别驱动两个**独立**的视觉通道：
    有效个数 → 三态着色（还剩多少活）；非法个数 → 警告灯（能不能保存）。
    合并成一个数会让"5 格全填了 abc"看起来像填完了。
    """
    states = [reading_state(raw) for raw in values]
    return states.count("valid"), states.count("invalid")
