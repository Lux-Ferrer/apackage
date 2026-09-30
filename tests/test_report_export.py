# -*- coding: utf-8 -*-
"""项目级 Word 导出路由测试。"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from lxml import etree

from webapp import config
from webapp.services import measurements

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

PROJECT_FORM = {
    "project_no": "JCZG",
    "house_name": "金骐智谷",
    "house_address": "深圳市南山区",
    "client_org": "中冶",
    "test_date": "2026-09-03",
}


def _project(client, **overrides):
    payload = dict(PROJECT_FORM)
    payload.update(overrides)
    return client.post("/projects/", data=payload)


def _record(project_id=1, template_type="column", faces=None, **record_overrides):
    data = {
        "floor": "六层",
        "member_position": "1",
        "size_result": "63×164",
        "requirement_text": config.REQUIREMENT_OPTIONS[template_type][0],
        "faces": faces or [{"face": "B", "values": [2.99, 3.02, 3.01, 3.01, 2.99]}],
    }
    data.update(record_overrides)
    return measurements.create_record(project_id, template_type, data)


def _document_root(response):
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        return etree.fromstring(archive.read("word/document.xml"))


def _document_text(response):
    return "".join(node.text or "" for node in _document_root(response).iter(W + "t"))


# --------------------------------------------------------------------------
# 基本导出
# --------------------------------------------------------------------------
def test_export_returns_docx_attachment(client, ctx):
    _project(client)
    _record()
    response = client.get("/projects/1/export")
    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]
    assert response.data[:2] == b"PK"                    # docx 就是 zip


def test_export_filename_follows_template(client, ctx):
    from urllib.parse import unquote

    _project(client)
    disposition = unquote(client.get("/projects/1/export").headers["Content-Disposition"])
    assert "JCZG_金骐智谷_检测报告.docx" in disposition


def test_export_writes_file_into_reports_dir(client, ctx, app):
    _project(client)
    client.get("/projects/1/export")
    written = Path(app.config["REPORTS_DIR"]) / "JCZG_金骐智谷_检测报告.docx"
    assert written.exists()


def test_export_content(client, ctx):
    _project(client)
    _record()
    text = _document_text(client.get("/projects/1/export"))

    assert "项目编号：JCZG" in text
    assert "房屋名称：金骐智谷" in text
    assert "房屋地点：深圳市南山区" in text
    assert "委托单位：中冶" in text
    assert "检测日期：2026-09-03" in text
    assert "幕墙立柱截面尺寸检测结果" in text
    assert "63×164" in text
    assert "2.99" in text
    assert "立柱铝型材开口部位" in text
    assert "备注：检测构件位置详见检测工作内容附件 18。" in text


def test_export_includes_both_sections(client, ctx):
    _project(client)
    _record(template_type="column")
    _record(template_type="beam", member_position="6",
            faces=[{"face": "t", "values": [2.14, 2.12, 2.11, 2.10, 2.10]}])
    text = _document_text(client.get("/projects/1/export"))
    assert "幕墙立柱截面尺寸检测结果" in text
    assert "幕墙横梁截面尺寸检测结果" in text
    # 立柱在前、横梁在后
    assert text.index("幕墙立柱截面尺寸检测结果") < text.index("幕墙横梁截面尺寸检测结果")


def test_export_outputs_only_existing_sections(client, ctx):
    _project(client)
    _record(template_type="beam", member_position="6",
            faces=[{"face": "t", "values": [2.14, 2.12, 2.11, 2.10, 2.10]}])
    text = _document_text(client.get("/projects/1/export"))
    assert "幕墙横梁截面尺寸检测结果" in text
    assert "幕墙立柱截面尺寸检测结果" not in text


def test_export_omits_glass_section(client, ctx):
    """玻璃模块不在范围内：生成物里绝不能出现。"""
    _project(client)
    _record()
    text = _document_text(client.get("/projects/1/export"))
    assert "玻璃" not in text


def test_export_produces_a4(client, ctx):
    _project(client)
    root = _document_root(client.get("/projects/1/export"))
    sect = root.find(W + "body").find(W + "sectPr")
    assert sect.find(W + "pgSz").get(W + "w") == "11907"
    assert sect.find(W + "pgSz").get(W + "h") == "16839"
    assert sect.find(W + "pgMar").get(W + "top") == "1440"


def test_export_uses_expected_table_count(client, ctx):
    _project(client)
    _record(template_type="column")
    _record(template_type="beam", member_position="6",
            faces=[{"face": "t", "values": [2.14, 2.12, 2.11, 2.10, 2.10]}])
    body = _document_root(client.get("/projects/1/export")).find(W + "body")
    assert len(body.findall(W + "tbl")) == 2


# --------------------------------------------------------------------------
# 边界
# --------------------------------------------------------------------------
def test_export_empty_project(client, ctx):
    """空项目允许导出：只有信息段 + 备注，不出表格、不出章节标题。"""
    _project(client)
    response = client.get("/projects/1/export")
    assert response.status_code == 200

    body = _document_root(response).find(W + "body")
    assert body.findall(W + "tbl") == []

    text = _document_text(response)
    assert "项目编号：JCZG" in text
    assert "备注：" in text
    assert "截面尺寸检测结果" not in text


def test_export_blank_optional_fields(client, ctx):
    _project(client, house_address="", client_org="", test_date="")
    text = _document_text(client.get("/projects/1/export"))
    assert "房屋地点：" in text
    assert "委托单位：" in text


def test_export_multi_face_member_merges(client, ctx):
    """多面构件：第二行的前 3 列与要求列应是纵向合并的 continue 格。"""
    _project(client)
    _record(faces=[
        {"face": "B", "values": [2.99, 3.02, 3.01, 3.01, 2.99]},
        {"face": "H", "values": [2.55, 2.52, 2.52, 2.53, 2.53]},
    ])
    body = _document_root(client.get("/projects/1/export")).find(W + "body")
    rows = body.findall(W + "tbl")[0].findall(W + "tr")
    assert len(rows) == 4                                  # 表头 2 + 2 个面
    for column in (0, 1, 2, 10):
        vmerge = rows[3].findall(W + "tc")[column].find(W + "tcPr").find(W + "vMerge")
        assert vmerge is not None and vmerge.get(W + "val") is None


def test_export_404_for_unknown_project(client):
    assert client.get("/projects/999/export").status_code == 404


def test_export_requires_no_get_side_effects(client, ctx):
    """导出是只读操作：不应改变记录数。"""
    _project(client)
    _record()
    client.get("/projects/1/export")
    assert measurements.count_by_template(1) == {"column": 1, "beam": 0}
