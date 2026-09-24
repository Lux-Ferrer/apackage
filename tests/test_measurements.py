# -*- coding: utf-8 -*-
"""检测记录服务层测试。

重点两件事：
1. **事务健壮性** —— 记录与其检测面读数要么一起成功，要么一起回滚；
2. **编辑锁定** —— 更新路径绝不改动 template_type。
"""

from __future__ import annotations

import sqlite3

import pytest
from docx import Document

from webapp import config, db
from webapp.services import measurements
from webapp.services import projects as project_service


@pytest.fixture
def project_id(ctx):
    return project_service.create({
        "project_no": "JCZG",
        "house_name": "金骐智谷",
        "house_address": None,
        "client_org": None,
        "test_date": None,
    })


def make_data(floor="六层", member_position="1", size_result="63×164",
              requirement_text=None, faces=None):
    return {
        "floor": floor,
        "member_position": member_position,
        "size_result": size_result,
        "requirement_text": requirement_text,
        "faces": faces if faces is not None else [
            {"face": "B", "values": [2.99, 3.02, 3.01, 3.01, 2.99]},
        ],
    }


# --------------------------------------------------------------------------
# 尺寸结果规范化 / 条文解析
# --------------------------------------------------------------------------
@pytest.mark.parametrize("raw, expected", [
    ("63x164", "63×164"),
    ("63X164", "63×164"),
    ("63*164", "63×164"),
    ("63 × 164", "63×164"),
    ("  63×164  ", "63×164"),
    ("12+75", "12+75"),
    ("", None),
    ("   ", None),
    (None, None),
])
def test_normalize_size_result(raw, expected):
    assert measurements.normalize_size_result(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("63 164", "63×164"),          # 两个数字 + 空格 → 空格视作乘号
    ("63  164", "63×164"),
    ("63\u3000164", "63×164"),     # 全角空格
    ("12 + 75", "12+75"),          # 需求报告里的加号写法保留
    ("  82 * 76 ", "82×76"),
])
def test_normalize_size_result_space_forms(raw, expected):
    assert measurements.normalize_size_result(raw) == expected


def test_normalize_size_result_never_glues_two_numbers():
    """回归：`63 164` 曾经被删空格粘成 `63164`（数据静默损坏）。"""
    assert measurements.normalize_size_result("63 164") != "63164"
    assert measurements.normalize_size_result("63 164") == "63×164"


def test_beam_requirement_options_keep_existing_order():
    """预置条文只允许追加：前两项的文本与索引不能变（历史快照靠索引回填）。"""
    options = config.REQUIREMENT_OPTIONS[config.TEMPLATE_BEAM]
    assert len(options) == 3
    assert options[0] == "当横梁跨度不大于1.2m时，铝型材截面主要受力部位的厚度不应小于2.0mm"
    assert options[1] == "当横梁跨度大于1.2m时，其截面主要受力部位的厚度不应小于2.5mm"
    assert options[2].startswith("当横梁跨度不大于1.2m时") and "；" in options[2]


def test_column_requirement_options_unchanged():
    options = config.REQUIREMENT_OPTIONS[config.TEMPLATE_COLUMN]
    assert len(options) == 2
    assert options[0].startswith("立柱铝型材开口部位的厚度不应小于3.0mm")


REQUIREMENTS_DOC = config.BASE_DIR / "docs" / "requirements" / "幕墙检测APP需求报告.docx"


def test_requirement_text_matches_requirements_doc():
    """config 的条文文案必须与需求报告一致（去空白、统一标点后比较）。

    需求报告是"文字内容"的权威来源，对拍基准样例只负责字体与版式。
    第 3 个横梁选项只存在于需求报告的表 2-5 图片里（文字层没有），故只核对前两项。
    """
    if not REQUIREMENTS_DOC.exists():
        pytest.skip("需求报告缺失：%s" % REQUIREMENTS_DOC)

    document = Document(str(REQUIREMENTS_DOC))
    known = {
        measurements.normalize_clause(paragraph.text.strip().lstrip("-").strip())
        for paragraph in document.paragraphs
    }
    for template_type in config.TEMPLATE_TYPES:
        for option in config.REQUIREMENT_OPTIONS[template_type][:2]:
            assert measurements.normalize_clause(option) in known, option


def test_normalize_clause_unifies_spacing_and_punctuation():
    assert measurements.normalize_clause("不应小于 3.0mm，闭口") == "不应小于3.0mm,闭口"
    assert measurements.normalize_clause("当横梁跨度大于1.2m时；") == "当横梁跨度大于1.2m时"
    assert measurements.normalize_clause(None) == ""


def test_resolve_requirement_by_index():
    options = config.REQUIREMENT_OPTIONS["column"]
    assert measurements.resolve_requirement("0", "column") == options[0]
    assert measurements.resolve_requirement("1", "column") == options[1]
    assert measurements.resolve_requirement("", "column") is None
    assert measurements.resolve_requirement("9", "column") is None      # 越界
    assert measurements.resolve_requirement("abc", "column") is None


def test_requirement_index_round_trip():
    options = config.REQUIREMENT_OPTIONS["beam"]
    assert measurements.requirement_index_of(options[1], "beam") == 1
    assert measurements.requirement_index_of(options[2], "beam") == 2
    assert measurements.requirement_index_of("某条历史文案", "beam") is None
    assert measurements.requirement_index_of(None, "beam") is None


# --------------------------------------------------------------------------
# 表单解析
# --------------------------------------------------------------------------
def _form(**overrides):
    data = {
        "floor": "六层",
        "member_position": "1",
        "size_result": "63x164",
        "requirement_index": "0",
        "face_0": "B",
        "value_0_1": "2.99", "value_0_2": "3.02", "value_0_3": "3.01",
        "value_0_4": "3.01", "value_0_5": "2.99",
        "face_1": "H",
        "value_1_1": "2.55", "value_1_2": "", "value_1_3": "", "value_1_4": "", "value_1_5": "",
    }
    data.update(overrides)
    return data


def test_parse_valid_form():
    data, errors = measurements.parse_record_form(_form(), "column")
    assert errors == {}
    assert data["size_result"] == "63×164"
    assert data["requirement_text"].startswith("立柱铝型材开口部位")
    assert [face["face"] for face in data["faces"]] == ["B", "H"]
    assert data["faces"][0]["values"] == [2.99, 3.02, 3.01, 3.01, 2.99]
    assert data["faces"][1]["values"] == [2.55, None, None, None, None]


def test_parse_requires_floor_and_position():
    _, errors = measurements.parse_record_form(_form(floor="  ", member_position=""), "column")
    assert "floor" in errors and "member_position" in errors


def test_parse_requires_at_least_one_face():
    blank = {}
    for index in range(6):
        blank["face_%d" % index] = ""
        for position in range(1, 6):
            blank["value_%d_%d" % (index, position)] = ""
    _, errors = measurements.parse_record_form(_form(**blank), "column")
    assert errors.get("faces")


def test_parse_reports_face_row_with_only_readings():
    """填了读数却没填面标签：报错指向该行，而不是笼统的"至少一个面"。"""
    _, errors = measurements.parse_record_form(_form(face_0="", face_1=""), "column")
    assert "face_0" in errors and "face_1" in errors
    assert "faces" not in errors


def test_parse_skips_blank_rows_without_error():
    """加了一行却没填：整行跳过，不产生脏数据也不报错。"""
    data, errors = measurements.parse_record_form(_form(face_2="", face_3=""), "column")
    assert errors == {}
    assert len(data["faces"]) == 2


def test_parse_rejects_reading_without_face():
    _, errors = measurements.parse_record_form(_form(face_0="", value_0_1="2.5"), "column")
    assert "face_0" in errors


def test_parse_rejects_duplicate_face():
    _, errors = measurements.parse_record_form(_form(face_1="B"), "column")
    assert "检测面「B」在本记录中重复" in errors["face_1"]


def test_parse_rejects_non_numeric_reading():
    _, errors = measurements.parse_record_form(_form(value_0_3="abc"), "column")
    assert "value_0_3" in errors


def test_parse_ignores_rows_beyond_face_max():
    """服务端只探测 0..FACE_MAX_COUNT-1，多提交的行被忽略。"""
    form = _form(face_6="Z", value_6_1="1.0")
    data, errors = measurements.parse_record_form(form, "column")
    assert errors == {}
    assert len(data["faces"]) == 2


def test_parse_rejects_unknown_template():
    with pytest.raises(ValueError):
        measurements.parse_record_form(_form(), "glass")


# --------------------------------------------------------------------------
# 新增 / 读取
# --------------------------------------------------------------------------
def test_create_record_persists_faces(project_id):
    record_id = measurements.create_record(project_id, "column", make_data(
        faces=[
            {"face": "B", "values": [2.99, 3.02, 3.01, 3.01, 2.99]},
            {"face": "H", "values": [2.55, 2.52, 2.52, 2.53, 2.53]},
        ]
    ))
    record = measurements.get_record(record_id)
    assert record["project_id"] == project_id
    assert record["template_type"] == "column"
    assert record["size_result"] == "63×164"

    readings = measurements.get_readings(record_id)
    assert [row["face"] for row in readings] == ["B", "H"]
    assert measurements.count_by_template(project_id) == {"column": 1, "beam": 0}


def test_create_record_increments_sort_order(project_id):
    first = measurements.create_record(project_id, "column", make_data(member_position="1"))
    second = measurements.create_record(project_id, "column", make_data(member_position="2"))
    assert measurements.get_record(first)["sort_order"] == 0
    assert measurements.get_record(second)["sort_order"] == 1


def test_create_record_rejects_unknown_template(project_id):
    with pytest.raises(ValueError):
        measurements.create_record(project_id, "glass", make_data())


def test_create_record_rolls_back_on_duplicate_face(project_id):
    """事务健壮性：读数写入失败时，已插入的记录头必须一并回滚。"""
    duplicated = make_data(faces=[
        {"face": "B", "values": [2.99, 3.02, 3.01, 3.01, 2.99]},
        {"face": "B", "values": [9.99, 9.99, 9.99, 9.99, 9.99]},   # 触发 UNIQUE 冲突
    ])
    with pytest.raises(sqlite3.IntegrityError):
        measurements.create_record(project_id, "column", duplicated)

    assert measurements.count_by_template(project_id) == {"column": 0, "beam": 0}
    assert db.query_one("SELECT COUNT(*) AS total FROM thickness_readings")["total"] == 0


# --------------------------------------------------------------------------
# 更新（含编辑锁定）
# --------------------------------------------------------------------------
def test_update_record_replaces_readings(project_id):
    record_id = measurements.create_record(project_id, "column", make_data())
    measurements.update_record(record_id, make_data(
        floor="二十三层",
        faces=[{"face": "H", "values": [1.0, 2.0, 3.0, 4.0, 5.0]}],
    ))

    record = measurements.get_record(record_id)
    assert record["floor"] == "二十三层"
    readings = measurements.get_readings(record_id)
    assert len(readings) == 1 and readings[0]["face"] == "H"


def test_update_record_never_changes_template_type(project_id):
    """编辑锁定（数据层）：UPDATE 字段清单不含 template_type。"""
    record_id = measurements.create_record(project_id, "column", make_data())
    payload = make_data()
    payload["template_type"] = "beam"          # 即使硬塞进来也不生效
    measurements.update_record(record_id, payload)
    assert measurements.get_record(record_id)["template_type"] == "column"


def test_update_record_rolls_back_and_keeps_original(project_id, monkeypatch):
    """事务健壮性：读数重写失败时，构件字段与原有读数都必须保持不变。"""
    record_id = measurements.create_record(project_id, "column", make_data(
        floor="六层",
        faces=[{"face": "B", "values": [1.0, 2.0, 3.0, 4.0, 5.0]}],
    ))

    def boom(conn, record_id_arg, faces):
        raise RuntimeError("模拟写入失败")

    monkeypatch.setattr(measurements, "_insert_readings", boom)

    with pytest.raises(RuntimeError):
        measurements.update_record(record_id, make_data(
            floor="二十三层",
            faces=[{"face": "H", "values": [9.0, 9.0, 9.0, 9.0, 9.0]}],
        ))

    record = measurements.get_record(record_id)
    assert record["floor"] == "六层", "UPDATE 应已回滚"

    readings = measurements.get_readings(record_id)
    assert len(readings) == 1, "DELETE 应已回滚"
    assert readings[0]["face"] == "B"
    assert readings[0]["value_1"] == 1.0


def test_update_missing_record_raises(project_id):
    with pytest.raises(LookupError):
        measurements.update_record(999999, make_data())


# --------------------------------------------------------------------------
# 删除
# --------------------------------------------------------------------------
def test_delete_record_cascades_readings(project_id):
    record_id = measurements.create_record(project_id, "column", make_data(
        faces=[{"face": "B", "values": [1, 2, 3, 4, 5]},
               {"face": "H", "values": [6, 7, 8, 9, 10]}],
    ))
    assert db.query_one("SELECT COUNT(*) AS total FROM thickness_readings")["total"] == 2

    measurements.delete_record(record_id)

    assert measurements.get_record(record_id) is None
    assert db.query_one("SELECT COUNT(*) AS total FROM thickness_readings")["total"] == 0


def test_delete_missing_record_raises(project_id):
    with pytest.raises(LookupError):
        measurements.delete_record(999999)


# --------------------------------------------------------------------------
# 分组读取
# --------------------------------------------------------------------------
def test_grouped_by_template_orders_column_first_and_carries_min(project_id):
    measurements.create_record(project_id, "beam", make_data(
        member_position="6",
        faces=[{"face": "t", "values": [2.14, 2.12, 2.11, 2.10, 2.10]}],
    ))
    measurements.create_record(project_id, "column", make_data(
        member_position="1",
        faces=[{"face": "B", "values": [2.99, 3.02, 3.01, 3.01, 2.99]},
               {"face": "H", "values": [2.55, 2.52, 2.52, 2.53, 2.53]}],
    ))

    groups = measurements.grouped_by_template(project_id)
    assert [group["template_type"] for group in groups] == ["column", "beam"]
    assert [group["count"] for group in groups] == [1, 1]

    column_faces = groups[0]["records"][0]["faces"]
    assert [face["face"] for face in column_faces] == ["B", "H"]
    assert column_faces[0]["min_text"] == "2.99"
    assert column_faces[1]["min_text"] == "2.52"
    assert column_faces[0]["readings_text"] == ["2.99", "3.02", "3.01", "3.01", "2.99"]

    assert groups[1]["records"][0]["faces"][0]["min_text"] == "2.10"


def test_grouped_by_template_empty_project(project_id):
    groups = measurements.grouped_by_template(project_id)
    assert [group["count"] for group in groups] == [0, 0]


def test_describe_counts():
    assert measurements.describe_counts({"column": 3, "beam": 2}) == "立柱 3 条 · 横梁 2 条"
