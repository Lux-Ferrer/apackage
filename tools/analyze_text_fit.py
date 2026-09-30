# -*- coding: utf-8 -*-
"""排版度量：用真实字体预测"客户模板列宽能否装下真实数据"。

为什么需要它
------------
现基准（`tests/fixtures/检测表_真实裁剪.docx`，实测自真实报告）的列宽是按客户自己的
演示数据调的。拿真实案例数据（`63×164`、`二十三层`、长条文）去套，某些列会折行。
本工具把这件事**量化**，用于与客户/导师讨论列宽是否需要调整。

度量方式
--------
按文档的字体设置分段度量后相加：西文用 Times New Roman、中文用主题字体（等线），
字号取 `report_layout.json` 的值（表格正文继承 10pt、要求列继承），
再与"列宽 − 左右边距"比较，得出需要几行。

用法::

    python tools/analyze_text_fit.py                      # 控制台报告
    python tools/analyze_text_fit.py --report fit.md      # 生成 markdown 证据
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webapp import config                                       # noqa: E402
from webapp.services import word_report as wr                   # noqa: E402

# 字体文件候选（用于度量，找不到时退化为字符宽度估算）
LATIN_FONTS = (r"C:\Windows\Fonts\times.ttf", "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf")
CJK_FONTS = (r"C:\Windows\Fonts\Deng.ttf", r"C:\Windows\Fonts\simsun.ttc",
             "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")

MEASURE_PX = 1000          # 以 1000px 度量再按比例换算，避免小字号的取整误差

# 各列的测量配置：(列下标, 名称, 字号来源)
COLUMN_SPECS = (
    (wr.COLUMN_INDEX["floor"], "楼层", "inherited"),
    (wr.COLUMN_INDEX["position"], "构件位置", "inherited"),
    (wr.COLUMN_INDEX["size"], "尺寸结果", "inherited"),
    (wr.COLUMN_INDEX["face"], "检测面", "inherited"),
    (wr.COLUMN_INDEX["readingFirst"], "读数 1（1~5 同宽）", "inherited"),
    (wr.COLUMN_INDEX["minimum"], "最小值", "inherited"),
    (wr.COLUMN_INDEX["requirement"], "截面尺寸要求", "requirement"),
)


def cell_margin_twips() -> int:
    """单元格左右内边距：优先用单元格级 tcMar，否则用表级 tblCellMar。

    真实报告的表级内边距是左右各 57 twips，单元格上不再单独设置。
    """
    if wr.CELL_MARGIN_HORIZONTAL:
        return int(wr.CELL_MARGIN_HORIZONTAL)
    return int(wr.SPEC["table"]["tableCellMargin"]["left"])


def column_pt(size_kind: str) -> float:
    """该列字号：要求列若显式设了字号就用它，否则用表格正文的继承字号。"""
    if size_kind == "requirement" and wr.REQUIREMENT_PT:
        return float(wr.REQUIREMENT_PT)
    return float(wr.INHERITED_TABLE_PT)


# --------------------------------------------------------------------------
# 字体与度量
# --------------------------------------------------------------------------
def _load_fonts():
    from PIL import ImageFont

    def first_existing(paths):
        for path in paths:
            if Path(path).exists():
                return ImageFont.truetype(path, MEASURE_PX)
        return None

    latin = first_existing(LATIN_FONTS)
    cjk = first_existing(CJK_FONTS)
    if latin is None or cjk is None:
        print("提示：未找到字体文件，退化为按字符宽度估算（中文 1.0em、西文 0.5em）\n")
    return latin, cjk


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (0x3000 <= code <= 0x303F or 0x4E00 <= code <= 0x9FFF
            or 0xFF00 <= code <= 0xFFEF or 0x3400 <= code <= 0x4DBF)


def make_measurer():
    """返回 ``measure(text, pt) -> twips``。"""
    latin, cjk = _load_fonts()

    def measure(text: str, pt: float) -> float:
        if not text:
            return 0.0
        if latin is None or cjk is None:
            return sum((1.0 if _is_cjk(ch) else 0.5) for ch in text) * pt * 20

        total = 0.0
        run, run_is_cjk = "", None
        for char in text + "\0":                       # 尾哨兵，收尾最后一段
            is_cjk = _is_cjk(char) if char != "\0" else None
            if run and is_cjk != run_is_cjk:
                font = cjk if run_is_cjk else latin
                total += font.getlength(run)
                run = ""
            if char != "\0":
                run += char
                run_is_cjk = is_cjk
        return total * pt / MEASURE_PX * 20            # px@1000 -> pt -> twips

    return measure


# --------------------------------------------------------------------------
# 样本数据
# --------------------------------------------------------------------------
def load_samples() -> dict:
    """从案例数据里取各列的真实文本样本；案例不可用时只用表头与预置条文。"""
    samples = {name: [] for _, name, _ in COLUMN_SPECS}
    try:
        from case_data import BEAM_SHEET, COLUMN_SHEET, read_case
    except SystemExit as error:                        # 缺 openpyxl
        print("提示：%s\n（跳过真实数据样本，仅分析表头与预置条文）\n" % error)
        return samples

    for sheet in (COLUMN_SHEET, BEAM_SHEET):
        cases, _order = read_case(sheet)
        for (floor, position, face), case in cases.items():
            samples["楼层"].append(floor)
            samples["构件位置"].append(position)
            samples["尺寸结果"].append(case["size"])
            samples["检测面"].append(face)
            samples["读数 1（1~5 同宽）"] += ["%.2f" % float(v) for v in case["readings"]]
            samples["最小值"].append(case["expected_min"])
            if case["requirement"]:
                samples["截面尺寸要求"].append(str(case["requirement"]))
    return samples


def header_samples() -> dict:
    """表头文字（含模板里的空格写法）。"""
    fixed = wr.HEADER_FIXED
    return {
        "楼层": [fixed[0]],
        "构件位置": [fixed[1]],
        "尺寸结果": [fixed[2]],
        "检测面": [wr.HEADER_THICKNESS_SUB[0]],
        "读数 1（1~5 同宽）": list(wr.HEADER_THICKNESS_SUB[1:6]),
        "最小值": [wr.HEADER_THICKNESS_SUB[6]],
        "截面尺寸要求": [config.REQUIREMENT_LABELS[config.TEMPLATE_COLUMN]],
    }


# --------------------------------------------------------------------------
# 分析
# --------------------------------------------------------------------------
def lines_needed(text: str, measure, pt: float, usable: int) -> int:
    """一个单元格需要几行。

    文本里的 ``\\n`` 是真实表格中的**多个段落**（如「检测构件」/「位置」），
    段落之间不共享行，所以逐段度量再求和。
    """
    total = 0
    for paragraph in str(text).split("\n"):
        total += max(1, math.ceil(measure(paragraph, pt) / usable))
    return max(1, total)


def analyze(measure) -> list:
    table_samples = load_samples()
    headers = header_samples()

    # 预置条文也可能比案例里的更长，一并纳入
    for template_type in config.TEMPLATE_TYPES:
        table_samples["截面尺寸要求"] += list(config.REQUIREMENT_OPTIONS[template_type])

    rows = []
    margin = cell_margin_twips()
    for index, name, size_kind in COLUMN_SPECS:
        width = wr.GRID_COLS[index]
        pt = column_pt(size_kind)
        usable = width - margin * 2

        header = max(headers.get(name, [""]), key=lambda t: measure(t, pt), default="")
        header_width = max((measure(line, pt) for line in str(header).split("\n")), default=0)
        header_lines = lines_needed(header, measure, pt, usable)

        data = table_samples.get(name) or [""]
        longest = max(data, key=lambda t: measure(t, pt))
        data_width = max((measure(line, pt) for line in str(longest).split("\n")), default=0)
        data_lines = lines_needed(longest, measure, pt, usable)

        rows.append({
            "column": index,
            "name": name,
            "width": width,
            "pt": pt,
            "usable": usable,
            "header": header, "header_width": header_width, "header_lines": header_lines,
            "longest": longest, "data_width": data_width, "data_lines": data_lines,
        })
    return rows


def render_console(rows) -> None:
    print("列宽适配分析（twips；1 pt = 20 twips）")
    print("=" * 108)
    print("%-22s %6s %6s %5s  %-24s %6s %4s  %-24s %6s %4s" % (
        "列", "列宽", "可用", "字号", "最长表头", "需要", "行", "最长数据", "需要", "行"))
    print("-" * 108)
    for row in rows:
        print("%-22s %6d %6d %4gpt  %-24s %6.0f %3d%s  %-24s %6.0f %3d%s" % (
            row["name"], row["width"], row["usable"], row["pt"],
            _clip(row["header"]), row["header_width"], row["header_lines"],
            "!" if row["header_lines"] > 1 else " ",
            _clip(row["longest"]), row["data_width"], row["data_lines"],
            "!" if row["data_lines"] > 1 else " ",
        ))
    print("-" * 108)
    wrapped = [row for row in rows if row["data_lines"] > 1 or row["header_lines"] > 1]
    if wrapped:
        print("会折行的列：")
        for row in wrapped:
            detail = []
            if row["header_lines"] > 1:
                detail.append("表头 %d 行" % row["header_lines"])
            if row["data_lines"] > 1:
                detail.append("数据最多 %d 行" % row["data_lines"])
            print("  - %s：%s（列宽 %d / 可用 %d）" % (row["name"], "、".join(detail),
                                                      row["width"], row["usable"]))
        print()
        print("说明：行高是「至少」语义，折行只会让行变高，不会截断内容；")
        print("      但表头/数据行会比客户模板的演示数据高，属于客户列宽与真实数据不匹配，")
        print("      不是导出实现的问题（我们照抄版式，不擅自改列宽）。")
    else:
        print("所有列都能单行容纳表头与真实数据。")


def render_markdown(rows) -> str:
    lines = [
        "# 列宽适配分析",
        "",
        "用真实字体（Times New Roman / 等线）按文档字号度量，与「列宽 − 左右边距」比较。",
        "",
        "| 列 | 列宽 | 可用 | 字号 | 最长表头 | 需要 | 行数 | 最长数据 | 需要 | 行数 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append("| %s | %d | %d | %gpt | %s | %.0f | %d | %s | %.0f | %d |" % (
            row["name"], row["width"], row["usable"], row["pt"],
            _escape(row["header"]), row["header_width"], row["header_lines"],
            _escape(row["longest"]), row["data_width"], row["data_lines"]))
    lines += [
        "",
        "## 结论",
        "",
    ]
    wrapped = [row for row in rows if row["data_lines"] > 1 or row["header_lines"] > 1]
    if wrapped:
        lines.append("以下列无法单行容纳，会折行（行高是「至少」语义，只会变高、不会截断）：")
        lines.append("")
        for row in wrapped:
            lines.append("- **%s**：列宽 %d / 可用 %d；表头 %d 行、数据最多 %d 行"
                         % (row["name"], row["width"], row["usable"],
                            row["header_lines"], row["data_lines"]))
        lines += [
            "",
            "根因：列宽是从**客户模板**照抄来的，客户是按它自己的演示数据（楼层 `1`、"
            "尺寸结果 `1`、读数 `1.00`）调的，换成真实数据（`二十三层`、`63×164`、长条文）"
            "后必然折行。",
            "这是**客户模板本身的适配问题**，不是导出实现的问题 —— 我们照抄版式，"
            "不擅自改列宽。",
        ]
    else:
        lines.append("所有列都能单行容纳。")
    return "\n".join(lines) + "\n"


def _clip(text: str, limit: int = 22) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _escape(text: str) -> str:
    return text.replace("|", "\\|")


def main() -> int:
    parser = argparse.ArgumentParser(description="用真实字体分析客户模板列宽的适配情况")
    parser.add_argument("--report", help="把结果写成 markdown 证据文件")
    args = parser.parse_args()

    measure = make_measurer()
    rows = analyze(measure)
    render_console(rows)

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(render_markdown(rows), encoding="utf-8")
        print("\n报告已写入 %s" % args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
