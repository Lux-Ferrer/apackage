# -*- coding: utf-8 -*-
"""缺陷检测报告服务层：表单解析、绑定项目、图片落盘的原子性、附页数据装配。"""

from __future__ import annotations

from pathlib import Path

import pytest

from webapp import config, db
from webapp.services import defects as defect_service
from webapp.services import images
from webapp.services import projects as project_service
from webapp.services import word_report as wr

FORM = {
    "defect_type": "密封胶开裂",
    "project_part": "东立面三层 1# 立柱",
    "risk_level": "中",
    "rectification_plan": "第一行：更换密封胶。\n第二行：复检确认无渗漏。",
}


@pytest.fixture
def project_id(ctx):
    return project_service.create({
        "project_no": "JCZG", "house_name": "金骐智谷",
        "house_address": None, "client_org": None, "test_date": None,
    })


def form(**overrides):
    payload = dict(FORM)
    payload.update(overrides)
    return payload


def data_of(**overrides):
    data, errors = defect_service.parse_form(form(**overrides))
    assert not errors, errors
    return data


# --------------------------------------------------------------------------
# 表单解析
# --------------------------------------------------------------------------
def test_parse_valid_form():
    data, errors = defect_service.parse_form(form(
        related_standards="GB/T 21086-2007 第 5.2 条\nJGJ 102-2003 第 3.1 条",
        extra_advice="注意高空作业安全",
    ))
    assert errors == {}
    assert data["defect_type"] == "密封胶开裂"
    assert data["risk_level"] == "中"
    assert data["related_standards"].startswith("GB/T")
    assert data["extra_advice"] == "注意高空作业安全"
    assert data["project_id"] is None                       # 默认不绑定
    assert data["reporter_name"] == config.DEFAULT_REPORTER["name"]
    assert set(data) == {
        "defect_type", "project_part", "risk_level", "rectification_plan",
        "related_standards", "extra_advice", "project_id",
        "reporter_name", "reporter_department", "created_at",
    }                                                       # 图片路径不在表单解析里产生


def test_parse_optional_fields_become_none():
    data, _ = defect_service.parse_form(form(related_standards="  ", extra_advice=""))
    assert data["related_standards"] is None and data["extra_advice"] is None


def test_parse_custom_defect_type():
    data, errors = defect_service.parse_form(form(
        defect_type=config.CUSTOM_DEFECT_OPTION, custom_defect_type="幕墙开启扇脱落"))
    assert errors == {} and data["defect_type"] == "幕墙开启扇脱落"

    _, errors = defect_service.parse_form(form(
        defect_type=config.CUSTOM_DEFECT_OPTION, custom_defect_type="  "))
    assert "custom_defect_type" in errors


@pytest.mark.parametrize("overrides, field", [
    ({"project_part": ""}, "project_part"),
    ({"rectification_plan": "   "}, "rectification_plan"),
    ({"defect_type": ""}, "defect_type"),
    ({"risk_level": "紧急"}, "risk_level"),
])
def test_parse_required_fields(overrides, field):
    _, errors = defect_service.parse_form(form(**overrides))
    assert field in errors


def test_parse_default_risk_level():
    data, _ = defect_service.parse_form(form(risk_level=""))
    assert data["risk_level"] == config.DEFAULT_RISK_LEVEL


def test_parse_binds_existing_project(project_id):
    data, errors = defect_service.parse_form(form(project_id=str(project_id)))
    assert errors == {} and data["project_id"] == project_id


def test_parse_rejects_unknown_project(ctx):
    _, errors = defect_service.parse_form(form(project_id="999"))
    assert "project_id" in errors
    _, errors = defect_service.parse_form(form(project_id="abc"))
    assert "project_id" in errors


# --------------------------------------------------------------------------
# 写入
# --------------------------------------------------------------------------
def test_create_persists_report_and_image(ctx, app, make_upload):
    data = data_of(project_id=None)

    defect_id = defect_service.create(data, make_upload(filename="隐患照片.png"))
    row = defect_service.get(defect_id)

    assert row["defect_type"] == "密封胶开裂"
    assert row["rectification_plan"].startswith("第一行")
    assert row["image_path"].startswith("uploads/defects/")
    assert images.original_name_from_path(row["image_path"]) == "隐患照片.png"
    # 落盘位置 = 应用配置的上传目录（单一真相源）
    assert (Path(app.config["UPLOADS_DIR"]) / Path(row["image_path"]).name).exists()


def test_create_binds_project(ctx, project_id, make_upload):
    defect_id = defect_service.create(data_of(project_id=str(project_id)), make_upload())

    assert defect_service.count_for_project(project_id) == 1
    assert [row["id"] for row in defect_service.list_for_project(project_id)] == [defect_id]


def test_create_removes_file_when_insert_fails(ctx, app, make_upload):
    """图片先落盘再入库；**入库失败必须把文件删掉**，不留孤儿。"""
    class Boom:
        def __enter__(self):
            raise RuntimeError("模拟入库失败")

        def __exit__(self, *exc):
            return False

    monkeypatch_target = defect_service.db
    original = monkeypatch_target.transaction
    monkeypatch_target.transaction = lambda: Boom()
    try:
        with pytest.raises(RuntimeError):
            defect_service.create(data_of(), make_upload(filename="x.png"))
    finally:
        monkeypatch_target.transaction = original

    uploads = Path(app.config["UPLOADS_DIR"])
    assert list(uploads.iterdir()) == [], "入库失败后不应留下孤儿文件"


def test_delete_project_keeps_report_and_clears_link(ctx, project_id, make_upload):
    """已确认语义：删除项目 → 关联报告置空保留。"""
    defect_id = defect_service.create(data_of(project_id=str(project_id)), make_upload())

    project_service.delete(project_id)

    row = defect_service.get(defect_id)
    assert row is not None and row["project_id"] is None
    assert defect_service.list_for_project(project_id) == []


# --------------------------------------------------------------------------
# 附页数据装配
# --------------------------------------------------------------------------
def _row(**overrides):
    row = {
        "id": 1,
        "defect_type": "密封胶开裂",
        "project_part": "东立面三层 1# 立柱",
        "risk_level": "高",
        "rectification_plan": "更换密封胶",
        "related_standards": "GB/T 21086-2007 第 5.2 条",
        "extra_advice": None,
        "reporter_name": "Zeyu Jin",
        "reporter_department": "结构工程部",
        "image_path": None,
        "created_at": "2026-09-23 10:05:07",
    }
    row.update(overrides)
    return row


def test_format_report_time():
    assert defect_service.format_report_time("2026-09-23 10:05:07") == "2026-09-23 10:05"
    assert defect_service.format_report_time("") == ""
    assert defect_service.format_report_time(None) == ""


def test_field_values_compose_reporter_and_empties():
    values = defect_service.field_values({"defect": _row(), "original_name": ""})
    assert values["reporter"] == "Zeyu Jin（结构工程部）"
    assert values["reported_at"] == "2026-09-23 10:05"
    assert values["extra_advice"] == config.EMPTY_TEXT          # 空 → 无
    assert values["image_file"] == config.EMPTY_TEXT
    assert list(values) == list(config.ATTACHMENT_ORDER)        # 顺序即渲染顺序


def test_attachment_views_without_image():
    views = defect_service.attachment_views([_row()])
    assert views[0]["image_path"] is None
    assert views[0]["original_name"] == ""
    assert views[0]["missing"] is False


def test_attachment_views_prepare_image_copy(ctx, tmp_path, make_upload):
    defect_id = defect_service.create(data_of(), make_upload(size=(2400, 1200), filename="大图.png"))
    row = defect_service.get(defect_id)

    workdir = tmp_path / "work"
    view = defect_service.attachment_views([row], workdir)[0]

    assert view["original_name"] == "大图.png"
    assert view["compressed"] is True
    assert view["image_path"].exists()
    assert view["image_width_twips"] <= wr.ATTACHMENT_SPEC["imageMaxWidthTwips"]
    assert defect_service.image_file_text(view) == "大图.png（已压缩）"


def test_attachment_views_flags_missing_file(ctx, tmp_path, make_upload):
    """图片文件被删掉时，附页数据要标记缺失而不是让导出失败。"""
    defect_id = defect_service.create(data_of(), make_upload(filename="lost.png"))
    row = defect_service.get(defect_id)
    images.absolute_path(row["image_path"]).unlink()

    view = defect_service.attachment_views([row], tmp_path / "work")[0]
    assert view["missing"] is True and view["image_path"] is None
    assert defect_service.image_file_text(view) == "lost.png（文件缺失）"
