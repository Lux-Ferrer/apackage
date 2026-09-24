# -*- coding: utf-8 -*-
"""Word 报告生成：底座 + 版式规格 + 立柱/横梁表构建 + 项目级报告装配。

版式规格不写死在代码里，而是放在 ``webapp/resources/report_layout.json``：
所有数值实测自对拍基准 ``tests/fixtures/金骐智谷_金骐_检测报告.docx``，
并由 ``tests/test_word_report.py::test_layout_spec_matches_sample`` 上锁。
该 JSON 语言中立——将来把导出逻辑移植到前端（docx JS）时可直接复用同一份数值。

底座（:func:`new_document`）：
优先从 ``webapp/resources/report_base.docx`` 继承（样例派生，保留 theme/styles/sectPr），
因此 A4 纸张、页边距、以及**西文 Times New Roman + 中文主题字体（等线）**与样例一致，
代码里不硬编码任何中文字体名。

复刻要点（均为实测，容易做错的地方）：
- 表头「厚度检测结果 (mm)」横向跨 7 列 → 该行只写 5 个 ``w:tc``；
- 纵向合并的 continue 单元格是"裸格"：只有 ``tcW + vMerge``，无 ``tcMar``/``vAlign``，
  段落是不带 ``pPr`` 的空 ``<w:p/>``；
- 「截面尺寸要求」列的数据格用 8pt + 左右 60 边距（为长条文挤空间，样例原样如此）；
- 其余单元格不写字号（继承，Word 下为 10pt）；普通数据格的 run **不带 ``rPr``**。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Twips
from lxml import etree

from .. import config

# --------------------------------------------------------------------------
# 版式规格（唯一数据源，语言中立）
# --------------------------------------------------------------------------
SPEC_PATH = Path(__file__).resolve().parent.parent / "resources" / "report_layout.json"


def load_spec(path=None) -> dict:
    return json.loads(Path(path or SPEC_PATH).read_text(encoding="utf-8"))


SPEC = load_spec()

# —— 页面 ——
PAGE_WIDTH_TWIPS = SPEC["page"]["widthTwips"]
PAGE_HEIGHT_TWIPS = SPEC["page"]["heightTwips"]
PAGE_MARGIN_TWIPS = SPEC["page"]["marginTwips"]
HEADER_FOOTER_TWIPS = SPEC["page"]["headerFooterTwips"]
DOC_GRID_LINE_PITCH = SPEC["page"]["docGridLinePitch"]

# —— 表格 ——
TABLE_WIDTH_TWIPS = SPEC["table"]["widthTwips"]
GRID_COLS = tuple(SPEC["columns"]["widths"])
COLUMN_INDEX = SPEC["columns"]["index"]
MERGED_IN_BODY = tuple(SPEC["columns"]["mergedInBody"])
THICKNESS_FIRST_COL = COLUMN_INDEX["face"]
THICKNESS_SPAN = SPEC["spans"]["thickness"]
HEADER_ROW_TWIPS = SPEC["rows"]["headerHeightTwips"]
DATA_ROW_TWIPS = SPEC["rows"]["dataHeightTwips"]
BORDER_SIZE = SPEC["table"]["border"]["sz"]
BORDER_COLOR = SPEC["table"]["border"]["color"]

CELL_MARGIN_VERTICAL = SPEC["cell"]["marginVerticalTwips"]
CELL_MARGIN_HORIZONTAL = SPEC["cell"]["marginHorizontalTwips"]
REQUIREMENT_MARGIN = SPEC["cell"]["requirementMarginTwips"]

# —— 字号（pt）——
INHERITED_TABLE_PT = SPEC["fonts"]["inheritedTablePt"]   # 表格正文继承值，文档用，不写入 XML
REQUIREMENT_PT = SPEC["fonts"]["requirementPt"]
BODY_PT = SPEC["fonts"]["bodyPt"]
TITLE_PT = SPEC["fonts"]["titlePt"]
TITLE_SIZE = Pt(TITLE_PT)
BODY_SIZE = Pt(BODY_PT)
REQUIREMENT_SIZE = Pt(REQUIREMENT_PT)

# —— 段落间距（w:spacing 的单位是 1/20 pt）——
SPACING = SPEC["paragraphSpacing"]

# —— 表头文案（照抄样例，含空格）——
HEADER_FIXED = tuple(SPEC["headers"]["fixed"])
HEADER_THICKNESS = SPEC["headers"]["thickness"]
HEADER_THICKNESS_SUB = tuple(SPEC["headers"]["thicknessSub"])

ASCII_FONT = "Times New Roman"

# 二列信息表（旧缺陷单页导出用，需求报告 4.4）
INFO_LABEL_WIDTH = 1600
INFO_VALUE_WIDTH = TABLE_WIDTH_TWIPS - INFO_LABEL_WIDTH

# --------------------------------------------------------------------------
# OOXML 子元素顺序（顺序不符合 schema 时 Word 可能报文档损坏）
# --------------------------------------------------------------------------
_TBLPR_ORDER = (
    "tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
    "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd",
    "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook",
    "tblCaption", "tblDescription",
)
_TCPR_ORDER = (
    "cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
    "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark",
)
_TRPR_ORDER = (
    "cnfStyle", "divId", "gridBefore", "gridAfter", "wBefore", "wAfter",
    "cantSplit", "trHeight", "tblHeader", "tblCellSpacing", "jc", "hidden",
)
_PPR_ORDER = (
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr",
    "widowControl", "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs",
    "suppressAutoHyphens", "kinsoku", "wordWrap", "overflowPunct",
    "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
    "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents",
    "suppressOverlap", "jc", "textDirection", "textAlignment", "textboxTightWrap",
    "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr", "pPrChange",
)
_SECTPR_ORDER = (
    "footnotePr", "endnotePr", "type", "pgSz", "pgMar", "paperSrc",
    "pgBorders", "lnNumType", "pgNumType", "cols", "formProt",
    "vAlign", "noEndnote", "titlePg", "textDirection", "bidi",
    "rtlGutter", "docGrid", "printerSettings",
)


def _insert_ordered(parent, element, order):
    """按 OOXML schema 顺序把 element 插入 parent。"""
    tag = etree.QName(element).localname
    index = order.index(tag)
    for child in parent:
        child_tag = etree.QName(child).localname
        if child_tag in order and order.index(child_tag) > index:
            child.addprevious(element)
            return element
    parent.append(element)
    return element


def _get_or_add(parent, tag, order):
    existing = parent.find(qn(tag))
    if existing is not None:
        return existing
    return _insert_ordered(parent, OxmlElement(tag), order)


# --------------------------------------------------------------------------
# 底座
# --------------------------------------------------------------------------
def clear_body(doc) -> None:
    """清空正文（段落 + 表格），保留末尾 sectPr。"""
    body = doc.element.body
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)


def new_document():
    """新建报告文档（继承样例的页面与字体设置）。"""
    template = config.REPORT_BASE_TEMPLATE
    if template.exists():
        doc = Document(str(template))
        clear_body(doc)
        return doc

    doc = Document()                      # 兜底：底座缺失时按样例参数手工设置
    apply_a4_layout(doc)
    apply_default_fonts(doc)
    return doc


def apply_a4_layout(doc) -> None:
    """A4 纸张 + 四边 1440 twips 页边距 + docGrid（与样例 sectPr 一致）。"""
    for section in doc.sections:
        section.page_width = Twips(PAGE_WIDTH_TWIPS)
        section.page_height = Twips(PAGE_HEIGHT_TWIPS)
        section.left_margin = Twips(PAGE_MARGIN_TWIPS)
        section.right_margin = Twips(PAGE_MARGIN_TWIPS)
        section.top_margin = Twips(PAGE_MARGIN_TWIPS)
        section.bottom_margin = Twips(PAGE_MARGIN_TWIPS)
        section.header_distance = Twips(HEADER_FOOTER_TWIPS)
        section.footer_distance = Twips(HEADER_FOOTER_TWIPS)
        grid = _get_or_add(section._sectPr, "w:docGrid", _SECTPR_ORDER)
        grid.set(qn("w:linePitch"), str(DOC_GRID_LINE_PITCH))


def apply_default_fonts(doc) -> None:
    """西文 Times New Roman + 中文走主题字体（不硬编码中文字体名）。"""
    styles_el = doc.styles.element
    doc_defaults = styles_el.find(qn("w:docDefaults"))
    if doc_defaults is None:
        doc_defaults = OxmlElement("w:docDefaults")
        styles_el.insert(0, doc_defaults)

    rpr_default = doc_defaults.find(qn("w:rPrDefault"))
    if rpr_default is None:
        rpr_default = OxmlElement("w:rPrDefault")
        doc_defaults.insert(0, rpr_default)

    rpr = rpr_default.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        rpr_default.append(rpr)

    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)

    rfonts.set(qn("w:ascii"), ASCII_FONT)
    rfonts.set(qn("w:hAnsi"), ASCII_FONT)
    rfonts.set(qn("w:cs"), ASCII_FONT)
    rfonts.set(qn("w:eastAsiaTheme"), "minorEastAsia")
    if rfonts.get(qn("w:eastAsia")) is not None:
        del rfonts.attrib[qn("w:eastAsia")]


# --------------------------------------------------------------------------
# run / 段落写入（原始 XML，便于与样例逐属性对齐）
# --------------------------------------------------------------------------
def _add_run(paragraph_element, text: str, *, bold: bool = False,
             size_pt: float | None = None):
    """写入一个 run；无格式时不写 rPr（与样例的普通数据格一致）。"""
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    if bold:
        rpr.append(OxmlElement("w:b"))
        rpr.append(OxmlElement("w:bCs"))
    if size_pt is not None:
        half_points = str(int(round(size_pt * 2)))
        size = OxmlElement("w:sz")
        size.set(qn("w:val"), half_points)
        size_cs = OxmlElement("w:szCs")
        size_cs.set(qn("w:val"), half_points)
        rpr.append(size)
        rpr.append(size_cs)
    if len(rpr):
        run.append(rpr)
    text_el = OxmlElement("w:t")
    text_el.text = text
    run.append(text_el)
    paragraph_element.append(run)
    return run


def _add_paragraph(container, text: str = "", *, bold: bool = False,
                   size_pt: float | None = None, align: str | None = "center",
                   before: int | None = None, after: int | None = None,
                   with_props: bool = True):
    """在 tc / body 内追加一个段落。

    ``container`` 可以是 ``CT_Tc``（单元格）或 ``Document``（正文）。
    ``with_props=False`` 用于纵向合并的 continue 单元格：段落是裸的 ``<w:p/>``。
    """
    if hasattr(container, "add_p"):
        paragraph = container.add_p()
    else:                                        # Document → 其 body 就是 CT_Body
        paragraph = container.element.body.add_p()
    if with_props:
        ppr = OxmlElement("w:pPr")
        if before is not None or after is not None:
            spacing = OxmlElement("w:spacing")
            if before is not None:
                spacing.set(qn("w:before"), str(before))
            if after is not None:
                spacing.set(qn("w:after"), str(after))
            _insert_ordered(ppr, spacing, _PPR_ORDER)
        if align is not None:
            jc = OxmlElement("w:jc")
            jc.set(qn("w:val"), align)
            _insert_ordered(ppr, jc, _PPR_ORDER)
        if len(ppr):
            paragraph.insert(0, ppr)
    if text:
        _add_run(paragraph, text, bold=bold, size_pt=size_pt)
    return paragraph


# 正文段落（按样例的角色间距）
def add_info_line(doc, text: str):
    """项目信息段：加粗 11pt，段后 100（5pt），左对齐。"""
    return _add_paragraph(doc, text, bold=True, size_pt=BODY_PT,
                          align=None, after=SPACING["infoAfter"])


def add_section_title(doc, text: str):
    """章节标题：居中加粗 16pt，段前 300 段后 200。"""
    return _add_paragraph(doc, text, bold=True, size_pt=TITLE_PT, align="center",
                          before=SPACING["titleBefore"], after=SPACING["titleAfter"])


def add_spacer(doc):
    """表格之后的空段落（样例每张表后都有一个）。"""
    return _add_paragraph(doc, "", align=None,
                          before=SPACING["spacerBefore"], after=SPACING["spacerAfter"])


def add_note(doc, text: str):
    """备注段：常规 11pt，段前 300。"""
    return _add_paragraph(doc, text, bold=False, size_pt=BODY_PT,
                          align=None, before=SPACING["noteBefore"])


def add_trailing_empty(doc):
    """文末空段落（样例 sectPr 之前保留了一个）。"""
    return _add_paragraph(doc, "", align=None)


def add_page_break(doc):
    """插入分页符（附页每份独立成页，M3 使用）。"""
    return doc.add_page_break()


# 兼容 M0 的旧接口（旧缺陷单页导出与既有测试仍在使用）
def add_title(doc, text: str):
    return add_section_title(doc, text)


def add_body_paragraph(doc, text: str, *, bold: bool = False):
    return _add_paragraph(doc, text, bold=bold, size_pt=BODY_PT, align=None)


# --------------------------------------------------------------------------
# 表格：规格 → OOXML
# --------------------------------------------------------------------------
@dataclass
class Cell:
    """一个逻辑单元格的规格。``width`` 是它**跨列之和**（twips）。"""

    text: str = ""
    width: int = 0
    span: int = 1
    vmerge: str | None = None            # None / "restart" / "continue"
    margin_h: int | None = CELL_MARGIN_HORIZONTAL
    margin_v: int | None = CELL_MARGIN_VERTICAL
    vcenter: bool = True
    bold: bool = False
    size_pt: float | None = None         # None = 继承（不写 w:sz）
    align: str | None = "center"
    plain: bool = False                  # True = 段落不写 pPr（continue 裸格）


@dataclass
class Row:
    cells: list = field(default_factory=list)
    height: int = DATA_ROW_TWIPS


def continuation_cell(width: int) -> Cell:
    """纵向合并的后续格：裸格（只有 tcW + vMerge + 空段落）。"""
    return Cell(text="", width=width, vmerge="continue",
                margin_h=None, margin_v=None, vcenter=False, plain=True)


def requirement_cell(text: str, *, vmerge: str | None = None) -> Cell:
    """「截面尺寸要求」列的数据格：8pt + 左右 60 边距（样例原样）。"""
    return Cell(text=text, width=GRID_COLS[COLUMN_INDEX["requirement"]],
                vmerge=vmerge, margin_h=REQUIREMENT_MARGIN, margin_v=REQUIREMENT_MARGIN,
                size_pt=REQUIREMENT_PT)


def _apply_table_properties(table, widths) -> None:
    """tblW / jc / tblBorders / tblLayout / tblCellMar / tblLook（顺序敏感）。"""
    tbl_pr = table._tbl.tblPr

    tbl_w = _get_or_add(tbl_pr, "w:tblW", _TBLPR_ORDER)
    tbl_w.set(qn("w:w"), str(sum(widths)))
    tbl_w.set(qn("w:type"), "dxa")

    jc = _get_or_add(tbl_pr, "w:jc", _TBLPR_ORDER)
    jc.set(qn("w:val"), SPEC["table"]["align"])

    old_borders = tbl_pr.find(qn("w:tblBorders"))
    if old_borders is not None:
        tbl_pr.remove(old_borders)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement("w:%s" % edge)
        element.set(qn("w:val"), SPEC["table"]["border"]["val"])
        element.set(qn("w:sz"), str(SPEC["table"]["border"]["sz"]))
        element.set(qn("w:space"), str(SPEC["table"]["border"]["space"]))
        element.set(qn("w:color"), SPEC["table"]["border"]["color"])
        borders.append(element)
    _insert_ordered(tbl_pr, borders, _TBLPR_ORDER)

    layout = _get_or_add(tbl_pr, "w:tblLayout", _TBLPR_ORDER)
    layout.set(qn("w:type"), SPEC["table"]["layout"])

    old_margin = tbl_pr.find(qn("w:tblCellMar"))
    if old_margin is not None:
        tbl_pr.remove(old_margin)
    cell_margin = OxmlElement("w:tblCellMar")
    for side, value in SPEC["table"]["tableCellMargin"].items():
        element = OxmlElement("w:%s" % side)
        element.set(qn("w:w"), str(value))
        element.set(qn("w:type"), "dxa")
        cell_margin.append(element)
    _insert_ordered(tbl_pr, cell_margin, _TBLPR_ORDER)

    look = _get_or_add(tbl_pr, "w:tblLook", _TBLPR_ORDER)
    for key, value in SPEC["table"]["look"].items():
        look.set(qn("w:%s" % key), str(value))

    grid = table._tbl.find(qn("w:tblGrid"))
    if grid is not None:
        table._tbl.remove(grid)
    new_grid = OxmlElement("w:tblGrid")
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        new_grid.append(col)
    tbl_pr.addnext(new_grid)


def _set_row_properties(tr, height: int) -> None:
    tr_pr = tr.get_or_add_trPr()
    tr_height = _get_or_add(tr_pr, "w:trHeight", _TRPR_ORDER)
    tr_height.set(qn("w:val"), str(height))          # 不写 hRule → "至少"
    jc = _get_or_add(tr_pr, "w:jc", _TRPR_ORDER)
    jc.set(qn("w:val"), "center")


def _write_cell(tc, cell: Cell) -> None:
    tc.clear_content()                               # 保留 tcPr，清掉默认空段落

    tc_pr = tc.get_or_add_tcPr()
    tc_w = _get_or_add(tc_pr, "w:tcW", _TCPR_ORDER)
    tc_w.set(qn("w:w"), str(cell.width))
    tc_w.set(qn("w:type"), "dxa")

    if cell.span > 1:
        span = _get_or_add(tc_pr, "w:gridSpan", _TCPR_ORDER)
        span.set(qn("w:val"), str(cell.span))

    if cell.vmerge is not None:
        vmerge = _get_or_add(tc_pr, "w:vMerge", _TCPR_ORDER)
        if cell.vmerge == "restart":
            vmerge.set(qn("w:val"), "restart")
        elif vmerge.get(qn("w:val")) is not None:
            del vmerge.attrib[qn("w:val")]

    if cell.margin_h is not None and cell.margin_v is not None:
        tc_mar = _get_or_add(tc_pr, "w:tcMar", _TCPR_ORDER)
        for side, value in (("top", cell.margin_v), ("left", cell.margin_h),
                            ("bottom", cell.margin_v), ("right", cell.margin_h)):
            element = OxmlElement("w:%s" % side)
            element.set(qn("w:w"), str(value))
            element.set(qn("w:type"), "dxa")
            tc_mar.append(element)

    if cell.vcenter:
        v_align = _get_or_add(tc_pr, "w:vAlign", _TCPR_ORDER)
        v_align.set(qn("w:val"), "center")

    lines = str(cell.text).split("\n") if cell.text else [""]
    for line in lines:
        _add_paragraph(tc, line, bold=cell.bold, size_pt=cell.size_pt,
                       align=cell.align, with_props=not cell.plain)


def build_table(doc, rows, widths=GRID_COLS):
    """按行规格建表；``widths`` 之和即表宽。"""
    widths = tuple(widths)
    table = doc.add_table(rows=len(rows), cols=len(widths))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _apply_table_properties(table, widths)

    for row_element, row in zip(table.rows, rows):
        _set_row_properties(row_element._tr, row.height)
        tr = row_element._tr
        tcs = tr.findall(qn("w:tc"))
        for surplus in tcs[len(row.cells):]:          # 横向合并 → 该行 tc 数量减少
            tr.remove(surplus)
        for tc, cell in zip(tr.findall(qn("w:tc")), row.cells):
            _write_cell(tc, cell)
    return table


# --------------------------------------------------------------------------
# 立柱 / 横梁表
# --------------------------------------------------------------------------
def _header_rows(template_type: str):
    requirement_label = config.REQUIREMENT_LABELS[template_type]
    first = [
        Cell(text=HEADER_FIXED[0], width=GRID_COLS[0], vmerge="restart", bold=True),
        Cell(text=HEADER_FIXED[1], width=GRID_COLS[1], vmerge="restart", bold=True),
        Cell(text=HEADER_FIXED[2], width=GRID_COLS[2], vmerge="restart", bold=True),
        Cell(text=HEADER_THICKNESS, width=sum(GRID_COLS[THICKNESS_FIRST_COL:THICKNESS_FIRST_COL + THICKNESS_SPAN]),
             span=THICKNESS_SPAN, bold=True),
        Cell(text=requirement_label, width=GRID_COLS[COLUMN_INDEX["requirement"]],
             vmerge="restart", bold=True),
    ]
    second = [
        continuation_cell(GRID_COLS[0]),
        continuation_cell(GRID_COLS[1]),
        continuation_cell(GRID_COLS[2]),
    ]
    second += [Cell(text=label, width=GRID_COLS[THICKNESS_FIRST_COL + offset], bold=True)
               for offset, label in enumerate(HEADER_THICKNESS_SUB)]
    second.append(continuation_cell(GRID_COLS[COLUMN_INDEX["requirement"]]))
    return [
        Row(cells=first, height=HEADER_ROW_TWIPS),
        Row(cells=second, height=HEADER_ROW_TWIPS),
    ]


def _member_rows(item) -> list:
    """一个构件 → 每个检测面一行。

    只有**真正需要合并**（该构件有 ≥2 个检测面）时才写 ``vMerge``：
    单面构件与样例一样不带任何 vMerge —— 一条 vMerge=restart 本身不构成合并，
    但会让文档与样例产生无谓差异。
    """
    record = item["record"]
    faces = item["faces"] or []
    merged = len(faces) > 1
    rows = []
    for index, face in enumerate(faces):
        first = index == 0
        vmerge = ("restart" if first else "continue") if merged else None

        cells = []
        for key, width in (("floor", GRID_COLS[0]), ("position", GRID_COLS[1]),
                           ("size", GRID_COLS[2])):
            if first:
                value = record["floor"] if key == "floor" else (
                    record["member_position"] if key == "position" else (record["size_result"] or ""))
                cells.append(Cell(text=value, width=width, vmerge=vmerge))
            else:
                cells.append(continuation_cell(width))

        cells.append(Cell(text=face["face"], width=GRID_COLS[THICKNESS_FIRST_COL]))
        cells += [Cell(text=text, width=GRID_COLS[THICKNESS_FIRST_COL + 1 + offset])
                  for offset, text in enumerate(face["readings_text"])]
        cells.append(Cell(text=face["min_text"], width=GRID_COLS[COLUMN_INDEX["minimum"]]))

        REQUIREMENT_INDEX = COLUMN_INDEX["requirement"]
        if first:
            requirement = record["requirement_text"] or config.EMPTY_TEXT
            cells.append(requirement_cell(requirement, vmerge=vmerge))
        else:
            cells.append(continuation_cell(GRID_COLS[REQUIREMENT_INDEX]))

        rows.append(Row(cells=cells, height=DATA_ROW_TWIPS))
    return rows


def build_detection_table(doc, group):
    """一张立柱/横梁检测表（表头 2 行 + 每检测面 1 行）。"""
    rows = _header_rows(group["template_type"])
    for item in group["records"]:
        rows.extend(_member_rows(item))
    return build_table(doc, rows)


# --------------------------------------------------------------------------
# 项目级报告
# --------------------------------------------------------------------------
def info_lines(project) -> list:
    """项目信息段：5 行「标签：值」，空值留空。"""
    return [
        "%s：%s" % (label, project[field] or "")
        for field, label in config.PROJECT_INFO_FIELDS
    ]


def build_project_report(project, groups):
    """装配完整报告：信息段 → （章节标题 + 表 + 空段）×N → 备注 → 空段。

    只输出有记录的章节（立柱 / 横梁各自判断）；不输出玻璃模块。
    """
    doc = new_document()
    for line in info_lines(project):
        add_info_line(doc, line)

    for group in groups:
        if not group["records"]:
            continue
        add_section_title(doc, config.TEMPLATE_TITLES[group["template_type"]])
        build_detection_table(doc, group)
        add_spacer(doc)

    add_note(doc, config.NOTE_TEXT)
    add_trailing_empty(doc)
    return doc


_UNSAFE_FILENAME_CHARS = '\\/:*?"<>|'


def report_filename(project) -> str:
    """`项目编号_房屋名称_检测报告.docx`，清理文件名非法字符并限长。"""
    stem, _, extension = config.REPORT_FILENAME.rpartition(".")
    stem = stem.format(project_no=project["project_no"], house_name=project["house_name"])
    cleaned = "".join("_" if (ch in _UNSAFE_FILENAME_CHARS or ord(ch) < 32) else ch
                      for ch in stem).strip().strip(".")
    return "%s.%s" % ((cleaned or "检测报告")[:120], extension or "docx")


def save(doc, path) -> str:
    """保存文档，返回路径字符串。"""
    path = str(path)
    doc.save(path)
    return path


# --------------------------------------------------------------------------
# 旧的单条缺陷导出（M0 迁移版；M3 会换成「检测报告附页」格式）
# --------------------------------------------------------------------------
_DEFECT_FIELDS = (
    ("报告编号", "id", "#%s"),
    ("缺陷类型", "defect_type", "%s"),
    ("工程部位", "project_part", "%s"),
    ("隐患等级", "risk_level", "%s"),
    ("整改方案", "rectification_plan", "%s"),
    ("提交时间", "created_at", "%s"),
)


def build_defect_draft(defect):
    """把一条缺陷记录输出成 A4 文档（临时版）。"""
    doc = new_document()
    add_section_title(doc, "缺陷检测报告（临时版）")

    rows = []
    for label, key, template in _DEFECT_FIELDS:
        value = template % defect[key]
        rows.append(Row(cells=[
            Cell(text=label, width=INFO_LABEL_WIDTH, bold=True, size_pt=BODY_PT),
            Cell(text=value, width=INFO_VALUE_WIDTH, align="left", size_pt=BODY_PT),
        ], height=DATA_ROW_TWIPS))
    build_table(doc, rows, widths=(INFO_LABEL_WIDTH, INFO_VALUE_WIDTH))
    return doc


# --------------------------------------------------------------------------
# M0 起就存在的通用原语（保持兼容）
# --------------------------------------------------------------------------
def even_widths(cols: int, total: int = TABLE_WIDTH_TWIPS):
    """把总宽平均分配给 cols 列（余数给最后一列）。"""
    base, remainder = divmod(total, cols)
    widths = [base] * cols
    widths[-1] += remainder
    return tuple(widths)


def create_table(doc, rows: int, cols: int, widths=None):
    """建一张普通表格（等宽或指定列宽），供旧调用与测试使用。"""
    spec_widths = tuple(widths) if widths is not None else even_widths(cols)
    if len(spec_widths) != cols:
        raise ValueError("列宽数量(%d)与列数(%d)不一致" % (len(spec_widths), cols))
    layout = [Row(cells=[Cell(width=width) for width in spec_widths]) for _ in range(rows)]
    return build_table(doc, layout, spec_widths)


def apply_table_grid(table, widths=GRID_COLS) -> None:
    _apply_table_properties(table, tuple(widths))


def apply_table_borders(table, size: int = BORDER_SIZE, color: str = BORDER_COLOR) -> None:
    """覆盖表格边框（默认即样例的 single/sz=4/auto）。"""
    tbl_pr = table._tbl.tblPr
    old = tbl_pr.find(qn("w:tblBorders"))
    if old is not None:
        tbl_pr.remove(old)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement("w:%s" % edge)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), str(size))
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)
        borders.append(element)
    _insert_ordered(tbl_pr, borders, _TBLPR_ORDER)


def set_cell_margins(cell, top=CELL_MARGIN_VERTICAL, left=CELL_MARGIN_HORIZONTAL,
                     bottom=CELL_MARGIN_VERTICAL, right=CELL_MARGIN_HORIZONTAL) -> None:
    tc_mar = _get_or_add(cell._tc.get_or_add_tcPr(), "w:tcMar", _TCPR_ORDER)
    for tag, value in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        element = _get_or_add(tc_mar, "w:%s" % tag, ("top", "left", "bottom", "right"))
        element.set(qn("w:w"), str(value))
        element.set(qn("w:type"), "dxa")


def set_cell_width(cell, twips: int) -> None:
    tc_w = _get_or_add(cell._tc.get_or_add_tcPr(), "w:tcW", _TCPR_ORDER)
    tc_w.set(qn("w:w"), str(twips))
    tc_w.set(qn("w:type"), "dxa")


def set_cell_valign(cell, value: str = "center") -> None:
    v_align = _get_or_add(cell._tc.get_or_add_tcPr(), "w:vAlign", _TCPR_ORDER)
    v_align.set(qn("w:val"), value)


def set_vertical_merge(cell, restart: bool = True) -> None:
    """纵向合并：首个单元格 restart，其余 continue。"""
    vmerge = _get_or_add(cell._tc.get_or_add_tcPr(), "w:vMerge", _TCPR_ORDER)
    if restart:
        vmerge.set(qn("w:val"), "restart")
    elif vmerge.get(qn("w:val")) is not None:
        del vmerge.attrib[qn("w:val")]


def set_row_height(row, twips: int) -> None:
    """行高（"至少"语义，与样例一致）。"""
    tr_pr = _get_or_add(row._tr.get_or_add_trPr(), "w:trHeight", _TRPR_ORDER)
    tr_pr.set(qn("w:val"), str(twips))
    if tr_pr.get(qn("w:hRule")) is not None:
        del tr_pr.attrib[qn("w:hRule")]


def write_cell(cell, text, *, bold: bool = False, size=None,
               align=WD_ALIGN_PARAGRAPH.CENTER, multiline: bool = False):
    """向单元格写文本（保持 M0 接口）。

    注意：**默认不设置字号**（``size=None`` = 继承），与样例一致；
    也不写段落间距（样例的单元格段落没有 spacing）。
    """
    spec = Cell(
        text="" if text is None else str(text),
        align="center" if align == WD_ALIGN_PARAGRAPH.CENTER else "left",
        bold=bold,
        size_pt=None if size is None else size.pt,
    )
    _write_cell(cell._tc, spec)
    if multiline:
        return None
    return None


def display_text(value, empty_text: str = None) -> str:
    """空值占位（截面尺寸要求/选填字段为空时显示「无」）。"""
    if value is None:
        return config.EMPTY_TEXT if empty_text is None else empty_text
    text = str(value).strip()
    return text if text else (config.EMPTY_TEXT if empty_text is None else empty_text)
