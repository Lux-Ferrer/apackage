# -*- coding: utf-8 -*-
"""M3 附页导出：结构、分页、图片嵌入、降级，以及"无附页路径不变"。"""

from __future__ import annotations

import io
import zipfile

from lxml import etree

from webapp import config
from webapp.services import measurements

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

PROJECT = {
    "project_no": "JCZG", "house_name": "金骐智谷",
    "house_address": "", "client_org": "", "test_date": "",
}


def _project(client, **overrides):
    payload = dict(PROJECT)
    payload.update(overrides)
    return client.post("/projects/", data=payload)


def _record(project_id=1):
    return measurements.create_record(project_id, "column", {
        "floor": "六层", "member_position": "1", "size_result": "63×164",
        "requirement_text": None,
        "faces": [{"face": "B", "values": [2.99, 3.02, 3.01, 3.01, 2.99]}],
    })


def _defect(client, make_image, project_id=1, **overrides):
    payload = {
        "defect_type": "密封胶开裂",
        "project_part": "东立面三层 1# 立柱",
        "risk_level": "高",
        "rectification_plan": "第一行：更换密封胶。\n第二行：复检确认无渗漏。",
        "related_standards": "GB/T 21086-2007 第 5.2 条",
        "project_id": str(project_id),
        "image": make_image(filename="隐患照片.png"),
    }
    payload.update(overrides)
    return client.post("/defects/", data=payload, content_type="multipart/form-data")


# --------------------------------------------------------------------------
# 解析辅助
# --------------------------------------------------------------------------
def _archive(response):
    return zipfile.ZipFile(io.BytesIO(response.data))


def _body(response):
    with _archive(response) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    return root.find(W + "body")


def _text(response) -> str:
    return "".join(node.text or "" for node in _body(response).iter(W + "t"))


def _child_names(response) -> list:
    return [etree.QName(child).localname for child in _body(response)]


def _text_of(element) -> str:
    return "".join(node.text or "" for node in element.iter(W + "t"))


def _paragraphs(response) -> list:
    return _body(response).findall(W + "p")


def _attachment_titles(response) -> list:
    """附页标题及其是否带 pageBreakBefore。"""
    titles = []
    for paragraph in _paragraphs(response):
        text = _text_of(paragraph)
        if not text.startswith("检测报告附页"):
            continue
        ppr = paragraph.find(W + "pPr")
        has_break = ppr is not None and ppr.find(W + "pageBreakBefore") is not None
        titles.append((text, has_break))
    return titles


def _media(response) -> list:
    with _archive(response) as archive:
        return [name for name in archive.namelist() if name.startswith("word/media/")]


# --------------------------------------------------------------------------
# 附页结构
# --------------------------------------------------------------------------
def test_attachments_are_appended_when_requested(client, ctx, make_image):
    _project(client)
    _record()
    _defect(client, make_image)

    response = client.get("/projects/1/export?attachments=1")
    assert response.status_code == 200

    text = _text(response)
    assert "检测报告附页（1/1）" in text
    for label in config.ATTACHMENT_LABELS.values():
        assert label in text
    assert "密封胶开裂" in text
    assert "Zeyu Jin（结构工程部）" in text
    assert "隐患照片.png" in text                 # 原文件名可追溯


def test_attachment_title_starts_a_new_page(client, ctx, make_image):
    """每份附页独立成页：标题段落带 pageBreakBefore（不产生游离空段）。"""
    _project(client)
    _record()
    _defect(client, make_image)

    titles = _attachment_titles(client.get("/projects/1/export?attachments=1"))
    assert len(titles) == 1
    assert titles[0][1] is True


def test_attachment_comes_after_note(client, ctx, make_image):
    _project(client)
    _record()
    _defect(client, make_image)

    body = _body(client.get("/projects/1/export?attachments=1"))
    texts = [_text_of(child) for child in body if etree.QName(child).localname == "p"]
    note_index = next(i for i, t in enumerate(texts) if t.startswith("备注"))
    title_index = next(i for i, t in enumerate(texts) if t.startswith("检测报告附页"))
    assert note_index < title_index


def test_attachment_embeds_compressed_image(client, ctx, make_image):
    _project(client)
    _record()
    _defect(client, make_image, image=make_image(size=(2400, 1200), filename="现场大图.jpg"))

    media = _media(client.get("/projects/1/export?attachments=1"))
    assert any(name.endswith((".jpeg", ".jpg")) for name in media)
    assert "现场大图.jpg" in _text(client.get("/projects/1/export?attachments=1"))


def test_multiple_attachments_are_numbered(client, ctx, make_image):
    _project(client)
    _record()
    _defect(client, make_image, project_part="东立面")
    _defect(client, make_image, project_part="西立面")

    response = client.get("/projects/1/export?attachments=1")
    titles = _attachment_titles(response)
    assert [text for text, _has_break in titles] == ["检测报告附页（1/2）", "检测报告附页（2/2）"]
    assert all(has_break for _text, has_break in titles)

    text = _text(response)
    assert "东立面" in text and "西立面" in text


def test_attachment_shows_placeholder_for_empty_fields(client, ctx, make_image):
    _project(client)
    _record()
    _defect(client, make_image, related_standards="", extra_advice="")

    text = _text(client.get("/projects/1/export?attachments=1"))
    assert config.EMPTY_TEXT in text                     # 空字段显示「无」


# --------------------------------------------------------------------------
# 分支与降级
# --------------------------------------------------------------------------
def test_no_attachments_when_not_requested(client, ctx, make_image):
    _project(client)
    _record()
    _defect(client, make_image)

    for url in ("/projects/1/export", "/projects/1/export?attachments=0"):
        response = client.get(url)
        assert response.status_code == 200
        assert "检测报告附页" not in _text(response)
        assert _media(response) == []                    # 没有嵌入任何图片


def test_no_attachments_when_project_has_none(client, ctx):
    """没有关联报告时，即使传了 attachments=1 也不加附页。"""
    _project(client)
    _record()

    response = client.get("/projects/1/export?attachments=1")
    assert response.status_code == 200
    assert "检测报告附页" not in _text(response)


def test_attachment_renders_when_image_file_is_missing(client, ctx, app, make_image):
    """图片文件被删掉 —— 附页仍要导出，并就地说明缺失。"""
    from pathlib import Path

    _project(client)
    _record()
    _defect(client, make_image)

    uploads = Path(app.config["UPLOADS_DIR"])
    for path in uploads.glob("*"):
        path.unlink()

    response = client.get("/projects/1/export?attachments=1")
    assert response.status_code == 200
    text = _text(response)
    assert "检测报告附页（1/1）" in text
    assert "图片缺失" in text
    assert _media(response) == []


# --------------------------------------------------------------------------
# 回归：无附页路径必须与 M2 完全一致
# --------------------------------------------------------------------------
def test_without_attachments_body_sequence_matches_m2(client, ctx):
    """无附页时元素序列 = 信息段×5 + 标题 + 表 + 空段 + 备注 + 文末空段。"""
    _project(client)
    _record()

    body = _body(client.get("/projects/1/export"))
    names = [etree.QName(child).localname for child in body]
    assert names == ["p"] * 6 + ["tbl"] + ["p"] * 3 + ["sectPr"]

    paragraphs = [_text_of(child) for child in body if etree.QName(child).localname == "p"]
    assert paragraphs[0].startswith("项目编号：")
    assert paragraphs[4].startswith("检测日期：")
    assert paragraphs[5] == "幕墙立柱截面尺寸检测结果"
    assert paragraphs[6] == ""                           # 表格后的空段
    assert paragraphs[7].startswith("备注：")
    assert paragraphs[8] == ""                           # 文末空段


def test_attachment_does_not_change_detection_tables(client, ctx, make_image):
    """加附页不影响正文两张检测表的内容与结构。"""
    _project(client)
    _record()
    _defect(client, make_image)

    without = _text(client.get("/projects/1/export?attachments=0"))
    with_attachments = _text(client.get("/projects/1/export?attachments=1"))
    assert "幕墙立柱截面尺寸检测结果" in without
    assert without.split("检测报告附页")[0] == with_attachments.split("检测报告附页")[0]
