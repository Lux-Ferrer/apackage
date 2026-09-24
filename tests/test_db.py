# -*- coding: utf-8 -*-
"""数据库结构测试：表、约束、级联语义。"""

from __future__ import annotations

import sqlite3

import pytest

from webapp import db as db_module

EXPECTED_TABLES = {"projects", "measurement_records", "thickness_readings", "defects"}


def _tables(conn) -> set:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row["name"] for row in rows} - {"sqlite_sequence"}


def test_init_db_creates_four_tables(conn):
    assert EXPECTED_TABLES <= _tables(conn)


def test_no_out_of_scope_tables(conn):
    """登录与速记不在本期范围，不建死表。"""
    tables = _tables(conn)
    assert "users" not in tables
    assert "notes" not in tables


def test_schema_version_written(conn):
    assert db_module.schema_version(conn) == db_module.SCHEMA_VERSION


def test_foreign_keys_enabled(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_project_no_is_unique(conn):
    conn.execute("INSERT INTO projects (project_no, house_name) VALUES ('JCZG','金骐智谷')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO projects (project_no, house_name) VALUES ('JCZG','重复编号')")


def test_template_type_only_column_or_beam(conn):
    conn.execute("INSERT INTO projects (id, project_no, house_name) VALUES (1,'P1','A')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO measurement_records (project_id, template_type, floor, member_position)"
            " VALUES (1,'glass','六层','1')"
        )


def test_risk_level_only_high_medium_low(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO defects (defect_type, project_part, risk_level, rectification_plan)"
            " VALUES ('密封胶开裂','东立面','紧急','重新打胶')"
        )


def test_face_accepts_free_text(conn):
    """检测面是短文本：真实数据为 B / H / t，且允许自由输入，不做枚举校验。"""
    conn.execute("INSERT INTO projects (id, project_no, house_name) VALUES (1,'P1','A')")
    conn.execute(
        "INSERT INTO measurement_records (id, project_id, template_type, floor, member_position)"
        " VALUES (1,1,'column','六层','1')"
    )
    for face in ("B", "H", "t", "自定义面"):
        conn.execute(
            "INSERT INTO thickness_readings (record_id, face, value_1) VALUES (1,?,2.5)",
            (face,),
        )
    faces = {row["face"] for row in conn.execute("SELECT face FROM thickness_readings")}
    assert faces == {"B", "H", "t", "自定义面"}


def test_face_is_unique_per_record(conn):
    conn.execute("INSERT INTO projects (id, project_no, house_name) VALUES (1,'P1','A')")
    conn.execute(
        "INSERT INTO measurement_records (id, project_id, template_type, floor, member_position)"
        " VALUES (1,1,'column','六层','1')"
    )
    conn.execute("INSERT INTO thickness_readings (record_id, face, value_1) VALUES (1,'B',2.5)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO thickness_readings (record_id, face, value_1) VALUES (1,'B',3.0)")


def test_delete_project_cascades_measurements(conn):
    conn.execute("INSERT INTO projects (id, project_no, house_name) VALUES (1,'P1','A')")
    conn.execute(
        "INSERT INTO measurement_records (id, project_id, template_type, floor, member_position)"
        " VALUES (1,1,'column','六层','1')"
    )
    conn.execute("INSERT INTO thickness_readings (record_id, face, value_1) VALUES (1,'B',2.99)")

    conn.execute("DELETE FROM projects WHERE id = 1")

    assert conn.execute("SELECT COUNT(*) AS c FROM measurement_records").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) AS c FROM thickness_readings").fetchone()["c"] == 0


def test_delete_project_keeps_defect_and_clears_link(conn):
    """已确认：删除项目 -> 关联缺陷报告置空保留（不级联删除）。"""
    conn.execute("INSERT INTO projects (id, project_no, house_name) VALUES (1,'P1','A')")
    conn.execute(
        "INSERT INTO defects (id, project_id, defect_type, project_part, risk_level, rectification_plan)"
        " VALUES (1,1,'密封胶开裂','东立面三层','中','重新打胶')"
    )

    conn.execute("DELETE FROM projects WHERE id = 1")

    row = conn.execute("SELECT * FROM defects WHERE id = 1").fetchone()
    assert row is not None, "缺陷报告应保留"
    assert row["project_id"] is None, "关联应被置空"


def test_legacy_poc_database_is_rejected(tmp_path):
    """未重建的 PoC 旧库应给出明确报错，而不是静默产生错乱数据。"""
    legacy_path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(str(legacy_path))
    legacy.execute(
        "CREATE TABLE defects (id INTEGER PRIMARY KEY AUTOINCREMENT, defect_type TEXT NOT NULL,"
        " project_part TEXT NOT NULL, risk_level TEXT NOT NULL,"
        " rectification_plan TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    legacy.commit()
    legacy.close()

    with pytest.raises(RuntimeError) as excinfo:
        db_module.init_db(legacy_path)
    assert "旧版 PoC 数据库" in str(excinfo.value)


def test_reading_columns_allow_null(conn):
    """现场可能只测了部分点，读数允许留空。"""
    conn.execute("INSERT INTO projects (id, project_no, house_name) VALUES (1,'P1','A')")
    conn.execute(
        "INSERT INTO measurement_records (id, project_id, template_type, floor, member_position)"
        " VALUES (1,1,'beam','六层','6')"
    )
    conn.execute(
        "INSERT INTO thickness_readings (record_id, face, value_1, value_2)"
        " VALUES (1,'t',2.14,2.12)"
    )
    row = conn.execute("SELECT * FROM thickness_readings").fetchone()
    assert row["value_3"] is None and row["value_5"] is None
