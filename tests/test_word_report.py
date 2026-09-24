# -*- coding: utf-8 -*-
"""Word 底座测试：A4 页面、字体沿用样例、表格原语、与样例页面参数对齐。"""

from __future__ import annotations

import zipfile

import pytest
from docx import Document
from docx.oxml.ns import qn
from docx.table import _Cell
from lxml import etree

from webapp import config
from webapp.services import word_report as wr

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


# --------------------------------------------------------------------------
# 底座
# --------------------------------------------------------------------------
def test_report_base_template_present():
    assert config.REPORT_BASE_TEMPLATE.exists(), (
        "缺少报告底座模板，请先运行：python tools/make_report_template.py"
    )


def test_new_document_is_a4():
    section = wr.new_document().sections[0]
    assert section.page_width.twips == wr.PAGE_WIDTH_TWIPS == 11906
    assert section.page_height.twips == wr.PAGE_HEIGHT_TWIPS == 16838
    assert section.left_margin.twips == wr.PAGE_MARGIN_TWIPS
    assert section.right_margin.twips == wr.PAGE_MARGIN_TWIPS
    assert section.top_margin.twips == wr.PAGE_MARGIN_TWIPS
    assert section.bottom_margin.twips == wr.PAGE_MARGIN_TWIPS


def test_page_setup_matches_sample():
    """生成的文档与样例的 pgSz / pgMar 必须逐项一致。"""
    sample = _section_props(config.GOLDEN_SAMPLE)
    generated_doc = wr.new_document()
    generated = _section_props_from_element(
        generated_doc.sections[0]._sectPr
    )
    assert generated["pgSz"] == sample["pgSz"]
    assert generated["pgMar"] == sample["pgMar"]


def test_default_fonts_follow_sample():
    rfonts = _doc_default_rfonts(wr.new_document())
    assert rfonts.get(qn("w:ascii")) == "Times New Roman"
    assert rfonts.get(qn("w:hAnsi")) == "Times New Roman"
    assert rfonts.get(qn("w:cs")) == "Times New Roman"
    assert rfonts.get(qn("w:eastAsiaTheme")) == "minorEastAsia"
    # 关键：不硬编码中文字体，交给主题
    assert rfonts.get(qn("w:eastAsia")) is None


def test_theme_inherits_sample_cjk_font(tmp_path):
    """底座派生自样例，主题中文字体应是样例的「等线」，而不是 python-docx 默认的「宋体」。"""
    path = tmp_path / "theme.docx"
    wr.new_document().save(str(path))
    theme = etree.fromstring(zipfile.ZipFile(path).read("word/theme/theme1.xml"))
    scheme = theme.find(A + "themeElements").find(A + "fontScheme")
    minor = scheme.find(A + "minorFont")
    hans = {f.get("script"): f.get("typeface") for f in minor.findall(A + "font")}
    assert hans.get("Hans") == "等线"


def test_write_cell_does_not_hardcode_cjk_font():
    doc = wr.new_document()
    table = wr.create_table(doc, 1, 1)
    wr.write_cell(table.cell(0, 0), "幕墙立柱截面尺寸检测结果")
    run = table.cell(0, 0).paragraphs[0].runs[0]
    rfonts = run._element.rPr.rFonts if run._element.rPr is not None else None
    assert rfonts is None or rfonts.get(qn("w:eastAsia")) is None


# --------------------------------------------------------------------------
# 表格原语
# --------------------------------------------------------------------------
def test_grid_cols_measured_from_sample():
    assert len(wr.GRID_COLS) == 11
    assert sum(wr.GRID_COLS) == wr.TABLE_WIDTH_TWIPS == 8800
    # "厚度检测结果 (mm)" 横跨 面 + 1..5 + 最小 共 7 列，其后仅剩"截面尺寸要求"一列
    assert wr.THICKNESS_FIRST_COL == 3
    assert wr.THICKNESS_SPAN == 7
    assert wr.THICKNESS_FIRST_COL + wr.THICKNESS_SPAN == len(wr.GRID_COLS) - 1
    assert wr.GRID_COLS[-1] == 2101          # 截面尺寸要求列


def test_create_table_grid_and_width():
    doc = wr.new_document()
    table = wr.create_table(doc, 2, 2, widths=(wr.INFO_LABEL_WIDTH, wr.INFO_VALUE_WIDTH))
    cols = [int(g.get(qn("w:w"))) for g in table._tbl.find(qn("w:tblGrid")).findall(qn("w:gridCol"))]
    assert cols == [1600, 7200]

    tblPr = table._tbl.tblPr
    assert int(tblPr.find(qn("w:tblW")).get(qn("w:w"))) == 8800
    assert tblPr.find(qn("w:tblW")).get(qn("w:type")) == "dxa"
    assert tblPr.find(qn("w:tblLayout")).get(qn("w:type")) == "fixed"


def test_table_borders_match_sample():
    doc = wr.new_document()
    table = wr.create_table(doc, 1, 1)
    borders = table._tbl.tblPr.find(qn("w:tblBorders"))
    assert borders is not None
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = borders.find(qn("w:%s" % edge))
        assert element.get(qn("w:val")) == "single"
        assert element.get(qn("w:sz")) == "4"


def test_table_children_order_is_schema_valid():
    """tblBorders 必须在 tblLayout 之前，否则 Word 可能报文档损坏。"""
    doc = wr.new_document()
    table = wr.create_table(doc, 1, 1)
    tags = [etree.QName(child).localname for child in table._tbl.tblPr]
    assert tags.index("tblBorders") < tags.index("tblLayout")
    assert tags.index("tblW") < tags.index("tblBorders")


def test_cell_margins_match_sample():
    doc = wr.new_document()
    table = wr.create_table(doc, 1, 1)
    tcMar = table.cell(0, 0)._tc.tcPr.find(qn("w:tcMar"))
    assert tcMar.find(qn("w:top")).get(qn("w:w")) == "60"
    assert tcMar.find(qn("w:bottom")).get(qn("w:w")) == "60"
    assert tcMar.find(qn("w:left")).get(qn("w:w")) == "80"
    assert tcMar.find(qn("w:right")).get(qn("w:w")) == "80"


def test_vertical_merge_restart_and_continue():
    """多面构件四列纵向合并所需：首格 restart、后续 continue。

    注意：python-docx 的 ``table.cell(r, c)`` 会把 continue 行的单元格解析回
    合并起始格，所以这里直接对底层的 ``w:tc`` 元素断言。
    """
    doc = wr.new_document()
    table = wr.create_table(doc, 3, 1)
    tcs = [row._tr.findall(qn("w:tc"))[0] for row in table.rows]

    for index, tc in enumerate(tcs):
        wr.set_vertical_merge(_Cell(tc, table), restart=(index == 0))

    assert tcs[0].tcPr.find(qn("w:vMerge")).get(qn("w:val")) == "restart"
    for index in (1, 2):
        vmerge = tcs[index].tcPr.find(qn("w:vMerge"))
        assert vmerge is not None and vmerge.get(qn("w:val")) is None


def test_row_height_is_at_least_semantics():
    doc = wr.new_document()
    table = wr.create_table(doc, 2, 1)
    wr.set_row_height(table.rows[0], wr.HEADER_ROW_TWIPS)
    wr.set_row_height(table.rows[1], wr.DATA_ROW_TWIPS)
    first = table.rows[0]._tr.trPr.find(qn("w:trHeight"))
    second = table.rows[1]._tr.trPr.find(qn("w:trHeight"))
    assert first.get(qn("w:val")) == "600"
    assert second.get(qn("w:val")) == "400"
    assert first.get(qn("w:hRule")) is None      # 不写 hRule = "至少"，与样例一致


def test_write_cell_is_centered_and_sized():
    doc = wr.new_document()
    table = wr.create_table(doc, 1, 1)
    wr.write_cell(table.cell(0, 0), "楼层", bold=True)
    cell = table.cell(0, 0)
    paragraph = cell.paragraphs[0]
    assert paragraph.alignment == 1                              # CENTER
    assert cell._tc.tcPr.find(qn("w:vAlign")).get(qn("w:val")) == "center"
    run = paragraph.runs[0]
    assert run.bold is True
    assert run.font.size.pt == 11


def test_write_cell_multiline_creates_paragraphs():
    doc = wr.new_document()
    table = wr.create_table(doc, 1, 1)
    wr.write_cell(table.cell(0, 0), "第一行\n第二行", multiline=True)
    paragraphs = table.cell(0, 0).paragraphs
    assert len(paragraphs) == 2
    assert paragraphs[0].text == "第一行"
    assert paragraphs[1].text == "第二行"


def test_create_table_rejects_mismatched_widths():
    doc = wr.new_document()
    with pytest.raises(ValueError):
        wr.create_table(doc, 1, 3, widths=(1600, 7200))


def test_display_text_uses_placeholder():
    assert wr.display_text(None) == "无"
    assert wr.display_text("   ") == "无"
    assert wr.display_text("立柱铝型材开口部位…") == "立柱铝型材开口部位…"


# --------------------------------------------------------------------------
# 文档级
# --------------------------------------------------------------------------
def test_document_round_trip(tmp_path):
    doc = wr.new_document()
    wr.add_title(doc, "幕墙立柱截面尺寸检测结果")
    table = wr.create_table(doc, 1, 11)
    wr.write_cell(table.cell(0, 0), "楼层")

    path = tmp_path / "report.docx"
    wr.save(doc, path)

    reopened = Document(str(path))
    assert len(reopened.tables) == 1
    assert len(reopened.tables[0].columns) == 11
    assert reopened.tables[0].cell(0, 0).text == "楼层"
    assert reopened.sections[0].page_width.twips == 11906


def test_clear_body_keeps_section_setup():
    doc = wr.new_document()
    doc.add_paragraph("临时内容")
    wr.clear_body(doc)
    assert [p.text for p in doc.paragraphs] == []
    assert doc.sections[0].page_width.twips == 11906


def test_build_defect_draft_contains_fields():
    defect = {
        "id": 7,
        "defect_type": "密封胶开裂",
        "project_part": "东立面三层 1# 立柱",
        "risk_level": "中",
        "rectification_plan": "第一行：更换密封胶。\n第二行：复检确认无渗漏。",
        "created_at": "2026-09-22 10:00:00",
    }
    doc = wr.build_defect_draft(defect)

    texts = [p.text for p in doc.paragraphs]
    assert any("缺陷检测报告" in t for t in texts)
    assert doc.sections[0].page_width.twips == 11906

    cells = [c.text for table in doc.tables for row in table.rows for c in row.cells]
    assert "密封胶开裂" in cells
    assert "东立面三层 1# 立柱" in cells
    assert any("更换密封胶" in c for c in cells)


# --------------------------------------------------------------------------
# 辅助
# --------------------------------------------------------------------------
def _doc_default_rfonts(doc):
    rpr = (doc.styles.element.find(qn("w:docDefaults"))
           .find(qn("w:rPrDefault")).find(qn("w:rPr")))
    return rpr.find(qn("w:rFonts"))


def _section_props(path):
    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    return _section_props_from_element(root.find(W + "body").find(W + "sectPr"))


def _section_props_from_element(sectPr):
    pg_sz = sectPr.find(W + "pgSz")
    pg_mar = sectPr.find(W + "pgMar")
    return {
        "pgSz": (pg_sz.get(W + "w"), pg_sz.get(W + "h")),
        "pgMar": tuple(pg_mar.get(W + k) for k in
                       ("top", "right", "bottom", "left", "header", "footer", "gutter")),
    }
