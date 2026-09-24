# -*- coding: utf-8 -*-
"""Word 报告底座。

M0 只交付两件事：

1. :func:`new_document` —— 报告底座。
   优先从 ``webapp/resources/report_base.docx`` 继承（该文件由样例派生，
   保留了样例的 ``theme1.xml`` / ``styles.xml`` / ``sectPr``），
   因此 A4 纸张、页边距、**Times New Roman + 主题中文字体** 与样例完全一致，
   而不是在代码里硬写中文字体名。
   底座缺失时退化为"新建文档 + 按样例参数手工设置"。

2. 表格原语 —— 固定列宽、边框、单元格边距、垂直合并、行高、居中写入。
   立柱/横梁表（表头跨列合并、多面构件的四列纵向合并）在 M2 用这些原语拼装。

版式常量全部实测自对拍基准 ``tests/fixtures/金骐智谷_金骐_检测报告.docx``。
"""

from __future__ import annotations

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Twips
from docx.text.paragraph import Paragraph
from lxml import etree

from .. import config

# --------------------------------------------------------------------------
# 页面参数（实测自样例 sectPr）
# --------------------------------------------------------------------------
PAGE_WIDTH_TWIPS = 11906          # A4 宽
PAGE_HEIGHT_TWIPS = 16838         # A4 高
PAGE_MARGIN_TWIPS = 1440
HEADER_FOOTER_TWIPS = 708
DOC_GRID_LINE_PITCH = 360

# --------------------------------------------------------------------------
# 立柱/横梁表参数（实测自样例 tblGrid / trPr / tcMar）
# --------------------------------------------------------------------------
TABLE_WIDTH_TWIPS = 8800
# 楼层 / 构件位置 / 尺寸结果 / 面 / 1 / 2 / 3 / 4 / 5 / 最小 / 截面尺寸要求
GRID_COLS = (492, 553, 614, 480, 760, 760, 760, 760, 760, 760, 2101)
THICKNESS_FIRST_COL = 3           # "面"所在列下标
THICKNESS_SPAN = 7                # 表头"厚度检测结果 (mm)"横向合并的列数
HEADER_ROW_TWIPS = 600
DATA_ROW_TWIPS = 400
CELL_MARGIN_VERTICAL = 60
CELL_MARGIN_HORIZONTAL = 80
BORDER_SIZE = 4                   # single, 0.5pt
BORDER_COLOR = "auto"

# 二列信息表（附页用，需求报告 4.4）
INFO_LABEL_WIDTH = 1600
INFO_VALUE_WIDTH = TABLE_WIDTH_TWIPS - INFO_LABEL_WIDTH

# --------------------------------------------------------------------------
# 字号（实测自样例正文：信息段/备注 11pt，章节标题 16pt）
# --------------------------------------------------------------------------
TITLE_SIZE = Pt(16)
BODY_SIZE = Pt(11)

ASCII_FONT = "Times New Roman"

# --------------------------------------------------------------------------
# OOXML 子元素顺序表（顺序不符合 schema 时 Word 可能报文档损坏）
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

    # 兜底：底座模板缺失时，按样例实测参数手工设置
    doc = Document()
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
        grid = _get_or_add(section._sectPr, "w:docGrid", (
            "footnotePr", "endnotePr", "type", "pgSz", "pgMar", "paperSrc",
            "pgBorders", "lnNumType", "pgNumType", "cols", "formProt",
            "vAlign", "noEndnote", "titlePg", "textDirection", "bidi",
            "rtlGutter", "docGrid", "printerSettings",
        ))
        grid.set(qn("w:linePitch"), str(DOC_GRID_LINE_PITCH))


def apply_default_fonts(doc) -> None:
    """西文 Times New Roman + 中文走主题字体。

    与样例 ``docDefaults`` 完全一致：``eastAsiaTheme="minorEastAsia"``，
    不写死 ``w:eastAsia``，中文由主题字体（样例为"等线"）决定。
    """
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
# 段落
# --------------------------------------------------------------------------
def _zero_spacing(paragraph) -> None:
    """样例正文无段前段后间距（docDefaults/pPrDefault 为空）。"""
    spacing = _get_or_add(paragraph._p.get_or_add_pPr(), "w:spacing", _PPR_ORDER)
    spacing.set(qn("w:before"), "0")
    spacing.set(qn("w:after"), "0")


def add_title(doc, text: str):
    """章节标题：居中加粗 16pt（样例实测）。"""
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _zero_spacing(paragraph)
    run = paragraph.add_run(text)
    run.bold = True
    run.font.size = TITLE_SIZE
    return paragraph


def add_body_paragraph(doc, text: str, *, bold: bool = False):
    """正文段落：11pt（样例的项目信息段为加粗 11pt，备注为常规 11pt）。"""
    paragraph = doc.add_paragraph()
    _zero_spacing(paragraph)
    run = paragraph.add_run("" if text is None else str(text))
    run.bold = bold
    run.font.size = BODY_SIZE
    return paragraph


def add_page_break(doc):
    """插入分页符（附页每份独立成页）。"""
    return doc.add_page_break()


# --------------------------------------------------------------------------
# 表格原语
# --------------------------------------------------------------------------
def create_table(doc, rows: int, cols: int, widths=None):
    """新建表格：固定布局、样例列宽、样例边框、样例单元格边距。

    ``widths`` 省略时按总宽平均分配；立柱/横梁表请显式传入 :data:`GRID_COLS`。
    """
    widths = tuple(widths) if widths is not None else even_widths(cols)
    if len(widths) != cols:
        raise ValueError("列宽数量(%d)与列数(%d)不一致" % (len(widths), cols))
    table = doc.add_table(rows=rows, cols=cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    apply_table_grid(table, widths)
    apply_table_borders(table)
    for row in table.rows:
        for cell in row.cells:
            set_cell_margins(cell)
    return table


def even_widths(cols: int, total: int = TABLE_WIDTH_TWIPS):
    """把总宽平均分配给 cols 列（余数给最后一列）。"""
    base, remainder = divmod(total, cols)
    widths = [base] * cols
    widths[-1] += remainder
    return tuple(widths)


def apply_table_grid(table, widths=GRID_COLS) -> None:
    """表总宽 + 固定布局 + tblGrid 列宽。"""
    tbl = table._tbl
    tblPr = tbl.tblPr

    tblW = _get_or_add(tblPr, "w:tblW", _TBLPR_ORDER)
    tblW.set(qn("w:w"), str(sum(widths)))
    tblW.set(qn("w:type"), "dxa")

    layout = _get_or_add(tblPr, "w:tblLayout", _TBLPR_ORDER)
    layout.set(qn("w:type"), "fixed")

    old_grid = tbl.find(qn("w:tblGrid"))
    if old_grid is not None:
        tbl.remove(old_grid)
    grid = OxmlElement("w:tblGrid")
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)
    tblPr.addnext(grid)                     # tblGrid 必须紧跟 tblPr


def apply_table_borders(table, size: int = BORDER_SIZE, color: str = BORDER_COLOR) -> None:
    """全边框（含内部横竖线），样例为 single / sz=4 / auto。"""
    tblPr = table._tbl.tblPr
    old = tblPr.find(qn("w:tblBorders"))
    if old is not None:
        tblPr.remove(old)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement("w:%s" % edge)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), str(size))
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)
        borders.append(element)
    _insert_ordered(tblPr, borders, _TBLPR_ORDER)


def set_cell_margins(cell, top=CELL_MARGIN_VERTICAL, left=CELL_MARGIN_HORIZONTAL,
                     bottom=CELL_MARGIN_VERTICAL, right=CELL_MARGIN_HORIZONTAL) -> None:
    """单元格内边距（样例：上下 60、左右 80 twips）。"""
    tcMar = _get_or_add(cell._tc.get_or_add_tcPr(), "w:tcMar", _TCPR_ORDER)
    for tag, value in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        element = tcMar.find(qn("w:%s" % tag))
        if element is None:
            element = OxmlElement("w:%s" % tag)
            tcMar.append(element)
        element.set(qn("w:w"), str(value))
        element.set(qn("w:type"), "dxa")


def set_cell_width(cell, twips: int) -> None:
    tcW = _get_or_add(cell._tc.get_or_add_tcPr(), "w:tcW", _TCPR_ORDER)
    tcW.set(qn("w:w"), str(twips))
    tcW.set(qn("w:type"), "dxa")


def set_cell_valign(cell, value: str = "center") -> None:
    vAlign = _get_or_add(cell._tc.get_or_add_tcPr(), "w:vAlign", _TCPR_ORDER)
    vAlign.set(qn("w:val"), value)


def set_vertical_merge(cell, restart: bool = True) -> None:
    """纵向合并：首个单元格 restart，其余 continue。

    立柱一个构件有多个检测面时，用它对"楼层/构件位置/尺寸结果/截面尺寸要求"
    四列做纵向合并（已确认需求）。
    """
    vMerge = _get_or_add(cell._tc.get_or_add_tcPr(), "w:vMerge", _TCPR_ORDER)
    if restart:
        vMerge.set(qn("w:val"), "restart")
    elif vMerge.get(qn("w:val")) is not None:
        del vMerge.attrib[qn("w:val")]


def set_row_height(row, twips: int) -> None:
    """行高（"至少"语义，内容多时自动撑高，与样例一致）。"""
    trPr = _get_or_add(row._tr.get_or_add_trPr(), "w:trHeight", _TRPR_ORDER)
    trPr.set(qn("w:val"), str(twips))
    if trPr.get(qn("w:hRule")) is not None:
        del trPr.attrib[qn("w:hRule")]


def write_cell(cell, text, *, bold: bool = False, size=BODY_SIZE,
               align=WD_ALIGN_PARAGRAPH.CENTER, multiline: bool = False):
    """向单元格写文本：居中 + 垂直居中，字号显式指定，字体继承文档默认。

    注意：这里**不设置**字体名，西文由 docDefaults 的 Times New Roman 生效、
    中文由主题字体生效——这正是"沿用样例字体"的做法。
    """
    tc = cell._tc
    tc.clear_content()                      # 清空单元格（含默认空段落与空 run）
    lines = str(text).splitlines() if (multiline and text is not None) else [text]
    if not lines:
        lines = [""]
    first = None
    for line in lines:
        paragraph = Paragraph(tc.add_p(), cell)
        if first is None:
            first = paragraph
        _zero_spacing(paragraph)
        paragraph.alignment = align
        run = paragraph.add_run("" if line is None else str(line))
        run.bold = bold
        if size is not None:
            run.font.size = size
    set_cell_valign(cell)
    return first


def display_text(value, empty_text: str = None) -> str:
    """空值占位（截面尺寸要求/选填字段为空时显示"无"）。"""
    if value is None:
        return config.EMPTY_TEXT if empty_text is None else empty_text
    text = str(value).strip()
    return text if text else (config.EMPTY_TEXT if empty_text is None else empty_text)


# --------------------------------------------------------------------------
# M0 临时导出：单条缺陷记录（M3 会按需求报告 4.4 换成"检测报告附页"格式）
# --------------------------------------------------------------------------
def build_defect_draft(defect) -> object:
    """把一条缺陷记录输出成 A4 文档（PoC 导出能力的迁移版）。

    仅把纸张从 Letter 换成样例的 A4 底座；字段集合与排版在 M3 按附页规范重做。
    """
    doc = new_document()
    add_title(doc, "缺陷检测报告（临时版）")

    rows = (
        ("报告编号", "#%s" % defect["id"]),
        ("缺陷类型", defect["defect_type"]),
        ("工程部位", defect["project_part"]),
        ("隐患等级", defect["risk_level"]),
        ("整改方案", defect["rectification_plan"]),
        ("提交时间", defect["created_at"]),
    )
    table = create_table(doc, len(rows), 2,
                         widths=(INFO_LABEL_WIDTH, INFO_VALUE_WIDTH))
    for index, (label, value) in enumerate(rows):
        label_cell, value_cell = table.rows[index].cells
        set_row_height(table.rows[index], DATA_ROW_TWIPS)
        write_cell(label_cell, label, bold=True)
        write_cell(value_cell, value, align=WD_ALIGN_PARAGRAPH.LEFT, multiline=True)
    return doc


def save(doc, path) -> str:
    """保存文档，返回路径字符串。"""
    path = str(path)
    doc.save(path)
    return path
