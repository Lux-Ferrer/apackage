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
    assert section.page_width.twips == wr.PAGE_WIDTH_TWIPS == 11907
    assert section.page_height.twips == wr.PAGE_HEIGHT_TWIPS == 16839
    assert section.left_margin.twips == wr.PAGE_MARGIN_HORIZONTAL_TWIPS == 907
    assert section.right_margin.twips == wr.PAGE_MARGIN_HORIZONTAL_TWIPS
    assert section.top_margin.twips == wr.PAGE_MARGIN_TWIPS == 1440
    assert section.bottom_margin.twips == wr.PAGE_MARGIN_BOTTOM_TWIPS == 1843
    assert section.header_distance.twips == wr.HEADER_FOOTER_TWIPS == 850
    assert section.footer_distance.twips == wr.FOOTER_TWIPS == 964


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
    assert sum(wr.GRID_COLS) == wr.TABLE_WIDTH_TWIPS == 10833
    # "厚度检测结果（mm）" 横跨 面 + 1..5 + 最小 共 7 列，其后仅剩"截面尺寸要求"一列
    assert wr.THICKNESS_FIRST_COL == 3
    assert wr.THICKNESS_SPAN == 7
    assert wr.THICKNESS_FIRST_COL + wr.THICKNESS_SPAN == len(wr.GRID_COLS) - 1
    assert wr.GRID_COLS[-1] == 1962          # 截面尺寸要求列


def test_create_table_grid_and_width():
    doc = wr.new_document()
    table = wr.create_table(doc, 2, 2, widths=(wr.INFO_LABEL_WIDTH, wr.INFO_VALUE_WIDTH))
    cols = [int(g.get(qn("w:w"))) for g in table._tbl.find(qn("w:tblGrid")).findall(qn("w:gridCol"))]
    assert cols == [1600, 9233]

    tblPr = table._tbl.tblPr
    assert int(tblPr.find(qn("w:tblW")).get(qn("w:w"))) == 10833
    assert tblPr.find(qn("w:tblW")).get(qn("w:type")) == "dxa"
    assert tblPr.find(qn("w:tblLayout")).get(qn("w:type")) == "fixed"


def test_table_borders_match_sample():
    doc = wr.new_document()
    table = wr.create_table(doc, 1, 1)
    borders = table._tbl.tblPr.find(qn("w:tblBorders"))
    assert borders is not None
    for edge in ("top", "left", "bottom", "right"):
        element = borders.find(qn("w:%s" % edge))
        assert element.get(qn("w:val")) == "single"
        assert element.get(qn("w:sz")) == "12"        # 外框加粗
        assert element.get(qn("w:color")) == "000000"
    for edge in ("insideH", "insideV"):
        element = borders.find(qn("w:%s" % edge))
        assert element.get(qn("w:val")) == "single"
        assert element.get(qn("w:sz")) == "6"         # 内线细


def test_table_children_order_is_schema_valid():
    """tblBorders 必须在 tblLayout 之前，否则 Word 可能报文档损坏。"""
    doc = wr.new_document()
    table = wr.create_table(doc, 1, 1)
    tags = [etree.QName(child).localname for child in table._tbl.tblPr]
    assert tags.index("tblBorders") < tags.index("tblLayout")
    assert tags.index("tblW") < tags.index("tblBorders")


def test_cell_margins_match_sample():
    """真实表格只在**表格级**设左右内边距（57），单元格上不写 tcMar。"""
    doc = wr.new_document()
    table = wr.create_table(doc, 1, 1)
    assert table.cell(0, 0)._tc.tcPr.find(qn("w:tcMar")) is None

    cell_margin = table._tbl.tblPr.find(qn("w:tblCellMar"))
    assert cell_margin.find(qn("w:left")).get(qn("w:w")) == "57"
    assert cell_margin.find(qn("w:right")).get(qn("w:w")) == "57"


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
    assert first.get(qn("w:val")) == "567"
    assert second.get(qn("w:val")) == "522"
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
# 版式规格与基准（真实报告裁剪版）的锁定关系
# --------------------------------------------------------------------------
def _fixture_body():
    with zipfile.ZipFile(config.GOLDEN_SAMPLE) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    return root.find(W + "body")


def _text(element):
    return "".join(node.text or "" for node in element.iter(W + "t"))


def _paragraph_texts(tc):
    return [_text(p) for p in tc.findall(W + "p")]


def test_layout_spec_matches_fixture():
    """`report_layout.json` 的每个版式常量都必须等于基准实测值 —— 改错这里立刻红。"""
    body = _fixture_body()
    tables = body.findall(W + "tbl")
    assert len(tables) == 2                     # 立柱 + 横梁

    # —— 页面（四边不同：上 1440 / 下 1843 / 左右 907；页眉 850、页脚 964）——
    sect = body.find(W + "sectPr")
    pg_sz, pg_mar, grid = (sect.find(W + "pgSz"), sect.find(W + "pgMar"),
                           sect.find(W + "docGrid"))
    assert int(pg_sz.get(W + "w")) == wr.PAGE_WIDTH_TWIPS == 11907
    assert int(pg_sz.get(W + "h")) == wr.PAGE_HEIGHT_TWIPS == 16839
    assert int(pg_mar.get(W + "top")) == wr.PAGE_MARGIN_TWIPS == 1440
    assert int(pg_mar.get(W + "bottom")) == wr.PAGE_MARGIN_BOTTOM_TWIPS == 1843
    assert int(pg_mar.get(W + "left")) == wr.PAGE_MARGIN_HORIZONTAL_TWIPS == 907
    assert int(pg_mar.get(W + "right")) == wr.PAGE_MARGIN_HORIZONTAL_TWIPS
    assert int(pg_mar.get(W + "header")) == wr.HEADER_FOOTER_TWIPS == 850
    assert int(pg_mar.get(W + "footer")) == wr.FOOTER_TWIPS == 964
    assert int(grid.get(W + "linePitch")) == wr.DOC_GRID_LINE_PITCH == 312

    for tbl in tables:
        tbl_pr = tbl.find(W + "tblPr")
        rows = tbl.findall(W + "tr")

        # —— 表格级 ——
        assert int(tbl_pr.find(W + "tblW").get(W + "w")) == wr.TABLE_WIDTH_TWIPS == 10833
        assert tbl_pr.find(W + "tblW").get(W + "type") == "dxa"
        assert tbl_pr.find(W + "jc").get(W + "val") == SPEC["table"]["align"] == "center"
        assert tbl_pr.find(W + "tblLayout").get(W + "type") == SPEC["table"]["layout"] == "fixed"
        col_widths = [int(g.get(W + "w")) for g in tbl.find(W + "tblGrid").findall(W + "gridCol")]
        assert len(col_widths) == 11
        # 表2-4 与规格逐列一致；表2-5 前 3 列与末列相差 ≤4 twips（Word 自动重算，见 JSON 说明）
        if tbl is tables[0]:
            assert col_widths == list(wr.GRID_COLS)
        else:
            assert [abs(a - b) for a, b in zip(col_widths, wr.GRID_COLS)] == [2, 1, 1] + [0] * 7 + [4]
        assert sum(wr.GRID_COLS) == wr.TABLE_WIDTH_TWIPS

        borders = tbl_pr.find(W + "tblBorders")
        for edge in ("top", "left", "bottom", "right"):
            assert int(borders.find(W + edge).get(W + "sz")) == SPEC["table"]["border"]["outerSz"] == 12
        for edge in ("insideH", "insideV"):
            assert int(borders.find(W + edge).get(W + "sz")) == SPEC["table"]["border"]["innerSz"] == 6
        assert borders.find(W + "top").get(W + "color") == "000000"
        cell_margin = tbl_pr.find(W + "tblCellMar")
        assert int(cell_margin.find(W + "left").get(W + "w")) == 57
        assert int(cell_margin.find(W + "right").get(W + "w")) == 57
        look = tbl_pr.find(W + "tblLook")
        for key, value in SPEC["table"]["look"].items():
            assert look.get(W + key) == str(value), key

        # —— 行高：表头两行一致；数据行按模板不同（立柱 522 / 横梁 567）——
        for tr in rows[:2]:
            height = tr.find(W + "trPr").find(W + "trHeight")
            assert int(height.get(W + "val")) == wr.HEADER_ROW_TWIPS == 567
            assert height.get(W + "hRule") is None            # "至少"语义
        template_type = "column" if tbl is tables[0] else "beam"
        for tr in rows[2:]:
            height = tr.find(W + "trPr").find(W + "trHeight")
            assert int(height.get(W + "val")) == wr.data_row_height(template_type)

        # —— 表头文案：不加粗；部分文案是多段落 ——
        header0 = rows[0].findall(W + "tc")
        assert len(header0) == 5                              # 横向跨 7 列 → 5 个 tc
        assert _text(header0[0]) == SPEC["headers"]["fixed"][0]
        assert _paragraph_texts(header0[1]) == SPEC["headers"]["fixed"][1].split("\n")
        assert _paragraph_texts(header0[2]) == SPEC["headers"]["fixed"][2].split("\n")
        assert _text(header0[3]) == SPEC["headers"]["thickness"]
        assert int(header0[3].find(W + "tcPr").find(W + "gridSpan").get(W + "val")) == wr.THICKNESS_SPAN == 7
        # 表头首行的 tcW 之和 = 该表自己的列宽（表2-5 的 Word 重算值略有偏差）
        assert [int(tc.find(W + "tcPr").find(W + "tcW").get(W + "w")) for tc in header0] == [
            col_widths[0], col_widths[1], col_widths[2],
            sum(col_widths[3:10]), col_widths[10],
        ]
        assert [_text(tc) for tc in rows[1].findall(W + "tc")[3:10]] == list(SPEC["headers"]["thicknessSub"])
        assert wr.HEADER_THICKNESS_SUB == ("检测面", "1", "2", "3", "4", "5", "最小值")

        # —— 表头不加粗；单元格一律不写 tcMar、不显式设字号 ——
        for row in rows:
            for tc in row.findall(W + "tc"):
                tc_pr = tc.find(W + "tcPr")
                assert tc_pr.find(W + "tcMar") is None, "真实表格不在单元格上设内边距"
                for run in tc.iter(W + "r"):
                    rpr = run.find(W + "rPr")
                    assert rpr is None or rpr.find(W + "b") is None, "真实表格的表头不加粗"
                    assert rpr is None or rpr.find(W + "sz") is None, "真实表格不显式设字号"

    # —— 正文段落骨架（我们自己的，非客户结构）——
    paragraphs = body.findall(W + "p")
    assert len(paragraphs) == 11

    def run_size(paragraph):
        return int(paragraph.find(W + "r").find(W + "rPr").find(W + "sz").get(W + "val"))

    def spacing(paragraph):
        element = paragraph.find(W + "pPr").find(W + "spacing")
        return element.attrib if element is not None else {}

    def attr(element, name):
        return element.get(W + name)

    # 0-4 信息段 / 5 立柱标题 / 6 空段 / 7 横梁标题 / 8 空段 / 9 备注 / 10 文末空段
    assert run_size(paragraphs[0]) == int(wr.BODY_PT * 2) == 22
    assert attr(spacing(paragraphs[0]), "after") == str(SPACING["infoAfter"])
    assert run_size(paragraphs[5]) == int(wr.TITLE_PT * 2) == 32
    assert attr(spacing(paragraphs[5]), "before") == str(SPACING["titleBefore"])
    assert attr(spacing(paragraphs[5]), "after") == str(SPACING["titleAfter"])
    assert _text(paragraphs[5]) == "幕墙立柱截面尺寸检测结果"
    assert _text(paragraphs[7]) == "幕墙横梁截面尺寸检测结果"
    for index in (6, 8):
        assert _text(paragraphs[index]) == ""
        assert attr(spacing(paragraphs[index]), "before") == str(SPACING["spacerBefore"])
        assert attr(spacing(paragraphs[index]), "after") == str(SPACING["spacerAfter"])
    assert _text(paragraphs[9]).startswith("备注：")
    assert attr(spacing(paragraphs[9]), "before") == str(SPACING["noteBefore"])
    assert _text(paragraphs[10]) == ""                        # 文末空段


def test_layout_spec_file_is_language_neutral():
    """规格放在 JSON 里（而非代码），便于将来移植到前端 docx JS。"""
    assert wr.SPEC_PATH.exists()
    spec = wr.load_spec()
    assert spec["columns"]["widths"] == list(wr.GRID_COLS)
    assert spec["fonts"]["inheritedTablePt"] == 10
    assert spec["fonts"]["requirementPt"] is None             # 真实表格不显式设字号
    assert spec["_scope"].startswith("只对齐表格版式")


def test_floor_column_holds_four_chinese_characters():
    """楼层列（真实模板 1077 twips）要装得下「二十三层」这类 4 字楼层。"""
    usable = (wr.GRID_COLS[wr.COLUMN_INDEX["floor"]]
              - 2 * wr.SPEC["table"]["tableCellMargin"]["left"])
    assert usable >= 4 * wr.INHERITED_TABLE_PT * 20           # 10pt 下 1 汉字 = 200 twips

    from tools.analyze_text_fit import make_measurer          # 用真实字体验证，而非只比算式
    assert make_measurer()("二十三层", wr.INHERITED_TABLE_PT) <= usable


def test_no_width_overrides_against_the_real_report():
    """当前基准即真实报告：生效列宽与基准逐列一致，不存在"有意偏离"。"""
    assert SPEC["columns"]["_widthOverrides"] == {}
    assert list(wr.sample_reference_widths()) == list(wr.GRID_COLS)


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


def test_single_face_member_only_merges_the_requirement_column():
    """单面构件：前三列不合并；「截面尺寸要求」列仍要合并（整张表同一条文时合并成一块）。"""
    doc = wr.new_document()
    table = wr.build_detection_table(doc, _group(["B"]))
    rows = table._tbl.findall(W + "tr")
    assert len(rows) == 3                                     # 表头 2 + 数据 1

    data_cells = rows[2].findall(W + "tc")
    for column in (0, 1, 2):
        assert data_cells[column].find(W + "tcPr").find(W + "vMerge") is None
    requirement = data_cells[wr.COLUMN_INDEX["requirement"]].find(W + "tcPr").find(W + "vMerge")
    assert requirement is not None and requirement.get(W + "val") == "restart"


def test_multi_face_member_merges_four_columns():
    """两个检测面 → 两行，四列纵向合并：首行 restart，次行为普通空格的 continue。"""
    doc = wr.new_document()
    table = wr.build_detection_table(doc, _group(["B", "H"]))
    rows = table._tbl.findall(W + "tr")
    assert len(rows) == 4                                     # 表头 2 + 2 个面

    first, second = rows[2], rows[3]
    for column in (0, 1, 2, wr.COLUMN_INDEX["requirement"]):
        restart = first.findall(W + "tc")[column].find(W + "tcPr").find(W + "vMerge")
        assert restart is not None and restart.get(W + "val") == "restart"

        tc = second.findall(W + "tc")[column]
        tc_pr = tc.find(W + "tcPr")
        vmerge = tc_pr.find(W + "vMerge")
        assert vmerge is not None and vmerge.get(W + "val") is None      # continue
        assert tc_pr.find(W + "tcMar") is None                          # 不设内边距
        assert tc_pr.find(W + "vAlign").get(W + "val") == "center"       # 续行格仍有垂直居中
        assert _text(tc) == ""                                          # 续行格不带文本
        assert tc.find(W + "p").find(W + "pPr").find(W + "jc").get(W + "val") == "center"

    # 面 / 读数 / 最小值 三列不参与纵向合并
    for column in (3, 4, 9):
        tc_pr = second.findall(W + "tc")[column].find(W + "tcPr")
        assert tc_pr.find(W + "vMerge") is None
        assert tc_pr.find(W + "vAlign") is not None

    # 第二行的面与读数是自己的内容
    assert _text(second.findall(W + "tc")[3]) == "H"


def test_requirement_column_merges_across_members_with_same_clause():
    """同一张表里多个构件共用同一条文时，要求列合并成一块（与真实报告/案例 Excel 一致）。"""
    clause = "共用条文"
    group = _group(["B"], requirement_text=clause)
    group["records"].append({
        "record": {"floor": "六层", "member_position": "2", "size_result": "63×164",
                   "requirement_text": clause},
        "faces": [{"face": "B", "readings_text": ["2.99"] * 5, "min_text": "2.99"}],
    })
    doc = wr.new_document()
    table = wr.build_detection_table(doc, group)
    rows = table._tbl.findall(W + "tr")

    first_requirement = rows[2].findall(W + "tc")[wr.COLUMN_INDEX["requirement"]]
    second_requirement = rows[3].findall(W + "tc")[wr.COLUMN_INDEX["requirement"]]
    assert first_requirement.find(W + "tcPr").find(W + "vMerge").get(W + "val") == "restart"
    assert _text(first_requirement) == clause
    assert second_requirement.find(W + "tcPr").find(W + "vMerge").get(W + "val") is None
    assert _text(second_requirement) == ""                    # 续格不带文本


def test_requirement_column_starts_new_block_when_clause_changes():
    """条文不同 → 新起一块（restart），不会错误地并入上一块。"""
    group = _group(["B"], requirement_text="条文甲")
    group["records"].append({
        "record": {"floor": "六层", "member_position": "2", "size_result": "63×164",
                   "requirement_text": "条文乙"},
        "faces": [{"face": "B", "readings_text": ["2.99"] * 5, "min_text": "2.99"}],
    })
    doc = wr.new_document()
    table = wr.build_detection_table(doc, group)
    rows = table._tbl.findall(W + "tr")

    for row, clause in ((rows[2], "条文甲"), (rows[3], "条文乙")):
        tc = row.findall(W + "tc")[wr.COLUMN_INDEX["requirement"]]
        assert tc.find(W + "tcPr").find(W + "vMerge").get(W + "val") == "restart"
        assert _text(tc) == clause


def test_table_header_spans_seven_columns():
    doc = wr.new_document()
    table = wr.build_detection_table(doc, _group(["B"]))
    header = table._tbl.findall(W + "tr")[0].findall(W + "tc")
    assert len(header) == 5                                   # 跨 7 列 → 该行只有 5 个 tc
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
    assert reopened.sections[0].page_width.twips == 11907


def test_clear_body_keeps_section_setup():
    doc = wr.new_document()
    doc.add_paragraph("临时内容")
    wr.clear_body(doc)
    assert [p.text for p in doc.paragraphs] == []
    assert doc.sections[0].page_width.twips == 11907


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
    assert doc.sections[0].page_width.twips == 11907

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
