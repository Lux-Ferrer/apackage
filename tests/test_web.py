# -*- coding: utf-8 -*-
"""Web 层冒烟测试：拆包后原有 PoC 链路（填报 -> 存储 -> 导出 Word）仍然可用。"""

from __future__ import annotations

import io
import zipfile

import pytest

from webapp import config

FORM = {
    "defect_type": "密封胶开裂",
    "project_part": "东立面三层 1# 立柱",
    "risk_level": "中",
    "rectification_plan": "第一行：更换密封胶。\n第二行：复检确认无渗漏。",
}


def post_defect(client, make_image, **overrides):
    """提交缺陷填报（M3 起隐患图片必填，所以默认带一张现场生成的小图）。"""
    payload = dict(FORM)
    payload.update(overrides)
    payload.setdefault("image", make_image(filename="缺陷照片.png"))
    return client.post("/defects/", data=payload, content_type="multipart/form-data")


def test_about_page_reachable(client):
    """旧首页内容（模块进度表）搬到了 /about，从「我的 → 应用信息」进入。

    更细的 UI 契约断言在 ``tests/test_ui.py``。
    """
    response = client.get("/about")
    assert response.status_code == 200
    assert "模块进度" in response.get_data(as_text=True)


def test_projects_page_reachable(client):
    """M1 之后 /projects/ 已是真实列表页（此处为空态）。"""
    response = client.get("/projects/")
    assert response.status_code == 200
    assert "还没有项目" in response.get_data(as_text=True)


def test_form_page_lists_preset_defect_types(client):
    html = client.get("/defects/new").get_data(as_text=True)
    for defect_type in config.DEFECT_TYPES:
        assert defect_type in html
    assert config.CUSTOM_DEFECT_OPTION in html


def test_submit_saves_and_redirects(client, make_image):
    """M4 起填报提交后落到「报告管理」的详情页（需求 3.4d 的查看报告）。"""
    response = post_defect(client, make_image)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/reports/1")


def test_submit_rejects_missing_required_field(client, make_image):
    response = post_defect(client, make_image, project_part="")
    assert response.status_code == 400
    assert "工程部位不能为空" in response.get_data(as_text=True)


def test_submit_rejects_blank_custom_defect_type(client, make_image):
    response = post_defect(client, make_image, defect_type=config.CUSTOM_DEFECT_OPTION,
                           custom_defect_type="  ")
    assert response.status_code == 400
    assert "自定义缺陷类型" in response.get_data(as_text=True)


def test_submit_accepts_custom_defect_type(client, make_image):
    response = post_defect(client, make_image, defect_type=config.CUSTOM_DEFECT_OPTION,
                           custom_defect_type="幕墙开启扇脱落")
    assert response.status_code == 302

    detail = client.get("/reports/1").get_data(as_text=True)
    assert "幕墙开启扇脱落" in detail


def test_detail_records_reporter_snapshot(client, make_image):
    post_defect(client, make_image)
    html = client.get("/reports/1").get_data(as_text=True)
    assert config.DEFAULT_REPORTER["name"] in html


def test_detail_404_for_unknown_id(client):
    assert client.get("/reports/999").status_code == 404
    # 旧的详情路径仍可用：308 到报告管理详情，跟随后 404
    assert client.get("/defects/999", follow_redirects=True).status_code == 404


def test_export_returns_a4_docx(client, make_image):
    post_defect(client, make_image)
    response = client.get("/defects/1/export")
    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]

    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        document = archive.read("word/document.xml").decode("utf-8")
        assert 'w:w="11907"' in document      # A4 宽，不是 Letter 的 12240
        assert "密封胶开裂" in document


def test_export_404_for_unknown_id(client):
    assert client.get("/defects/999/export").status_code == 404


def test_risk_level_default_is_medium(client, make_image):
    """表单未选等级时按默认「中」处理。"""
    response = post_defect(client, make_image, risk_level="")
    assert response.status_code == 302
    assert "中" in client.get("/reports/1").get_data(as_text=True)


def test_invalid_risk_level_rejected(client, make_image):
    response = post_defect(client, make_image, risk_level="紧急")
    assert response.status_code == 400
    assert "隐患等级无效" in response.get_data(as_text=True)


def test_app_creates_database(tmp_path):
    """create_app 应在指定路径建库（测试夹具用的是临时库，不碰项目 defects.db）。"""
    from webapp import create_app

    db_file = tmp_path / "fresh.db"
    app = create_app({"TESTING": True, "DB_PATH": str(db_file),
                      "REPORTS_DIR": str(tmp_path / "r"),
                      "UPLOADS_DIR": str(tmp_path / "u")})
    assert db_file.exists()
    with app.app_context():
        from webapp import db as db_module
        assert db_module.query_one("SELECT COUNT(*) AS c FROM projects")["c"] == 0
