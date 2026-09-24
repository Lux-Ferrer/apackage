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

SPEC = wr.SPEC
SPACING = wr.SPACING

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


def test_write_cell_is_centered_and_inherits_size_by_default():
    """样例的表格单元格**不写字号**（继承），所以默认 size=None 才是正确行为。"""
    doc = wr.new_document()
    table = wr.create_table(doc, 1, 1)
    wr.write_cell(table.cell(0, 0), "楼层", bold=True)
    cell = table.cell(0, 0)
    paragraph = cell.paragraphs[0]
    assert paragraph.alignment == 1                              # CENTER
    assert cell._tc.tcPr.find(qn("w:vAlign")).get(qn("w:val")) == "center"
    run = paragraph.runs[0]
    assert run.bold is True
    assert run.font.size is None                                 # 不写 w:sz → 继承


def test_write_cell_sets_size_when_explicitly_asked():
    doc = wr.new_document()
    table = wr.create_table(doc, 1, 1)
    wr.write_cell(table.cell(0, 0), "2.99", size=wr.BODY_SIZE)
    assert table.cell(0, 0).paragraphs[0].runs[0].font.size.pt == 11


def test_write_cell_multiline_creates_paragraphs():
    doc = wr.new_document()
    table = wr.create_table(doc, 1, 1)
    wr.write_cell(table.cell(0, 0), "第一行\n第二行", multiline=True)
    paragraphs = table.cell(0, 0).paragraphs
    assert len(paragraphs) == 2
    assert paragraphs[0].text == "第一行"
    assert paragraphs[1].text == "第二行"


# --------------------------------------------------------------------------
# 版式规格与样例的锁定关系
# --------------------------------------------------------------------------
def _sample_body():
    with zipfile.ZipFile(config.GOLDEN_SAMPLE) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    return root.find(W + "body")


def sample_column_widths():
    """样例的**原始**列宽（由生效列宽按 columns._widthOverrides 还原）。"""
    return wr.sample_reference_widths()


def _text(element):
    return "".join(node.text or "" for node in element.iter(W + "t"))


def test_layout_spec_matches_sample():
    """`report_layout.json` 的每个常量都必须等于样例实测值 —— 改错这里立刻红。"""
    body = _sample_body()
    sample_widths = sample_column_widths()
    tbl = body.findall(W + "tbl")[0]
    tbl_pr = tbl.find(W + "tblPr")
    rows = tbl.findall(W + "tr")

    # 表格级
    assert int(tbl_pr.find(W + "tblW").get(W + "w")) == wr.TABLE_WIDTH_TWIPS == 8800
    assert tbl_pr.find(W + "tblW").get(W + "type") == "dxa"
    assert tbl_pr.find(W + "jc").get(W + "val") == SPEC["table"]["align"]
    assert tbl_pr.find(W + "tblLayout").get(W + "type") == SPEC["table"]["layout"]
    col_widths = [int(g.get(W + "w")) for g in tbl.find(W + "tblGrid").findall(W + "gridCol")]
    assert col_widths == list(sample_column_widths())
    assert sum(col_widths) == wr.TABLE_WIDTH_TWIPS == 8800
    assert sum(wr.GRID_COLS) == wr.TABLE_WIDTH_TWIPS          # 生效列宽同样守恒

    borders = tbl_pr.find(W + "tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = borders.find(W + edge)
        assert element.get(W + "val") == SPEC["table"]["border"]["val"]
        assert int(element.get(W + "sz")) == SPEC["table"]["border"]["sz"]
    cell_margin = tbl_pr.find(W + "tblCellMar")
    assert int(cell_margin.find(W + "left").get(W + "w")) == SPEC["table"]["tableCellMargin"]["left"]
    assert int(cell_margin.find(W + "right").get(W + "w")) == SPEC["table"]["tableCellMargin"]["right"]
    look = tbl_pr.find(W + "tblLook")
    for key, value in SPEC["table"]["look"].items():
        assert look.get(W + key) == str(value), key

    # 行高（表头 600 / 数据 400，且不写 hRule）
    for tr in rows[:2]:
        height = tr.find(W + "trPr").find(W + "trHeight")
        assert int(height.get(W + "val")) == wr.HEADER_ROW_TWIPS
        assert height.get(W + "hRule") is None
    data_height = rows[2].find(W + "trPr").find(W + "trHeight")
    assert int(data_height.get(W + "val")) == wr.DATA_ROW_TWIPS

    # 表头文案（含样例里的空格写法）与跨列
    header0 = rows[0].findall(W + "tc")
    assert _text(header0[0]) == SPEC["headers"]["fixed"][0]
    assert _text(header0[1]) == SPEC["headers"]["fixed"][1]
    assert _text(header0[2]) == SPEC["headers"]["fixed"][2]
    assert _text(header0[3]) == SPEC["headers"]["thickness"]
    assert int(header0[3].find(W + "tcPr").find(W + "gridSpan").get(W + "val")) == wr.THICKNESS_SPAN
    assert [int(tc.find(W + "tcPr").find(W + "tcW").get(W + "w")) for tc in header0] == [
        sample_widths[0], sample_widths[1], sample_widths[2],
        sum(sample_widths[3:10]), sample_widths[10],
    ]
    sub = [_text(tc) for tc in rows[1].findall(W + "tc")[3:10]]
    assert sub == list(SPEC["headers"]["thicknessSub"])

    # 单元格边距：普通格 60/80，要求列数据格 60/60
    normal_mar = header0[0].find(W + "tcPr").find(W + "tcMar")
    assert int(normal_mar.find(W + "top").get(W + "w")) == wr.CELL_MARGIN_VERTICAL
    assert int(normal_mar.find(W + "left").get(W + "w")) == wr.CELL_MARGIN_HORIZONTAL
    requirement_cell = rows[2].findall(W + "tc")[wr.COLUMN_INDEX["requirement"]]
    requirement_mar = requirement_cell.find(W + "tcPr").find(W + "tcMar")
    for side in ("top", "left", "bottom", "right"):
        assert int(requirement_mar.find(W + side).get(W + "w")) == wr.REQUIREMENT_MARGIN

    # 「截面尺寸要求」数据格显式 8pt（为长条文挤空间）
    size = (requirement_cell.find(W + "p").find(W + "r")
            .find(W + "rPr").find(W + "sz"))
    assert int(size.get(W + "val")) == int(wr.REQUIREMENT_PT * 2) == 16

    # 正文段落：字号与间距
    paragraphs = body.findall(W + "p")

    def run_size(paragraph):
        return int(paragraph.find(W + "r").find(W + "rPr").find(W + "sz").get(W + "val"))

    def spacing(paragraph):
        element = paragraph.find(W + "pPr").find(W + "spacing")
        return element.attrib if element is not None else {}

    def attr(element, name):
        return element.get(W + name)

    assert run_size(paragraphs[0]) == int(wr.BODY_PT * 2) == 22
    assert attr(spacing(paragraphs[0]), "after") == str(SPACING["infoAfter"])
    assert run_size(paragraphs[5]) == int(wr.TITLE_PT * 2) == 32
    assert attr(spacing(paragraphs[5]), "before") == str(SPACING["titleBefore"])
    assert attr(spacing(paragraphs[5]), "after") == str(SPACING["titleAfter"])

    # note: findall(p) 不含表格，所以下标与 body 子元素下标不同：
    # 0-4 信息段 / 5 立柱标题 / 6 空段 / 7 横梁标题 / 8 空段 / 9 玻璃标题 / 10 空段 / 11 备注 / 12 文末空段
    assert len(paragraphs) == 13
    assert _text(paragraphs[5]) == "幕墙立柱截面尺寸检测结果"
    assert _text(paragraphs[7]) == "幕墙横梁截面尺寸检测结果"
    for index in (6, 8, 10):
        assert _text(paragraphs[index]) == ""
        assert attr(spacing(paragraphs[index]), "before") == str(SPACING["spacerBefore"])
        assert attr(spacing(paragraphs[index]), "after") == str(SPACING["spacerAfter"])

    note = paragraphs[11]
    assert _text(note).startswith("备注：")
    assert run_size(note) == int(wr.BODY_PT * 2)
    assert attr(spacing(note), "before") == str(SPACING["noteBefore"])
    assert _text(paragraphs[12]) == ""                       # 文末空段


def test_layout_spec_file_is_language_neutral():
    """规格放在 JSON 里（而非代码），便于将来移植到前端 docx JS。"""
    assert wr.SPEC_PATH.exists()
    spec = wr.load_spec()
    assert spec["columns"]["widths"] == list(wr.GRID_COLS)
    assert spec["fonts"]["inheritedTablePt"] == 10      # Word 未指定时的继承字号（已人工核对）
    assert spec["fonts"]["requirementPt"] == 8


def test_floor_column_fits_four_chinese_characters():
    """楼层列按「4 个汉字 + 20% 余量」设定（2026-09-24 决定）。

    样例的 492 twips 连案例里的「二十三层」都放不下（实测 800 twips、折 3 行）。
    """
    cjk_twips = wr.INHERITED_TABLE_PT * 20               # 10pt 下 1 个汉字 = 200 twips
    usable = wr.GRID_COLS[wr.COLUMN_INDEX["floor"]] - 2 * wr.CELL_MARGIN_HORIZONTAL
    assert usable >= 4 * cjk_twips                       # 装得下 4 个汉字
    assert usable - 4 * cjk_twips == cjk_twips * 0.2     # 并留 20% 一个汉字的余量（40 twips）

    from tools.analyze_text_fit import make_measurer     # 用真实字体验证，而非只比算式
    assert make_measurer()("二十三层", wr.INHERITED_TABLE_PT) <= usable


def test_width_overrides_are_declared_with_sample_values():
    """对样例的列宽偏离必须全部声明在 _widthOverrides 里，且如实记录样例原值。"""
    overrides = SPEC["columns"]["_widthOverrides"]
    for key in ("floor", "face", "reading"):
        assert overrides[key]["sampleTwips"] > 0
    assert overrides["floor"]["sampleTwips"] == 492
    assert overrides["floor"]["widthTwips"] == wr.GRID_COLS[wr.COLUMN_INDEX["floor"]]
    assert overrides["face"]["sampleTwips"] == 480
    assert overrides["face"]["widthTwips"] == wr.GRID_COLS[wr.COLUMN_INDEX["face"]]
    assert len(overrides["reading"]["columns"]) == 6
    for column in overrides["reading"]["columns"]:
        assert wr.GRID_COLS[column] == overrides["reading"]["widthTwips"]

    # 偏离列恰好是已声明的那些；其余列必须与样例一致
    expected = ([wr.COLUMN_INDEX["floor"], wr.COLUMN_INDEX["face"]]
                + list(overrides["reading"]["columns"]))
    differing = [index for index, (old, new)
                 in enumerate(zip(wr.sample_reference_widths(), wr.GRID_COLS)) if old != new]
    assert differing == expected
    for column in (wr.COLUMN_INDEX["position"], wr.COLUMN_INDEX["size"],
                   wr.COLUMN_INDEX["requirement"]):
        assert wr.GRID_COLS[column] == wr.sample_reference_widths()[column]


# --------------------------------------------------------------------------
# 立柱/横梁表结构
# --------------------------------------------------------------------------
def _group(faces, template_type="column", **record_overrides):
    record = {
        "floor": "六层",
        "member_position": "1",
        "size_result": "63×164",
        "requirement_text": "立柱铝型材开口部位的厚度不应小于3.0mm，闭口部位的厚度不应小于2.5mm",
    }
    record.update(record_overrides)
    return {
        "template_type": template_type,
        "records": [{
            "record": record,
            "faces": [
                {"face": face, "readings_text": ["2.99"] * 5, "min_text": "2.99"}
                for face in faces
            ],
        }],
    }


def test_single_face_member_has_no_vmerge():
    """单面构件与样例一样：不带任何 vMerge（一条 restart 不构成合并，但会产生无谓差异）。"""
    doc = wr.new_document()
    table = wr.build_detection_table(doc, _group(["B"]))
    rows = table._tbl.findall(W + "tr")
    assert len(rows) == 3                       # 表头 2 + 数据 1
    for tc in rows[2].findall(W + "tc"):
        assert tc.find(W + "tcPr").find(W + "vMerge") is None


def test_multi_face_member_merges_four_columns():
    """两个检测面 → 两行，四列纵向合并：首行 restart，次行 continue（裸格）。"""
    doc = wr.new_document()
    table = wr.build_detection_table(doc, _group(["B", "H"]))
    rows = table._tbl.findall(W + "tr")
    assert len(rows) == 4                       # 表头 2 + 2 个面

    first, second = rows[2], rows[3]
    merged_columns = (0, 1, 2, wr.COLUMN_INDEX["requirement"])
    for column in merged_columns:
        restart = first.findall(W + "tc")[column].find(W + "tcPr").find(W + "vMerge")
        assert restart is not None and restart.get(W + "val") == "restart"

        tc = second.findall(W + "tc")[column]
        tc_pr = tc.find(W + "tcPr")
        vmerge = tc_pr.find(W + "vMerge")
        assert vmerge is not None and vmerge.get(W + "val") is None      # continue
        assert tc_pr.find(W + "tcMar") is None                          # 裸格不带边距
        assert tc_pr.find(W + "vAlign") is None                         # 不带垂直居中
        paragraph = tc.find(W + "p")
        assert paragraph is not None and paragraph.find(W + "pPr") is None  # 无 pPr 的空段
        assert _text(tc) == ""

    # 面 / 读数 / 最小值 三列不参与纵向合并
    for column in (3, 4, 9):
        tc_pr = second.findall(W + "tc")[column].find(W + "tcPr")
        assert tc_pr.find(W + "vMerge") is None
        assert tc_pr.find(W + "vAlign") is not None

    # 第二行的面与读数是自己的内容
    assert _text(second.findall(W + "tc")[3]) == "H"


def test_table_header_spans_seven_columns():
    doc = wr.new_document()
    table = wr.build_detection_table(doc, _group(["B"]))
    header = table._tbl.findall(W + "tr")[0].findall(W + "tc")
    assert len(header) == 5                      # 跨 7 列 → 该行只有 5 个 tc
    span = header[3].find(W + "tcPr").find(W + "gridSpan")
    assert int(span.get(W + "val")) == 7
    assert int(header[3].find(W + "tcPr").find(W + "tcW").get(W + "w")) == sum(wr.GRID_COLS[3:10])


def test_empty_requirement_shows_placeholder():
    doc = wr.new_document()
    table = wr.build_detection_table(doc, _group(["B"], requirement_text=None))
    data_row = table._tbl.findall(W + "tr")[2]
    assert _text(data_row.findall(W + "tc")[wr.COLUMN_INDEX["requirement"]]) == "无"


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
