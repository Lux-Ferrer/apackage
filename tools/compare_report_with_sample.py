# -*- coding: utf-8 -*-
"""Word 报告与客户样例的逐单元格对拍。

主闸门（回灌模式）
------------------
从样例里读出它**自己的数据**（楼层/构件位置/尺寸结果/检测面/读数/条文），
用我们的导出引擎重新生成一份，再与样例**逐属性**比较。
因为数据完全相同，"内容不同所以结构可以不同"这个借口不成立 —— 结构必须全等。

比对的属性
----------
文档：``sectPr`` 的 pgSz / pgMar / cols / docGrid
正文：子元素顺序与类型、段落文本 / jc / spacing、run 的加粗与字号
表格：tblW / jc / tblLayout / tblBorders(6 边) / tblCellMar / tblLook / tblGrid 列宽
行  ：trHeight(val,hRule) / trPr jc
单元格：``w:tc`` 个数与顺序、tcW / gridSpan / vMerge / tcMar / vAlign、段落格式
合并结构：逻辑网格（``^`` = 纵向被合并，``<`` = 横向被合并）

明确忽略（每条都有理由，见 README / M2 设计文档）
--------------------------------------------------
- ``w:rsid*`` / ``w14:paraId`` / ``w14:textId`` / ``w:proofErr``：Word 编辑痕迹
- XML 声明与属性顺序：python-docx 重写为单引号 + LF（实测 styles.xml 仅此差异）
- **run 的切分方式**：样例把长条文按中英文字界拆成多个 run，我们写一个 run；
  渲染完全相同，所以文本按段落拼接后比较，run 只比"属性集合"
- 样例的玻璃/膜厚章节：范围外，基准 fixture 已裁掉；另反向断言生成物不含这些内容

用法::

    python tools/compare_report_with_sample.py                 # 控制台摘要
    python tools/compare_report_with_sample.py --verbose       # 列出全部差异
    python tools/compare_report_with_sample.py --report out.md # 生成 markdown 报告
"""

from __future__ import annotations

import argparse
import copy
import io
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lxml import etree                                          # noqa: E402

from webapp import config                                       # noqa: E402
from webapp.services import word_report as wr                   # noqa: E402

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_SHOWN_DIFFS = 20


# --------------------------------------------------------------------------
# 取文本 / 属性
# --------------------------------------------------------------------------
def text_of(element) -> str:
    return "".join(node.text or "" for node in element.iter(W + "t"))


def attr_map(element) -> dict:
    if element is None:
        return {}
    return {etree.QName(key).localname: value for key, value in element.attrib.items()}


def val_of(element, name="val"):
    if element is None:
        return None
    return element.get(W + name)


def run_props(paragraph) -> list:
    """run 的属性集合（去重排序）——比较时忽略 run 的切分方式。"""
    props = set()
    for run in paragraph.findall(W + "r"):
        rpr = run.find(W + "rPr")
        if rpr is None:
            props.add((False, None, None))
            continue
        fonts = rpr.find(W + "rFonts")
        props.add((
            rpr.find(W + "b") is not None,
            val_of(rpr.find(W + "sz")),
            None if fonts is None else fonts.get(W + "eastAsia"),
        ))
    return sorted(props, key=repr)


def paragraph_fingerprint(paragraph) -> dict:
    ppr = paragraph.find(W + "pPr")
    jc = ppr.find(W + "jc") if ppr is not None else None
    spacing = ppr.find(W + "spacing") if ppr is not None else None
    return {
        "text": text_of(paragraph),
        "jc": val_of(jc),
        "spacing": attr_map(spacing),
        "run_props": run_props(paragraph),
    }


def cell_fingerprint(tc) -> dict:
    tcpr = tc.find(W + "tcPr")
    tcmar = tcpr.find(W + "tcMar") if tcpr is not None else None
    return {
        "tcW": attr_map(tcpr.find(W + "tcW")) if tcpr is not None else {},
        "gridSpan": val_of(tcpr.find(W + "gridSpan")) if tcpr is not None else None,
        "vMerge": (val_of(tcpr.find(W + "vMerge")) or "continue")
        if (tcpr is not None and tcpr.find(W + "vMerge") is not None) else None,
        "tcMar": {etree.QName(e).localname: e.get(W + "w") for e in tcmar} if tcmar is not None else None,
        "vAlign": val_of(tcpr.find(W + "vAlign")) if tcpr is not None else None,
        "paragraphs": [paragraph_fingerprint(p) for p in tc.findall(W + "p")],
    }


def row_fingerprint(tr) -> dict:
    trpr = tr.find(W + "trPr")
    height = trpr.find(W + "trHeight") if trpr is not None else None
    return {
        "trHeight": (height.get(W + "val"), height.get(W + "hRule")) if height is not None else None,
        "jc": val_of(trpr.find(W + "jc")) if trpr is not None else None,
        "cells": [cell_fingerprint(tc) for tc in tr.findall(W + "tc")],
    }


def table_fingerprint(tbl) -> dict:
    tblpr = tbl.find(W + "tblPr")
    borders = tblpr.find(W + "tblBorders")
    cellmar = tblpr.find(W + "tblCellMar")
    return {
        "tblW": attr_map(tblpr.find(W + "tblW")),
        "jc": val_of(tblpr.find(W + "jc")),
        "tblLayout": attr_map(tblpr.find(W + "tblLayout")),
        "tblBorders": {etree.QName(e).localname: attr_map(e) for e in borders} if borders is not None else None,
        "tblCellMar": {etree.QName(e).localname: attr_map(e) for e in cellmar} if cellmar is not None else None,
        "tblLook": attr_map(tblpr.find(W + "tblLook")),
        "grid": [int(g.get(W + "w")) for g in tbl.find(W + "tblGrid").findall(W + "gridCol")],
        "rows": [row_fingerprint(tr) for tr in tbl.findall(W + "tr")],
    }


def section_fingerprint(sectpr) -> dict:
    return {
        "pgSz": attr_map(sectpr.find(W + "pgSz")),
        "pgMar": attr_map(sectpr.find(W + "pgMar")),
        "cols": attr_map(sectpr.find(W + "cols")),
        "docGrid": attr_map(sectpr.find(W + "docGrid")),
    }


# --------------------------------------------------------------------------
# 逻辑网格（合并结构）
# --------------------------------------------------------------------------
def layout_grid(tbl) -> list:
    """把表格展开成逻辑网格：``^`` 纵向被合并、``<`` 横向被合并、``·`` 空文本格。"""
    columns = len(tbl.find(W + "tblGrid").findall(W + "gridCol"))
    grid = []
    for tr in tbl.findall(W + "tr"):
        row = ["?"] * columns
        column = 0
        for tc in tr.findall(W + "tc"):
            tcpr = tc.find(W + "tcPr")
            span = int(val_of(tcpr.find(W + "gridSpan")) or 1) if tcpr is not None else 1
            vmerge = tcpr.find(W + "vMerge") if tcpr is not None else None
            if vmerge is not None and val_of(vmerge) is None:
                marker = "^"
            else:
                text = text_of(tc)
                marker = text if text else "·"
            row[column] = marker
            for offset in range(1, span):
                row[column + offset] = "<"
            column += span
        grid.append(row)
    return grid


def render_grid(grid) -> str:
    lines = []
    for index, row in enumerate(grid):
        lines.append("r%-2d | %s" % (index, " | ".join("%-8s" % (cell or "")[:8] for cell in row)))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 指纹与比较
# --------------------------------------------------------------------------
def document_fingerprint(path) -> dict:
    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    body = root.find(W + "body")
    children = []
    tables = []
    for child in body:
        tag = etree.QName(child).localname
        if tag == "p":
            children.append({"type": "p", **paragraph_fingerprint(child)})
        elif tag == "tbl":
            children.append({"type": "tbl", "index": len(tables)})
            tables.append(table_fingerprint(child))
        elif tag == "sectPr":
            children.append({"type": "sectPr", **section_fingerprint(child)})
    return {"children": children, "tables": tables}


def diff(expected, actual, path="", found=None):
    """递归比较两个指纹，产出 ``(路径, 期望, 实际)``。"""
    if found is None:
        found = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            diff(expected.get(key), actual.get(key), "%s.%s" % (path, key), found)
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            found.append(("%s.length" % path, len(expected), len(actual)))
        for index in range(min(len(expected), len(actual))):
            diff(expected[index], actual[index], "%s[%d]" % (path, index), found)
    elif expected != actual:
        found.append((path, expected, actual))
    return found


def drop_out_of_scope(children) -> list:
    """从样例正文里剔除玻璃章节（标题 + 表格 + 其后的空段）。

    玻璃模块明确不在范围内；比较时按"标题文本包含玻璃 → 连带它后面的表格与空段"剔除。
    """
    kept = []
    index = 0
    while index < len(children):
        child = children[index]
        if child["type"] == "p" and "玻璃" in (child.get("text") or ""):
            index += 1
            while index < len(children) and children[index]["type"] == "tbl":
                index += 1
            if index < len(children) and children[index]["type"] == "p" and not children[index].get("text"):
                index += 1
            continue
        kept.append(child)
        index += 1
    return kept


# --------------------------------------------------------------------------
# 从样例抽出它自己的数据（回灌用）
# --------------------------------------------------------------------------
def sample_root(path):
    with zipfile.ZipFile(path) as archive:
        return etree.fromstring(archive.read("word/document.xml"))


def extract_project(root) -> dict:
    project = {}
    labels = {label: key for key, label in config.PROJECT_INFO_FIELDS}
    for paragraph in root.find(W + "body").findall(W + "p"):
        text = text_of(paragraph)
        label, _, value = text.partition("：")
        if label in labels:
            project[labels[label]] = value
    return project


def extract_groups(root) -> list:
    """把基准两张表的数据读成我们内部的分组结构（一个构件 = 一条记录 + 多个面）。

    ⚠️ 必须对**纵向合并的四列**向下填充：同一构件的第 2 个检测面所在行，
    楼层/检测构件位置/尺寸检测结果/截面尺寸要求 四格是空的（被合并覆盖）。
    不填充就会把它们当成"另一个空构件"，合成数据后每个构件只剩 1 个面，
    整表的 vMerge 也随之错位（与当初读案例 xlsx 是同一类坑）。
    """
    tables = root.find(W + "body").findall(W + "tbl")
    groups = []
    for template_type, tbl in zip(config.TEMPLATE_TYPES, tables):
        members = {}
        order = []
        last = {"floor": "", "position": "", "size": "", "requirement": ""}
        for tr in tbl.findall(W + "tr")[2:]:
            texts = [text_of(tc) for tc in tr.findall(W + "tc")]
            if len(texts) < len(wr.GRID_COLS):
                continue
            for key, column in (("floor", 0), ("position", 1), ("size", 2), ("requirement", 10)):
                if texts[column].strip():
                    last[key] = texts[column]

            member_key = (last["floor"], last["position"])
            if member_key not in members:
                members[member_key] = {
                    "record": {
                        "floor": last["floor"],
                        "member_position": last["position"],
                        "size_result": last["size"],
                        "requirement_text": last["requirement"],
                    },
                    "faces": [],
                }
                order.append(member_key)
            members[member_key]["faces"].append({
                "face": texts[3],
                "readings_text": texts[4:9],
                "min_text": texts[9],
            })
        groups.append({
            "template_type": template_type,
            "records": [members[key] for key in order],
        })
    return groups


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def apply_spec_widths(table_fingerprint, spec_widths) -> dict:
    """把样例指纹里的列宽换成**规格值**（并重算跨列格的 tcW）。

    背景：基准是真实报告裁剪版，规格值就取自它（表2-4）。表2-5 的列宽有 ≤4 twips 的
    Word 自动重算偏差，因此两侧都归一到 ``report_layout.json`` 的列宽，
    "除列宽以外任何一处偏差"依然会被抓住。
    """
    patched = copy.deepcopy(table_fingerprint)
    patched["grid"] = list(spec_widths)
    for row in patched["rows"]:
        column = 0
        for cell in row["cells"]:
            span = int(cell.get("gridSpan") or 1)
            cell["tcW"] = {"w": str(sum(spec_widths[column:column + span])), "type": "dxa"}
            column += span
    return patched


def width_deviation_columns(sample_grid, spec_widths) -> list:
    """样例列宽与规格列宽不一致的列下标（应当恰好等于已声明的偏离列）。"""
    return [index for index, (old, new) in enumerate(zip(sample_grid, spec_widths)) if old != new]


def build_from_sample(output_path, sample_path=None):
    """用样例自身的数据生成报告并保存 —— O3 回灌模式的产物，也是回归基线的来源。"""
    sample_path = Path(sample_path or config.GOLDEN_SAMPLE)
    root = sample_root(sample_path)
    project = extract_project(root)
    groups = extract_groups(root)
    wr.build_project_report(project, groups).save(str(output_path))
    return Path(output_path)


def run_comparison(sample_path=None, output_docx=None) -> dict:
    """执行一次完整对拍，返回结果字典（供脚本与测试共用）。"""
    sample_path = Path(sample_path or config.GOLDEN_SAMPLE)
    if not sample_path.exists():
        raise SystemExit("找不到样例：%s" % sample_path)

    root = sample_root(sample_path)
    with tempfile.TemporaryDirectory() as tmp:
        generated_path = Path(tmp) / "generated.docx"
        build_from_sample(generated_path, sample_path)
        if output_docx:
            Path(output_docx).parent.mkdir(parents=True, exist_ok=True)
            build_from_sample(output_docx, sample_path)

        expected = document_fingerprint(sample_path)
        actual = document_fingerprint(generated_path)
        expected_grids = [layout_grid(tbl) for tbl in root.find(W + "body").findall(W + "tbl")]
        actual_grids = [layout_grid(tbl) for tbl in sample_root(generated_path).find(W + "body").findall(W + "tbl")]

    expected_children = drop_out_of_scope(expected["children"])
    diffs = []

    # 1) 正文序列（段落/表格/sectPr 的顺序与格式）
    diffs += diff(expected_children, actual["children"], "body")

    # 2) 每张表的全部版式属性（列宽/行高/边框/边距/合并/文本）
    #    列宽以**规格**为准（表2-5 的 Word 重算偏差需归一），其余属性以样例为准
    spec_widths = list(wr.GRID_COLS)
    for index in range(min(len(expected["tables"]), len(actual["tables"]))):
        reference = apply_spec_widths(expected["tables"][index], spec_widths)
        diffs += diff(reference, actual["tables"][index], "table[%d]" % index)

    # 3) 合并结构的逻辑网格
    for index in range(min(len(expected_grids), len(actual_grids))):
        if expected_grids[index] != actual_grids[index]:
            diffs.append(("grid[%d]" % index, expected_grids[index], actual_grids[index]))

    # 4) 表数量（样例有玻璃表，生成物只有立柱/横梁）
    expected_tables = len([c for c in expected_children if c["type"] == "tbl"])
    if len(actual["tables"]) != expected_tables:
        diffs.append(("tables.count", expected_tables, len(actual["tables"])))

    return {
        "diffs": diffs,
        "expected_tables": len(expected["tables"]),
        "compared_tables": min(len(expected["tables"]), len(actual["tables"])),
        "expected_grids": expected_grids,
        "actual_grids": actual_grids,
        "sample_widths": expected["tables"][0]["grid"] if expected["tables"] else [],
        "spec_widths": list(wr.GRID_COLS),
    }


def build_markdown(result, sample_name: str) -> str:
    diffs = result["diffs"]
    lines = [
        "# Word 导出与客户样例对拍报告",
        "",
        "- 基准：`%s`" % sample_name,
        "- 方式：从样例回灌其自身数据后重新生成，逐属性比较",
        "- 比对项：正文序列、表格级属性、行级属性、单元格级属性、合并网格",
        "",
    ]
    if diffs:
        lines.append("**结果：不一致 %d 处**" % len(diffs))
        lines.append("")
        lines.append("| # | 路径 | 期望（样例） | 实际（生成） |")
        lines.append("|---|---|---|---|")
        for index, (path, exp, act) in enumerate(diffs[:40], 1):
            lines.append("| %d | `%s` | `%s` | `%s` |"
                         % (index, path, repr(exp)[:60], repr(act)[:60]))
    else:
        lines += [
            "**结果：全部一致 ✅**",
            "",
            "生成的立柱表与横梁表在下列维度与样例完全相同：",
            "",
            "- 表格：总宽、居中方式、固定布局、六边边框、表级单元格边距、tblLook",
            "- 行：行高（含 hRule 语义）、行内居中",
            "- 单元格：gridSpan、vMerge、tcMar、vAlign、表头行距、段落对齐、run 属性",
            "- 合并结构：表头跨 7 列 + 四列纵向合并 +「截面尺寸要求」按同一条文合并的逻辑网格",
            "- 正文：信息段 / 章节标题 / 表格后空段 / 备注 / 文末空段的顺序与间距",
            "",
            "> 基准即**真实客户报告**第 12-13 页的裁剪版，规格值见 `webapp/resources/report_layout.json`，"
            "两侧都归一到该规格（表2-5 的列宽有 ≤4 twips 的 Word 重算偏差），因此不存在"
            "「对样例的有意偏离」；任何一处偏差都会被本报告抓住。",
            "",
            "> 基准已裁掉玻璃/膜厚等范围外章节；同时反向断言生成物不含这些内容。",
        ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Word 报告与客户样例逐单元格对拍")
    parser.add_argument("--sample", default=str(config.GOLDEN_SAMPLE), help="对拍基准（样例 docx）")
    parser.add_argument("--verbose", action="store_true", help="列出全部差异")
    parser.add_argument("--report", help="把结果写成 markdown 报告")
    parser.add_argument("--output", help="把生成的文档另存到指定路径（便于人工查看）")
    parser.add_argument("--bless", action="store_true",
                        help="重新冻结回归基线 tests/fixtures/generated_baseline.docx")
    args = parser.parse_args()

    if args.bless:
        path = build_from_sample(config.GENERATED_BASELINE, args.sample)
        print("回归基线已重新冻结：%s" % path)

    result = run_comparison(args.sample, args.output)
    diffs = result["diffs"]

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(
            build_markdown(result, Path(args.sample).name), encoding="utf-8")
        print("报告已写入 %s" % args.report)

    print("比对项：正文序列 + %d 张表（含每格属性）+ 合并网格" % result["compared_tables"])
    if not diffs:
        print("结果：全部一致 ✅")
        return 0

    print("结果：不一致 %d 处" % len(diffs))
    shown = diffs if args.verbose else diffs[:MAX_SHOWN_DIFFS]
    for path, exp, act in shown:
        print("  %-46s 期望=%-28s 实际=%s" % (path, repr(exp)[:28], repr(act)[:40]))
    if len(diffs) > len(shown):
        print("  …（其余 %d 处，用 --verbose 查看）" % (len(diffs) - len(shown)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
