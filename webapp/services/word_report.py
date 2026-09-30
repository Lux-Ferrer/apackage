# -*- coding: utf-8 -*-
"""Word 报告生成：底座 + 版式规格 + 立柱/横梁表构建 + 项目级报告装配。

版式规格不写死在代码里，而是放在 ``webapp/resources/report_layout.json``：
所有数值实测自对拍基准 ``tests/fixtures/检测表_真实裁剪.docx``
（真实客户报告 A06YG-2026-001 第 12-13 页「表2-4 立柱 / 表2-5 横梁」裁剪而成），
并由 ``tests/test_word_report.py::test_layout_spec_matches_fixture`` 上锁。
该 JSON 语言中立——将来把导出逻辑移植到前端（docx JS）时可直接复用同一份数值。

底座（:func:`new_document`）：
从 ``webapp/resources/report_base.docx`` 继承（由 ``config.FONT_SAMPLE`` 派生，
保留 theme/styles），因此**西文 Times New Roman + 中文主题字体（等线）**不变，
代码里不硬编码任何中文字体名。注意：字体不在"对齐真实报告"的范围内，
真实报告的 docDefaults（SimSun / 10.5pt）**不采纳**。

复刻要点（均为实测自真实报告，容易做错的地方）：
- 表头「厚度检测结果（mm）」横向跨 7 列 → 该行只写 5 个 ``w:tc``；
- 左右页边距 907（比上下 1440 窄），表宽 10833 因此**超出正文区**并居中溢出；
- 外框 sz=12 / 内线 sz=6，颜色 000000；单元格上**不写** ``tcMar``，
  内边距只由表级 ``tblCellMar``（左右 57）与默认值决定；
- 表头**不加粗**；所有单元格**不写** ``w:sz``（继承 Normal = 10pt）；
- 「检测构件\n位置」「尺寸检测结果m×n\n（mm×mm）」是**多段落**，不是自动折行；
- 表头部分单元格带固定行距 ``line=280 atLeast``（第一行前 2 格、第二行前 5 格），
  对视觉无影响，但为逐属性一致而照抄；
- 数据行高按模板不同：立柱 522、横梁 567（表头 567）。
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


def sample_reference_widths(spec=None) -> tuple:
    """由**生效列宽**还原出对拍基准的原始列宽。

    生效列宽里可能含对基准的有意偏离（见 ``columns._widthOverrides``）。测试与对拍工具
    需要"基准侧"的期望值时用本函数，避免在各处重复抄写基准原值。
    当前基准即真实报告，无偏离，故返回生效列宽本身。
    """
    spec = spec or SPEC
    widths = list(spec["columns"]["widths"])
    overrides = spec["columns"].get("_widthOverrides", {})
    for key, override in overrides.items():
        if not isinstance(override, dict):
            continue                                   # 跳过 rule 之类的说明项
        columns = override.get("columns")
        if columns:
            for column in columns:
                widths[column] = override["sampleTwips"]
            continue
        index = spec["columns"]["index"].get(key)
        if index is not None:
            widths[index] = override["sampleTwips"]
    return tuple(widths)


# —— 页面 ——
PAGE_WIDTH_TWIPS = SPEC["page"]["widthTwips"]
PAGE_HEIGHT_TWIPS = SPEC["page"]["heightTwips"]
PAGE_MARGIN_TWIPS = SPEC["page"]["marginTwips"]                  # 上
PAGE_MARGIN_BOTTOM_TWIPS = SPEC["page"].get("marginBottomTwips", PAGE_MARGIN_TWIPS)
PAGE_MARGIN_HORIZONTAL_TWIPS = SPEC["page"].get("marginHorizontalTwips", PAGE_MARGIN_TWIPS)
HEADER_FOOTER_TWIPS = SPEC["page"]["headerFooterTwips"]
FOOTER_TWIPS = SPEC["page"].get("footerTwips", HEADER_FOOTER_TWIPS)
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
BORDER_SIZE = SPEC["table"]["border"].get("outerSz", SPEC["table"]["border"].get("sz", 12))
BORDER_INNER_SIZE = SPEC["table"]["border"].get("innerSz", BORDER_SIZE)
BORDER_COLOR = SPEC["table"]["border"]["color"]

# None = 不写 tcMar（真实表格不在单元格上设内边距）
CELL_MARGIN_VERTICAL = SPEC["cell"]["marginVerticalTwips"]
CELL_MARGIN_HORIZONTAL = SPEC["cell"]["marginHorizontalTwips"]
REQUIREMENT_MARGIN = SPEC["cell"]["requirementMarginTwips"]

# —— 字号（pt）——
INHERITED_TABLE_PT = SPEC["fonts"]["inheritedTablePt"]   # 表格正文继承值，文档用，不写入 XML
REQUIREMENT_PT = SPEC["fonts"]["requirementPt"]          # None = 继承（真实表格不显式设字号）
BODY_PT = SPEC["fonts"]["bodyPt"]
TITLE_PT = SPEC["fonts"]["titlePt"]
TITLE_SIZE = Pt(TITLE_PT)
BODY_SIZE = Pt(BODY_PT)
REQUIREMENT_SIZE = Pt(REQUIREMENT_PT) if REQUIREMENT_PT else None

# —— 段落间距（w:spacing 的单位是 1/20 pt）——
SPACING = SPEC["paragraphSpacing"]

# —— 表头文案（实测自真实报告 表2-4/2-5）——
HEADER_FIXED = tuple(SPEC["headers"]["fixed"])
HEADER_THICKNESS = SPEC["headers"]["thickness"]
HEADER_THICKNESS_SUB = tuple(SPEC["headers"]["thicknessSub"])

# —— 缺陷报告附页（M3）——
# 两列信息表的宽度来自需求报告 4.4；图片压缩参数属渲染参数，导出时现压、不落库
ATTACHMENT_SPEC = SPEC["attachment"]
ATTACHMENT_LABEL_WIDTH = ATTACHMENT_SPEC["labelColumnTwips"]
ATTACHMENT_VALUE_WIDTH = ATTACHMENT_SPEC["valueColumnTwips"]
ATTACHMENT_ROW_TWIPS = ATTACHMENT_SPEC["rowHeightTwips"]
# 96 DPI 下 1 px = 15 twips（用于"不放大原图"的上限）
NATIVE_TWIPS_PER_PIXEL = 1440 / 96

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
    """新建报告文档。

    底座模板提供 theme / styles（字体与默认段落行为）；**页面参数一律由规格覆盖**，
    这样换对拍基准时只改 JSON 即可，不必重新派生底座。
    """
    template = config.REPORT_BASE_TEMPLATE
    if template.exists():
        doc = Document(str(template))
        clear_body(doc)
    else:
        doc = Document()
        apply_default_fonts(doc)
    apply_a4_layout(doc)
    return doc


def apply_a4_layout(doc) -> None:
    """A4 纸张 + 页边距 + docGrid（与对拍基准的 sectPr 一致）。

    四个方向的边距**互不相同**（取自真实报告里含立柱/横梁表的那一节）：
    上 1440、下 1843、左右 907、页眉距离 850、页脚距离 964。
    左右更窄 → 表格（10833）比版心（10093）更宽，向两侧对称溢出，与真实报告一致。
    """
    for section in doc.sections:
        section.page_width = Twips(PAGE_WIDTH_TWIPS)
        section.page_height = Twips(PAGE_HEIGHT_TWIPS)
        section.left_margin = Twips(PAGE_MARGIN_HORIZONTAL_TWIPS)
        section.right_margin = Twips(PAGE_MARGIN_HORIZONTAL_TWIPS)
        section.top_margin = Twips(PAGE_MARGIN_TWIPS)
        section.bottom_margin = Twips(PAGE_MARGIN_BOTTOM_TWIPS)
        section.header_distance = Twips(HEADER_FOOTER_TWIPS)
        section.footer_distance = Twips(FOOTER_TWIPS)
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
                   line: int | None = None, line_rule: str | None = None,
                   with_props: bool = True, page_break_before: bool = False):
    """在 tc / body 内追加一个段落。

    ``container`` 可以是 ``CT_Tc``（单元格）或 ``Document``（正文）。
    ``with_props=False`` 用于纵向合并的 continue 单元格：段落是裸的 ``<w:p/>``。
    ``page_break_before`` 用于附页标题（等价于分页符，但**不产生游离空段**）。
    """
    if hasattr(container, "add_p"):
        paragraph = container.add_p()
    else:                                        # Document → 其 body 就是 CT_Body
        paragraph = container.element.body.add_p()
    if with_props:
        ppr = OxmlElement("w:pPr")
        if page_break_before:
            _insert_ordered(ppr, OxmlElement("w:pageBreakBefore"), _PPR_ORDER)
        if before is not None or after is not None or line is not None:
            spacing = OxmlElement("w:spacing")
            if before is not None:
                spacing.set(qn("w:before"), str(before))
            if after is not None:
                spacing.set(qn("w:after"), str(after))
            if line is not None:
                spacing.set(qn("w:line"), str(line))
                spacing.set(qn("w:lineRule"), line_rule or "atLeast")
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
    line_twips: int | None = None        # 固定行距（客户模板里表头部分格手工设定）


@dataclass
class Row:
    cells: list = field(default_factory=list)
    height: int = DATA_ROW_TWIPS


def continuation_cell(width: int) -> Cell:
    """纵向合并的后续格：**空文本的普通格**。

    真实报告的续行格并非"裸格"——它同样有 ``vAlign=center`` 与居中的空段落，
    只是没有文本、也没有 tcMar 与逐格边框。
    """
    return Cell(text="", width=width, vmerge="continue")


def requirement_cell(text: str, *, vmerge: str | None = None) -> Cell:
    """「截面尺寸要求」列的数据格。

    真实报告里它与普通数据格**完全一致**：不设 tcMar、不显式设字号（继承）。
    保留这个工厂只为可读性与将来可能的差异化。
    """
    return Cell(text=text, width=GRID_COLS[COLUMN_INDEX["requirement"]], vmerge=vmerge)


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
    outer = SPEC["table"]["border"].get("outerSz", SPEC["table"]["border"].get("sz"))
    inner = SPEC["table"]["border"].get("innerSz", outer)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement("w:%s" % edge)
        element.set(qn("w:val"), SPEC["table"]["border"]["val"])
        element.set(qn("w:sz"), str(inner if edge.startswith("inside") else outer))
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
                       align=cell.align, line=cell.line_twips,
                       line_rule=HEADER_LINE_SPACING.get("lineRule"),
                       with_props=not cell.plain)


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
    """表头两行。

    真实表格的表头**不加粗**，部分文案是多段落（见 headers._note），
    且部分单元格被手工设了固定行距（见 cell.headerLineSpacing）。
    """
    requirement_label = config.REQUIREMENT_LABELS[template_type]
    first_specs = (
        (HEADER_FIXED[0], GRID_COLS[0], 1, "restart"),
        (HEADER_FIXED[1], GRID_COLS[1], 1, "restart"),
        (HEADER_FIXED[2], GRID_COLS[2], 1, "restart"),
        (HEADER_THICKNESS, sum(GRID_COLS[THICKNESS_FIRST_COL:THICKNESS_FIRST_COL + THICKNESS_SPAN]),
         THICKNESS_SPAN, None),
        (requirement_label, GRID_COLS[COLUMN_INDEX["requirement"]], 1, "restart"),
    )
    first = [
        Cell(text=text, width=width, span=span, vmerge=vmerge,
             line_twips=_header_line_spacing(0, index))
        for index, (text, width, span, vmerge) in enumerate(first_specs)
    ]

    second_specs = [
        (None, GRID_COLS[0], "continue"),
        (None, GRID_COLS[1], "continue"),
        (None, GRID_COLS[2], "continue"),
    ]
    second_specs += [(label, GRID_COLS[THICKNESS_FIRST_COL + offset], None)
                     for offset, label in enumerate(HEADER_THICKNESS_SUB)]
    second_specs.append((None, GRID_COLS[COLUMN_INDEX["requirement"]], "continue"))

    second = []
    for index, (text, width, vmerge) in enumerate(second_specs):
        line = _header_line_spacing(1, index)
        if vmerge == "continue":
            cell = continuation_cell(width)
            cell.line_twips = line
            second.append(cell)
        else:
            second.append(Cell(text=text, width=width, line_twips=line))

    return [
        Row(cells=first, height=HEADER_ROW_TWIPS),
        Row(cells=second, height=HEADER_ROW_TWIPS),
    ]


def data_row_height(template_type: str) -> int:
    """数据行高：真实报告里立柱表与横梁表不同（见 rows.dataHeightByTemplate）。"""
    return SPEC["rows"].get("dataHeightByTemplate", {}).get(template_type, DATA_ROW_TWIPS)


# —— 表头部分单元格的手工固定行距（客户模板设定，为逐属性一致而照抄）——
HEADER_LINE_SPACING = SPEC["cell"].get("headerLineSpacing") or {}
_HEADER_LINE_KEYS = {0: "row0Cells", 1: "row1Cells"}


def _header_line_spacing(row_index: int, cell_index: int):
    """该表头单元格是否带固定行距；不在配置清单里则返回 None。"""
    configured = HEADER_LINE_SPACING.get(_HEADER_LINE_KEYS.get(row_index, ""), ())
    return HEADER_LINE_SPACING.get("line") if cell_index in configured else None


def _member_rows(item, template_type: str, previous_requirement=None) -> tuple:
    """一个构件 → 每个检测面一行，返回 ``(行列表, 该构件的条文文本)``。

    **两类纵向合并的粒度不同**（实测自真实报告表2-4/2-5）：

    - 楼层 / 检测构件位置 / 尺寸检测结果：**按构件**合并（首行 restart，其余 continue）；
    - 截面尺寸要求：按**连续相同条文**合并 —— 真实报告里 5 个构件共用同一句条文，
      该列被合并成整块（首行 restart、其后全部 continue）；条文不同时自然分段。
      这也与案例 Excel 的 K 列整列合并一致。

    ``previous_requirement`` 是上一个构件的条文，用于判断本构件的首行该 restart 还是 continue。
    """
    record = item["record"]
    faces = item["faces"] or []
    merged = len(faces) > 1
    requirement = record["requirement_text"] or config.EMPTY_TEXT
    requirement_continues = (previous_requirement is not None
                             and previous_requirement == requirement)

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

        if first:
            if requirement_continues:
                # 与上一个构件共用同一条文 → 本格只是合并的续格，**不能带文本**
                cells.append(continuation_cell(GRID_COLS[COLUMN_INDEX["requirement"]]))
            else:
                cells.append(requirement_cell(requirement, vmerge="restart"))
        else:
            cells.append(continuation_cell(GRID_COLS[COLUMN_INDEX["requirement"]]))

        rows.append(Row(cells=cells, height=data_row_height(template_type)))
    return rows, requirement


def build_detection_table(doc, group):
    """一张立柱/横梁检测表（表头 2 行 + 每检测面 1 行）。"""
    template_type = group["template_type"]
    rows = _header_rows(template_type)
    previous_requirement = None
    for item in group["records"]:
        member_rows, previous_requirement = _member_rows(item, template_type,
                                                         previous_requirement)
        rows.extend(member_rows)
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


def build_project_report(project, groups, attachments=None):
    """装配完整报告：信息段 → （章节标题 + 表 + 空段）×N → 备注 → 附页×N → 文末空段。

    只输出有记录的章节（立柱 / 横梁各自判断）；不输出玻璃模块。
    ``attachments`` 为空时产出与 M2 **完全一致**（文末空段的位置对无附页路径是恒等变换）。
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

    attachments = list(attachments or [])
    for index, view in enumerate(attachments, start=1):
        build_attachment(doc, view, index, len(attachments))

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
# 缺陷报告附页（M3）
# --------------------------------------------------------------------------
def fit_image_twips(width_px: int, height_px: int, spec=None):
    """像素尺寸 → 嵌入用的 twips：适配附页的最大宽/高，且**不放大**。

    上限取 ``min(最大宽/像素宽, 最大高/像素高, 1px=15twips)`` ——
    最后一项保证小图不会被拉伸到超过其 96 DPI 的自然尺寸。
    """
    spec = spec or ATTACHMENT_SPEC
    if width_px <= 0 or height_px <= 0:
        return 0, 0
    scale = min(spec["imageMaxWidthTwips"] / width_px,
                spec["imageMaxHeightTwips"] / height_px,
                NATIVE_TWIPS_PER_PIXEL)
    return int(round(width_px * scale)), int(round(height_px * scale))


def add_picture_paragraph(doc, image_path, width_twips: int, height_twips: int):
    """居中插入一张图片（尺寸由 :func:`fit_image_twips` 算好）。"""
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    run.add_picture(str(image_path), width=Twips(int(width_twips)), height=Twips(int(height_twips)))
    return paragraph


def attachment_rows(view, values):
    """附页的两列信息表：标签列加粗居中、内容列左对齐（需求报告 4.4）。"""
    rows = []
    for key in config.ATTACHMENT_ORDER:
        rows.append(Row(cells=[
            Cell(text=config.ATTACHMENT_LABELS[key], width=ATTACHMENT_LABEL_WIDTH, bold=True),
            Cell(text=values[key], width=ATTACHMENT_VALUE_WIDTH, align="left"),
        ], height=ATTACHMENT_ROW_TWIPS))
    return rows


def build_attachment(doc, view, index: int, total: int):
    """一份检测报告附页：标题（前加分页）→ 两列信息表 → 隐患图片。"""
    _add_paragraph(doc, config.ATTACHMENT_TITLE.format(index=index, total=total),
                   bold=True, size_pt=TITLE_PT, align="center",
                   before=SPACING["titleBefore"], after=SPACING["titleAfter"],
                   page_break_before=True)

    from . import defects as defect_service          # 延迟导入，避免服务层循环依赖
    build_table(doc, attachment_rows(view, defect_service.field_values(view)),
                widths=(ATTACHMENT_LABEL_WIDTH, ATTACHMENT_VALUE_WIDTH))

    if view.get("image_path"):
        _add_paragraph(doc, ATTACHMENT_SPEC["imageLabel"], align="left",
                       size_pt=BODY_PT, before=SPACING["titleBefore"],
                       after=SPACING["titleAfter"])
        add_picture_paragraph(doc, view["image_path"],
                              view.get("image_width_twips", 0), view.get("image_height_twips", 0))
    elif view.get("original_name"):
        # 降级：图片读不出来也要把附页导出去
        _add_paragraph(doc, "（图片缺失：%s）" % view["original_name"],
                       align="left", size_pt=BODY_PT, before=SPACING["titleBefore"])
    return doc


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
    """建一张普通表格（等宽或指定列宽），供旧调用与测试使用。

    与导出主路径一致：**不写单元格 tcMar**（内边距由表级 tblCellMar 决定）。
    """
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


def set_cell_margins(cell, top=60, left=80, bottom=60, right=80) -> None:
    """显式设置单元格内边距（导出主路径不用它，仅为旧接口保留）。"""
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
