# -*- coding: utf-8 -*-
"""检测记录路由测试：录入链路、校验回填、编辑锁定、最小值展示。"""

from __future__ import annotations

from webapp import db

PROJECT_FORM = {
    "project_no": "JCZG",
    "house_name": "金骐智谷",
    "house_address": "",
    "client_org": "",
    "test_date": "",
}


def _project(client):
    client.post("/projects/", data=PROJECT_FORM)


def _record_form(**overrides):
    data = {
        "floor": "六层",
        "member_position": "1",
        "size_result": "63x164",
        "requirement_index": "0",
        "face_0": "B",
        "value_0_1": "2.99", "value_0_2": "3.02", "value_0_3": "3.01",
        "value_0_4": "3.01", "value_0_5": "2.99",
        "face_1": "H",
        "value_1_1": "2.55", "value_1_2": "2.52", "value_1_3": "2.52",
        "value_1_4": "2.53", "value_1_5": "2.53",
    }
    data.update(overrides)
    return data


def _post_record(client, template="column", **overrides):
    return client.post("/projects/1/records/?template=%s" % template,
                       data=_record_form(**overrides))


# --------------------------------------------------------------------------
# 模板选择
# --------------------------------------------------------------------------
def test_chooser_page_lists_both_templates(client):
    _project(client)
    html = client.get("/projects/1/records/new").get_data(as_text=True)
    assert "选择检测记录模板" in html
    assert "幕墙立柱" in html and "幕墙横梁" in html


def test_unknown_template_falls_back_to_chooser(client):
    _project(client)
    html = client.get("/projects/1/records/new?template=glass").get_data(as_text=True)
    assert "选择检测记录模板" in html


def test_form_page_renders_column_template(client):
    _project(client)
    html = client.get("/projects/1/records/new?template=column").get_data(as_text=True)
    assert "幕墙立柱截面尺寸检测结果" in html
    assert 'name="face_0"' in html
    assert 'name="value_0_1"' in html
    assert '<option value="B"></option>' in html      # datalist 建议值
    assert "立柱铝型材开口部位" in html
    assert "当横梁跨度" not in html                     # 不串到横梁条文


def test_form_page_renders_beam_template(client):
    _project(client)
    html = client.get("/projects/1/records/new?template=beam").get_data(as_text=True)
    assert "幕墙横梁截面尺寸检测结果" in html
    assert '<option value="t"></option>' in html
    assert "当横梁跨度" in html


def test_new_record_unknown_project_404(client):
    assert client.get("/projects/999/records/new").status_code == 404


# --------------------------------------------------------------------------
# 新增
# --------------------------------------------------------------------------
def test_create_record_persists_faces(client, ctx):
    _project(client)
    response = _post_record(client)
    assert response.status_code == 302
    assert "#record-" in response.headers["Location"]

    record = db.query_one("SELECT * FROM measurement_records WHERE id = 1")
    assert record["template_type"] == "column"
    assert record["size_result"] == "63×164"          # x 已规范化为 ×
    assert record["requirement_text"].startswith("立柱铝型材开口部位")

    readings = db.query_all("SELECT * FROM thickness_readings ORDER BY id")
    assert [row["face"] for row in readings] == ["B", "H"]
    assert readings[0]["value_1"] == 2.99


def test_create_requires_template_whitelist(client, ctx):
    _project(client)
    assert client.post("/projects/1/records/", data=_record_form()).status_code == 400
    assert client.post("/projects/1/records/?template=glass",
                       data=_record_form()).status_code == 400
    assert db.query_one("SELECT COUNT(*) AS total FROM measurement_records")["total"] == 0


def test_create_validation_error_rerenders_and_keeps_input(client):
    _project(client)
    response = _post_record(client, floor="", face_0="")
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "楼层不能为空" in html
    assert "填了厚度读数" in html
    assert 'value="2.99"' in html                      # 已填读数被保留


def test_create_rejects_duplicate_face(client, ctx):
    _project(client)
    response = _post_record(client, face_1="B")
    assert response.status_code == 400
    assert "重复" in response.get_data(as_text=True)
    assert db.query_one("SELECT COUNT(*) AS total FROM measurement_records")["total"] == 0


def test_create_without_any_face_rejected(client):
    _project(client)
    response = _post_record(client, face_0="", face_1="",
                            value_0_1="", value_0_2="", value_0_3="", value_0_4="", value_0_5="",
                            value_1_1="", value_1_2="", value_1_3="", value_1_4="", value_1_5="")
    assert response.status_code == 400
    assert "至少填写 1 个检测面" in response.get_data(as_text=True)


def test_create_blank_extra_row_is_ignored(client, ctx):
    """多加了一行却没填：不报错，也不产生脏数据。"""
    _project(client)
    response = _post_record(client, face_2="", value_2_1="")
    assert response.status_code == 302
    assert db.query_one("SELECT COUNT(*) AS total FROM thickness_readings")["total"] == 2


# --------------------------------------------------------------------------
# 编辑锁定
# --------------------------------------------------------------------------
def test_edit_page_has_no_template_control(client, ctx):
    _project(client)
    _post_record(client)
    html = client.get("/records/1/edit").get_data(as_text=True)

    assert "模板类型不可切换" in html
    assert 'name="template_type"' not in html
    assert "幕墙立柱截面尺寸检测结果" in html
    # 下拉只加载本模板的条文
    assert "立柱铝型材开口部位" in html
    assert "当横梁跨度" not in html


def test_edit_page_prefills_existing_faces(client, ctx):
    _project(client)
    _post_record(client)
    html = client.get("/records/1/edit").get_data(as_text=True)
    assert 'value="B"' in html and 'value="H"' in html
    assert 'value="2.99"' in html
    assert 'value="63×164"' in html


def test_update_cannot_switch_template_type(client, ctx):
    """核心保证：伪造 template_type=beam 也改不掉立柱记录。"""
    _project(client)
    _post_record(client)

    response = client.post("/records/1/update", data=_record_form(template_type="beam"))
    assert response.status_code == 302

    record = db.query_one("SELECT * FROM measurement_records WHERE id = 1")
    assert record["template_type"] == "column"
    # 条文仍是立柱的
    assert record["requirement_text"].startswith("立柱铝型材开口部位")


def test_update_replaces_faces(client, ctx):
    _project(client)
    _post_record(client)
    client.post("/records/1/update", data=_record_form(
        floor="二十三层", face_1="", value_1_1="", value_1_2="",
        value_1_3="", value_1_4="", value_1_5=""))

    record = db.query_one("SELECT * FROM measurement_records WHERE id = 1")
    assert record["floor"] == "二十三层"
    readings = db.query_all("SELECT * FROM thickness_readings")
    assert len(readings) == 1 and readings[0]["face"] == "B"


def test_update_validation_error_keeps_record(client, ctx):
    _project(client)
    _post_record(client)
    response = client.post("/records/1/update", data=_record_form(member_position=""))
    assert response.status_code == 400
    assert "构件位置不能为空" in response.get_data(as_text=True)
    assert db.query_one("SELECT member_position FROM measurement_records WHERE id=1")["member_position"] == "1"


def test_update_unknown_record_404(client):
    assert client.post("/records/999/update", data=_record_form()).status_code == 404


def test_edit_unknown_record_404(client):
    assert client.get("/records/999/edit").status_code == 404


# --------------------------------------------------------------------------
# 删除与详情展示
# --------------------------------------------------------------------------
def test_delete_record(client, ctx):
    _project(client)
    _post_record(client)
    response = client.post("/records/1/delete")
    assert response.status_code == 302
    assert db.query_one("SELECT COUNT(*) AS total FROM measurement_records")["total"] == 0
    assert db.query_one("SELECT COUNT(*) AS total FROM thickness_readings")["total"] == 0


def test_detail_shows_minimum_computed_by_server(client, ctx):
    _project(client)
    _post_record(client)
    html = client.get("/projects/1").get_data(as_text=True)
    assert "2.99" in html          # B 面最小值
    assert "2.52" in html          # H 面最小值
    assert "立柱 1 条 · 横梁 0 条" in html


def test_switch_template_option_absent_for_beam_record(client, ctx):
    _project(client)
    client.post("/projects/1/records/?template=beam", data=_record_form(
        face_0="t", value_0_1="2.14", value_0_2="2.12", value_0_3="2.11",
        value_0_4="2.10", value_0_5="2.10"))
    html = client.get("/records/1/edit").get_data(as_text=True)
    assert "当横梁跨度" in html
    assert "立柱铝型材开口部位" not in html
