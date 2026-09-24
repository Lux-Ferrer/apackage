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


def test_home_page(client):
    response = client.get("/")
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


def test_submit_saves_and_redirects(client):
    response = client.post("/defects/", data=FORM)
    assert response.status_code == 302
    assert "/defects/1" in response.headers["Location"]


def test_submit_rejects_missing_required_field(client):
    payload = dict(FORM, project_part="")
    response = client.post("/defects/", data=payload)
    assert response.status_code == 400
    assert "工程部位不能为空" in response.get_data(as_text=True)


def test_submit_rejects_blank_custom_defect_type(client):
    payload = dict(FORM, defect_type=config.CUSTOM_DEFECT_OPTION, custom_defect_type="  ")
    response = client.post("/defects/", data=payload)
    assert response.status_code == 400
    assert "自定义缺陷类型" in response.get_data(as_text=True)


def test_submit_accepts_custom_defect_type(client):
    payload = dict(FORM, defect_type=config.CUSTOM_DEFECT_OPTION, custom_defect_type="幕墙开启扇脱落")
    assert client.post("/defects/", data=payload).status_code == 302

    detail = client.get("/defects/1").get_data(as_text=True)
    assert "幕墙开启扇脱落" in detail


def test_detail_records_reporter_snapshot(client):
    client.post("/defects/", data=FORM)
    html = client.get("/defects/1").get_data(as_text=True)
    assert config.DEFAULT_REPORTER["name"] in html


def test_detail_404_for_unknown_id(client):
    assert client.get("/defects/999").status_code == 404


def test_export_returns_a4_docx(client):
    client.post("/defects/", data=FORM)
    response = client.get("/defects/1/export")
    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]

    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        document = archive.read("word/document.xml").decode("utf-8")
        assert 'w:w="11906"' in document      # A4 宽，不是 Letter 的 12240
        assert "密封胶开裂" in document


def test_export_404_for_unknown_id(client):
    assert client.get("/defects/999/export").status_code == 404


def test_risk_level_default_is_medium(client):
    """表单未选等级时按默认「中」处理。"""
    payload = dict(FORM)
    payload.pop("risk_level")
    client.post("/defects/", data=payload)
    assert "中" in client.get("/defects/1").get_data(as_text=True)


def test_invalid_risk_level_rejected(client):
    response = client.post("/defects/", data=dict(FORM, risk_level="紧急"))
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
