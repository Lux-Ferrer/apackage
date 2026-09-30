# -*- coding: utf-8 -*-
"""从任意一份检测报告 .docx 里提取版式规格，并与当前 report_layout.json 对比。

用途：客户给来一份**真实的**脱敏报告后，一条命令就能看出"哪些版式数值与现基准不同"，
而不必手工比对 OOXML。提取结果写成候选 JSON 供人工确认，**不会自动覆盖** report_layout.json。

提取内容是**泛化检测**的，不假设列数固定：

- 表头第一行里找出 ``gridSpan > 1`` 的跨列单元格 —— 那就是"厚度检测结果"块；
- 它左边的列 = 楼层 / 构件位置 / 尺寸结果…；右边的列 = 截面尺寸要求…；
- 表头第二行落在该跨列范围内的单元格 = 面 / 1 / 2 / … / 最小；
- 数据行里出现 ``vMerge=restart`` 的列 = 多面构件需要纵向合并的列。

用法::

    python tools/extract_layout_spec.py <报告.docx>                 # 对比当前规格
    python tools/extract_layout_spec.py <报告.docx> --json out.json # 另写候选规格
    python tools/extract_layout_spec.py <报告.docx> --report out.md # markdown 差异报告
    python tools/extract_layout_spec.py <报告.docx> --table 2       # 指定用第几张表
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lxml import etree                                          # noqa: E402

from compare_report_with_sample import attr_map, text_of, val_of   # noqa: E402
from webapp import config                                       # noqa: E402
from webapp.services import word_report as wr                   # noqa: E402

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# --------------------------------------------------------------------------
# OOXML 小工具
# --------------------------------------------------------------------------
def body_children(root) -> list:
    """返回 [(tag, element)]，tag ∈ {p, tbl, sectPr}。"""
    out = []
    for child in root.find(W + "body"):
        tag = etree.QName(child).localname
        if tag in ("p", "tbl", "sectPr"):
            out.append((tag, child))
    return out


def coerce(value):
    """把纯数字字符串转成 int，便于与 report_layout.json 里的数值直接比较。"""
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def half_points_to_pt(value):
    return None if value is None else float(value) / 2


def run_size_pt(paragraph):
    """段落里第一个带 w:sz 的 run 的字号（pt）；没有则 None（继承）。"""
    for run in paragraph.findall(W + "r"):
        rpr = run.find(W + "rPr")
        if rpr is None:
            continue
        size = rpr.find(W + "sz")
        if size is not None:
            return half_points_to_pt(size.get(W + "val"))
    return None


def spacing_map(paragraph) -> dict:
    ppr = paragraph.find(W + "pPr")
    spacing = ppr.find(W + "spacing") if ppr is not None else None
    if spacing is None:
        return {}
    return {etree.QName(key).localname: int(value) for key, value in spacing.attrib.items()
            if etree.QName(key).localname in ("before", "after")}


def paragraph_texts(tc) -> list:
    """单元格的逐段文本（表头里「检测构件」/「位置」是两段，不是自动折行）。"""
    texts = [text_of(p) for p in tc.findall(W + "p")]
    while texts and not texts[-1]:
        texts.pop()
    return texts


def cell_text(tc) -> str:
    """单元格文本，段落之间用 ``\\n`` 连接 —— 与 report_layout.json 的写法一致。"""
    return "\n".join(paragraph_texts(tc))


def line_spacing_indexes(row) -> tuple:
    """该行里被显式设了 ``w:spacing[@w:line]`` 的单元格下标，以及那个行距值。

    客户模板里表头前几格被手工设过固定行距；数值本身对版面无影响，
    但为了"逐属性一致"要照抄，因此提取器必须能读出它。
    """
    indexes, line, rule = [], None, None
    for index, tc in enumerate(row.findall(W + "tc")):
        hit = False
        for paragraph in tc.findall(W + "p"):
            ppr = paragraph.find(W + "pPr")
            spacing = ppr.find(W + "spacing") if ppr is not None else None
            if spacing is None or spacing.get(W + "line") is None:
                continue
            hit = True
            if line is None:
                line = int(spacing.get(W + "line"))
                rule = spacing.get(W + "lineRule")
        if hit:
            indexes.append(index)
    return indexes, line, rule


def cell_props(tc) -> dict:
    tcpr = tc.find(W + "tcPr")
    if tcpr is None:
        return {}
    tcmar = tcpr.find(W + "tcMar")
    return {
        "width": int(tcpr.find(W + "tcW").get(W + "w")) if tcpr.find(W + "tcW") is not None else None,
        "span": int(val_of(tcpr.find(W + "gridSpan")) or 1),
        "vmerge": (val_of(tcpr.find(W + "vMerge")) or "continue")
        if tcpr.find(W + "vMerge") is not None else None,
        "margins": {etree.QName(e).localname: int(e.get(W + "w")) for e in tcmar} if tcmar is not None else None,
    }


def find_detection_tables(root) -> list:
    """找出所有"看起来是检测表"的表（表头含「楼层」）。返回 [(index, tbl)]。"""
    found = []
    for index, (tag, element) in enumerate(body_children(root)):
        if tag != "tbl":
            continue
        if any("楼层" in text_of(tc) for tc in element.findall(W + "tr")[0].findall(W + "tc")):
            found.append((index, element))
    return found


def section_for(children, table_index: int):
    """求某张表所属的 ``sectPr``。

    多节文档里正文末尾那个 ``sectPr`` 往往属于**最后一节**（封面/落款那节），
    直接拿它当"本表的页面设置"会读出一堆无关差异。OOXML 的规则是：
    段落 ``pPr`` 里的 ``sectPr`` 结束它**前面**那一节，所以本表所属的节
    就是"从本表往后第一个带 sectPr 的段落"（没有则用正文末尾的 sectPr）。
    """
    for tag, element in children[table_index + 1:]:
        if tag != "p":
            continue
        ppr = element.find(W + "pPr")
        sect = ppr.find(W + "sectPr") if ppr is not None else None
        if sect is not None:
            return sect
    for tag, element in children:
        if tag == "sectPr":
            return element
    return None


# --------------------------------------------------------------------------
# 提取
# --------------------------------------------------------------------------
def extract(path, table_ordinal: int | None = None) -> dict:
    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))

    children = body_children(root)
    tables = find_detection_tables(root)
    if not tables:
        raise SystemExit("这份文档里没有找到含「楼层」表头的检测表：%s" % path)

    warnings = []
    if len(tables) > 1 and table_ordinal is None:
        grids = {tuple(int(g.get(W + "w")) for g in tbl.find(W + "tblGrid").findall(W + "gridCol"))
                 for _index, tbl in tables}
        if len(grids) > 1:
            warnings.append("文档里有 %d 张检测表，但列宽互不相同（下表取第一张；可用 --table 指定）"
                            % len(tables))

    chosen = tables[(table_ordinal or 1) - 1]
    table_index, tbl = chosen
    rows = tbl.findall(W + "tr")
    tbl_pr = tbl.find(W + "tblPr")

    # ---- 表头结构（泛化：靠 gridSpan 找出跨列块）----
    row0_cells = rows[0].findall(W + "tc")
    spanned_at = next((i for i, tc in enumerate(row0_cells) if cell_props(tc)["span"] > 1), None)
    if spanned_at is None:
        raise SystemExit("表头第一行里没有跨列单元格，无法定位「厚度检测结果」块")

    span = cell_props(row0_cells[spanned_at])["span"]
    before = [cell_text(tc) for tc in row0_cells[:spanned_at]]
    after = [cell_text(tc) for tc in row0_cells[spanned_at + 1:]]
    thickness_header = cell_text(row0_cells[spanned_at])

    row1_cells = rows[1].findall(W + "tc")
    sub_headers = [cell_text(tc) for tc in row1_cells[spanned_at:spanned_at + span]]

    grid = [int(g.get(W + "w")) for g in tbl.find(W + "tblGrid").findall(W + "gridCol")]
    total_columns = len(grid)

    # 列下标映射：跨列块的位置决定"面/读数/最小值"，其后一列是要求
    index_map = {
        "floor": 0,
        "position": 1,
        "size": 2,
        "face": spanned_at,
        "readingFirst": spanned_at + 1,
        "readingCount": max(0, span - 2),
        "minimum": spanned_at + span - 1,
        "requirement": total_columns - 1,
    }

    # ---- 列名映射（mergedInBody 用名字而不是下标，与本 JSON 的可读性一致）----
    name_by_index = {
        index_map["floor"]: "floor",
        index_map["position"]: "position",
        index_map["size"]: "size",
        index_map["face"]: "face",
        index_map["minimum"]: "minimum",
        index_map["requirement"]: "requirement",
    }
    for offset in range(index_map["readingCount"]):
        name_by_index[index_map["readingFirst"] + offset] = "reading%d" % (offset + 1)

    # ---- 数据行：行高 + 纵向合并的列 ----
    data_rows = rows[2:]
    # 扫**所有**数据行：多面构件可能不在第一行（横梁表常见），只看首行会漏检
    seen = set()
    for tr in data_rows:
        for column, tc in enumerate(tr.findall(W + "tc")):
            if cell_props(tc)["vmerge"] == "restart":
                seen.add(column)
    merged_columns = [name_by_index.get(column, "column%d" % column) for column in sorted(seen)]
    if not merged_columns:
        # 该报告的检测表完全没有纵向合并（或没有数据行）→ 保留当前规格值并提示
        merged_columns = list(wr.MERGED_IN_BODY)
        warnings.append("数据行里没有 vMerge —— 该报告的检测表可能没有多面构件，"
                        "无法据此确认'多面构件合并哪几列'，已沿用当前规格值")

    def row_height(tr):
        trpr = tr.find(W + "trPr")
        height = trpr.find(W + "trHeight") if trpr is not None else None
        return int(height.get(W + "val")) if height is not None else None

    header_heights = [row_height(tr) for tr in rows[:2]]
    data_height = row_height(data_rows[0]) if data_rows else None

    # ---- 两张检测表的数据行高不同（立柱 / 横梁），按模板各取一份 ----
    # 用「截面尺寸要求」表头的**文案**判定模板类型：报告里还有膜厚/玻璃/铝板/石材
    # 等十几张同样含「楼层」的表，它们不是我们的模板，不能混进来（否则行高被覆盖）。
    label_to_template = {label.replace("\n", ""): name
                         for name, label in config.REQUIREMENT_LABELS.items()}

    def template_type_of(other):
        header_cells = other.findall(W + "tr")[0].findall(W + "tc")
        if not header_cells:
            return None
        return label_to_template.get(cell_text(header_cells[-1]).replace("\n", ""))

    height_by_template = {"column": None, "beam": None}
    for _index, other in tables:
        other_rows = other.findall(W + "tr")
        if len(other_rows) < 3:
            continue
        template = template_type_of(other)
        if template is None:
            continue
        height_by_template[template] = row_height(other_rows[2])

    # ---- 单元格边距 ----
    normal_margins = cell_props(row0_cells[0])["margins"] or {}
    requirement_margins = None
    requirement_pt = None
    if data_rows:
        cells = data_rows[0].findall(W + "tc")
        if len(cells) > index_map["requirement"]:
            requirement_cell = cells[index_map["requirement"]]
            requirement_margins = cell_props(requirement_cell)["margins"]
            requirement_pt = run_size_pt(requirement_cell.find(W + "p"))

    # ---- 正文段落与字号 ----
    def paragraphs(kind):
        return [element for tag, element in children if tag == kind]

    body_paragraphs = paragraphs("p")
    before_table = [element for tag, element in children[:table_index] if tag == "p"]
    after_table = [element for tag, element in children[table_index + 1:] if tag == "p"]

    info_paragraph = before_table[0] if before_table else None
    title_paragraph = before_table[-1] if len(before_table) > 1 else None
    spacer_paragraph = next((p for p in after_table if not text_of(p)), None)
    note_paragraph = next((p for p in body_paragraphs if text_of(p).startswith("备注")), None)

    # 表格单元格继承字号：看**非要求列**的数据格是否显式写了 sz
    # （要求列本身就是显式 8pt，不能拿它当"继承值"）
    inherited_pt = wr.INHERITED_TABLE_PT
    if data_rows:
        others = [tc for column, tc in enumerate(data_rows[0].findall(W + "tc"))
                  if column != index_map["requirement"]]
        explicit = None
        for tc in others:
            explicit = run_size_pt(tc.find(W + "p"))
            if explicit is not None:
                break
        if explicit is None:
            warnings.append("普通数据单元格未显式写字号（继承）—— 已保留当前值 %gpt，请用 Word 人工确认"
                            % wr.INHERITED_TABLE_PT)
        else:
            inherited_pt = explicit

    # ---- 页面（取本表所属的那一节，而不是正文末尾那节）----
    sect_pr = section_for(children, table_index)
    page = {}
    if sect_pr is not None:
        pg_sz = attr_map(sect_pr.find(W + "pgSz"))
        pg_mar = attr_map(sect_pr.find(W + "pgMar"))
        grid_el = attr_map(sect_pr.find(W + "docGrid"))
        page = {
            "widthTwips": int(pg_sz.get("w", 0)),
            "heightTwips": int(pg_sz.get("h", 0)),
            "marginTwips": int(pg_mar.get("top", 0)),
            "marginBottomTwips": int(pg_mar.get("bottom", 0)),
            "marginHorizontalTwips": int(pg_mar.get("left", 0)),
            "headerFooterTwips": int(pg_mar.get("header", 0)),
            "footerTwips": int(pg_mar.get("footer", 0)),
            "docGridLinePitch": coerce(grid_el.get("linePitch")),
        }

    borders = tbl_pr.find(W + "tblBorders")
    outer = attr_map(borders.find(W + "top")) if borders is not None else {}
    inner = attr_map(borders.find(W + "insideH")) if borders is not None else {}
    table_cell_margin = tbl_pr.find(W + "tblCellMar")

    row0_spacing_cells, line_value, line_rule = line_spacing_indexes(rows[0])
    row1_spacing_cells, line_value_1, line_rule_1 = line_spacing_indexes(rows[1])
    line_value = line_value if line_value is not None else line_value_1
    line_rule = line_rule if line_rule is not None else line_rule_1

    spec = {
        "page": page,
        "table": {
            "widthTwips": int(tbl_pr.find(W + "tblW").get(W + "w")),
            "align": val_of(tbl_pr.find(W + "jc")),
            "layout": attr_map(tbl_pr.find(W + "tblLayout")).get("type"),
            "border": {"val": outer.get("val"), "space": int(outer.get("space", 0)),
                       "color": outer.get("color"),
                       "outerSz": int(outer.get("sz", 0)), "innerSz": int(inner.get("sz", 0))},
            "tableCellMargin": ({etree.QName(e).localname: int(e.get(W + "w")) for e in table_cell_margin}
                                if table_cell_margin is not None else {}),
            # w:val 是 "0000" 这样的位串，不能当数字（否则前导零丢失）
            "look": {etree.QName(k).localname: (v if etree.QName(k).localname == "val" else coerce(v))
                     for k, v in tbl_pr.find(W + "tblLook").attrib.items()},
        },
        "columns": {"widths": grid, "index": index_map, "mergedInBody": merged_columns},
        "rows": {"headerHeightTwips": header_heights[0], "dataHeightTwips": data_height,
                 "dataHeightByTemplate": height_by_template},
        "cell": {
            "marginVerticalTwips": normal_margins.get("top"),
            "marginHorizontalTwips": normal_margins.get("left"),
            "requirementMarginTwips": (requirement_margins or {}).get("left"),
            "headerLineSpacing": {"line": line_value, "lineRule": line_rule,
                                  "row0Cells": row0_spacing_cells, "row1Cells": row1_spacing_cells},
        },
        "fonts": {
            "inheritedTablePt": inherited_pt,
            "requirementPt": requirement_pt,
            "bodyPt": run_size_pt(info_paragraph) if info_paragraph is not None else None,
            "titlePt": run_size_pt(title_paragraph) if title_paragraph is not None else None,
        },
        "paragraphSpacing": {
            "infoAfter": spacing_map(info_paragraph).get("after") if info_paragraph is not None else None,
            "titleBefore": spacing_map(title_paragraph).get("before") if title_paragraph is not None else None,
            "titleAfter": spacing_map(title_paragraph).get("after") if title_paragraph is not None else None,
            "spacerBefore": spacing_map(spacer_paragraph).get("before") if spacer_paragraph is not None else None,
            "spacerAfter": spacing_map(spacer_paragraph).get("after") if spacer_paragraph is not None else None,
            "noteBefore": spacing_map(note_paragraph).get("before") if note_paragraph is not None else None,
        },
        "headers": {
            "fixed": before,
            "thickness": thickness_header,
            "thicknessSub": sub_headers,
        },
        "spans": {"thickness": span},
        "_extractedFrom": Path(path).name,
        "_detectionTables": len(tables),
        "_warnings": warnings,
        "_extraHeaderColumns": after,
    }
    return spec


# --------------------------------------------------------------------------
# 对比
# --------------------------------------------------------------------------
def flatten(data, prefix="") -> dict:
    flat = {}
    for key, value in data.items():
        if key.startswith("_"):
            continue
        path = "%s.%s" % (prefix, key) if prefix else key
        if isinstance(value, dict):
            flat.update(flatten(value, path))
        else:
            flat[path] = value
    return flat


# 不从检测报告里提取的键：
# - ``attachment.*``：缺陷报告附页的渲染参数，属我们自己的实现规格（需求报告 4.4 + M3 决策）；
# - ``paragraphSpacing.*`` 与 ``fonts.bodyPt/titlePt``：信息段/标题/空段/备注这套**段落骨架**
#   是我们按需求报告 4.2 自己定的，客户报告的正文结构在范围之外，比它只会产生"缺失"噪音。
IGNORED_PREFIXES = ("attachment.", "paragraphSpacing.")
IGNORED_KEYS = ("fonts.bodyPt", "fonts.titlePt")


def compare(current, candidate) -> list:
    left, right = flatten(current), flatten(candidate)
    diffs = []
    for key in sorted(set(left) | set(right)):
        if key.startswith(IGNORED_PREFIXES) or key in IGNORED_KEYS:
            continue
        old, new = left.get(key, "（缺）"), right.get(key, "（缺）")
        if old != new:
            diffs.append((key, old, new))
    return diffs


def describe_width_diff(sample_widths, spec_widths, spec) -> list:
    """把列宽差异按列说明，便于人工确认（比丢两个列表可读得多）。"""
    overrides = spec.get("columns", {}).get("_widthOverrides", {})
    names = {0: "楼层", 1: "构件位置", 2: "尺寸结果", 3: "检测面"}
    for offset in range(spec.get("columns", {}).get("index", {}).get("readingCount", 5)):
        names[4 + offset] = "读数 %d" % (offset + 1)
    names[9] = "最小值"
    names[10] = "截面尺寸要求"

    lines = []
    for index, (old, new) in enumerate(zip(sample_widths, spec_widths)):
        if old == new:
            continue
        label = names.get(index, "第 %d 列" % index)
        declared = ""
        if label == "楼层" and "floor" in overrides:
            declared = "（已声明：%s）" % overrides["floor"].get("reason", "")
        elif label.startswith("读数") and "reading" in overrides:
            declared = "（已声明：为楼层列匀出空间）"
        lines.append("第 %d 列 %s：样例 %d → 生效 %d%s" % (index, label, old, new, declared))
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="从报告 docx 提取版式规格并与当前规格对比")
    parser.add_argument("report", help="报告 .docx 路径")
    parser.add_argument("--table", type=int, help="用第几张检测表（默认第一张）")
    parser.add_argument("--json", help="把候选规格写到指定路径")
    parser.add_argument("--report-md", dest="report_md", help="把差异写成 markdown")
    parser.add_argument("--label", help="候选来源的显示名（默认用文件名；"
                                        "从 .doc 转出来的中间文件可在这里写原始文件名）")
    parser.add_argument("--quiet", action="store_true", help="只输出差异")
    args = parser.parse_args()

    path = Path(args.report)
    if not path.exists():
        raise SystemExit("找不到文件：%s" % path)

    candidate = extract(path, args.table)
    label = args.label or path.name
    diffs = compare(wr.SPEC, candidate)

    if not args.quiet:
        print("提取自：%s" % label)
        print("检测表数量：%d；列数：%d；跨列块：第 %d 列起 %d 列"
              % (candidate["_detectionTables"], len(candidate["columns"]["widths"]),
                 candidate["columns"]["index"]["face"], candidate["spans"]["thickness"]))
        print("表头固定列：%s" % candidate["headers"]["fixed"])
        print("厚度子表头：%s" % candidate["headers"]["thicknessSub"])
        print("跨列块之后还有 %d 列：%s" % (len(candidate["_extraHeaderColumns"]),
                                            candidate["_extraHeaderColumns"]))
        print("数据行纵向合并的列：%s" % (candidate["columns"]["mergedInBody"] or "（未检出）"))
        print("列宽：%s" % candidate["columns"]["widths"])
        for warning in candidate["_warnings"]:
            print("  ⚠ %s" % warning)
        print()

    if not diffs:
        print("结果：与当前 report_layout.json 完全一致 ✅")
    else:
        print("结果：%d 处与当前规格不同" % len(diffs))
        print("%-46s %-28s %s" % ("键", "当前值", "新报告值"))
        print("-" * 100)
        for key, old, new in diffs:
            print("%-46s %-28s %s" % (key, repr(old)[:28], repr(new)[:40]))
        if any(key == "columns.widths" for key, _old, _new in diffs):
            print()
            print("列宽逐列差异：")
            for line in describe_width_diff(candidate["columns"]["widths"], wr.GRID_COLS, wr.SPEC):
                print("  - %s" % line)

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(
            json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("\n候选规格已写入 %s（未自动覆盖 report_layout.json）" % args.json)

    if args.report_md:
        lines = ["# 版式规格差异（候选报告 vs 当前基准）", "",
                 "- 候选来源：`%s`" % label,
                 "- 检测表数量：%d；列数：%d" % (candidate["_detectionTables"],
                                                 len(candidate["columns"]["widths"])), ""]
        if diffs:
            lines += ["| 键 | 当前值 | 新报告值 |", "| --- | --- | --- |"]
            lines += ["| `%s` | `%s` | `%s` |" % (k, old, new) for k, old, new in diffs]
        else:
            lines.append("**与当前规格完全一致 ✅**")
        if candidate["_warnings"]:
            lines += ["", "## 提取时的提示", ""] + ["- %s" % w for w in candidate["_warnings"]]
        Path(args.report_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("差异报告已写入 %s" % args.report_md)

    return 0


if __name__ == "__main__":
    sys.exit(main())
