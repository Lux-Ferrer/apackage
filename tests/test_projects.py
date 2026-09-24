# -*- coding: utf-8 -*-
"""项目管理路由测试。"""

from __future__ import annotations

from webapp import db
from webapp.services import measurements

PROJECT_FORM = {
    "project_no": "JCZG",
    "house_name": "金骐智谷",
    "house_address": "深圳市南山区",
    "client_org": "中冶",
    "test_date": "2026-09-03",
}


def _create(client, **overrides):
    payload = dict(PROJECT_FORM)
    payload.update(overrides)
    return client.post("/projects/", data=payload)


def _one_record(project_id=1):
    return measurements.create_record(project_id, "column", {
        "floor": "六层",
        "member_position": "1",
        "size_result": "63×164",
        "requirement_text": None,
        "faces": [{"face": "B", "values": [2.99, 3.02, 3.01, 3.01, 2.99]}],
    })


# --------------------------------------------------------------------------
# 列表与新建
# --------------------------------------------------------------------------
def test_index_empty_state(client):
    html = client.get("/projects/").get_data(as_text=True)
    assert "还没有项目" in html


def test_create_redirects_to_detail(client):
    response = _create(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/projects/1")


def test_created_project_is_listed_with_counts(client):
    _create(client)
    html = client.get("/projects/").get_data(as_text=True)
    assert "JCZG" in html and "金骐智谷" in html
    assert "立柱 0 · 横梁 0" in html


def test_duplicate_project_no_gives_field_error(client, ctx):
    _create(client)
    response = _create(client, house_name="另一个项目")
    assert response.status_code == 400
    assert "已存在" in response.get_data(as_text=True)
    assert db.query_one("SELECT COUNT(*) AS total FROM projects")["total"] == 1


def test_required_fields_reported_inline(client):
    response = client.post("/projects/", data={"project_no": "", "house_name": ""})
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "项目编号不能为空" in html
    assert "房屋名称不能为空" in html


def test_invalid_date_rejected(client):
    response = _create(client, test_date="2026/09/03")
    assert response.status_code == 400
    assert "YYYY-MM-DD" in response.get_data(as_text=True)


def test_optional_fields_may_be_blank(client, ctx):
    response = client.post("/projects/", data={
        "project_no": "P1", "house_name": "只有必填",
        "house_address": "", "client_org": "", "test_date": "",
    })
    assert response.status_code == 302
    row = db.query_one("SELECT * FROM projects WHERE id = 1")
    assert row["house_address"] is None and row["test_date"] is None


def test_overlong_project_no_rejected(client):
    response = _create(client, project_no="X" * 51)
    assert response.status_code == 400
    assert "不能超过" in response.get_data(as_text=True)


# --------------------------------------------------------------------------
# 编辑
# --------------------------------------------------------------------------
def test_edit_form_prefilled(client):
    _create(client)
    html = client.get("/projects/1/edit").get_data(as_text=True)
    assert 'value="JCZG"' in html
    assert 'value="金骐智谷"' in html


def test_update_persists_changes(client, ctx):
    _create(client)
    response = client.post("/projects/1/update",
                           data=dict(PROJECT_FORM, house_name="金骐智谷二期"))
    assert response.status_code == 302
    row = db.query_one("SELECT house_name FROM projects WHERE id = 1")
    assert row["house_name"] == "金骐智谷二期"


def test_update_keeps_project_no_unique(client, ctx):
    _create(client)
    _create(client, project_no="OTHER", house_name="另一个项目")
    response = client.post("/projects/2/update",
                           data=dict(PROJECT_FORM, project_no="JCZG", house_name="另一个项目"))
    assert response.status_code == 400
    assert "已被其他项目使用" in response.get_data(as_text=True)


def test_edit_unknown_project_404(client):
    assert client.get("/projects/999/edit").status_code == 404


# --------------------------------------------------------------------------
# 删除（级联语义）
# --------------------------------------------------------------------------
def test_delete_project_cascades_records_but_keeps_defects(client, ctx):
    _create(client)
    _one_record(project_id=1)
    db.execute(
        "INSERT INTO defects (project_id, defect_type, project_part, risk_level, rectification_plan)"
        " VALUES (1, '密封胶开裂', '东立面三层', '中', '重新打胶')"
    )

    response = client.post("/projects/1/delete")
    assert response.status_code == 302

    assert db.query_one("SELECT COUNT(*) AS total FROM projects")["total"] == 0
    assert db.query_one("SELECT COUNT(*) AS total FROM measurement_records")["total"] == 0
    assert db.query_one("SELECT COUNT(*) AS total FROM thickness_readings")["total"] == 0

    defect = db.query_one("SELECT * FROM defects")
    assert defect is not None, "关联缺陷报告应保留"
    assert defect["project_id"] is None, "关联应被置空"


def test_delete_unknown_project_404(client):
    assert client.post("/projects/999/delete").status_code == 404


# --------------------------------------------------------------------------
# 详情页
# --------------------------------------------------------------------------
def test_detail_shows_project_info_and_counts(client, ctx):
    _create(client)
    _one_record(project_id=1)
    html = client.get("/projects/1").get_data(as_text=True)

    assert "金骐智谷" in html and "JCZG" in html
    assert "深圳市南山区" in html
    assert "立柱 1 条 · 横梁 0 条" in html


def test_detail_shows_face_minimum(client, ctx):
    _create(client)
    _one_record(project_id=1)
    html = client.get("/projects/1").get_data(as_text=True)
    assert "2.99" in html, "详情页应展示服务端算好的最小值"
    assert "检测面" in html


def test_detail_delete_message_states_record_impact(client, ctx):
    _create(client)
    _one_record(project_id=1)
    html = client.get("/projects/1").get_data(as_text=True)
    assert "将同时删除 1 条检测记录（立柱 1 条、横梁 0 条）" in html
    assert "没有关联的缺陷报告" in html


def test_detail_delete_message_mentions_defect_unbinding(client, ctx):
    _create(client)
    _one_record(project_id=1)
    db.execute(
        "INSERT INTO defects (project_id, defect_type, project_part, risk_level, rectification_plan)"
        " VALUES (1, '密封胶开裂', '东立面三层', '中', '重新打胶')"
    )
    html = client.get("/projects/1").get_data(as_text=True)
    assert "1 份缺陷报告将解除绑定并保留" in html


def test_detail_lists_associated_defects(client, ctx):
    _create(client)
    db.execute(
        "INSERT INTO defects (project_id, defect_type, project_part, risk_level, rectification_plan)"
        " VALUES (1, '密封胶开裂', '东立面三层', '高', '重新打胶')"
    )
    html = client.get("/projects/1").get_data(as_text=True)
    assert "关联缺陷报告" in html
    assert "密封胶开裂" in html


def test_detail_empty_defect_state(client):
    _create(client)
    html = client.get("/projects/1").get_data(as_text=True)
    assert "暂无关联报告" in html


def test_detail_unknown_project_404(client):
    assert client.get("/projects/999").status_code == 404
