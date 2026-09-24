# -*- coding: utf-8 -*-
"""项目读写服务。

包含项目 CRUD、列表统计（一条 SQL 出立柱/横梁记录数，避免 N+1）、
以及删除影响面统计（确认弹窗文案与 DB 级联语义严格一致）。
"""

from __future__ import annotations

from datetime import datetime

from .. import config, db

MAX_LENGTHS = {
    "project_no": (50, "项目编号"),
    "house_name": (100, "房屋名称"),
    "house_address": (200, "房屋地点"),
    "client_org": (100, "委托单位"),
}


def _clean(value):
    return "" if value is None else str(value).strip()


# --------------------------------------------------------------------------
# 读取
# --------------------------------------------------------------------------
def list_with_counts():
    """项目列表：附带立柱/横梁记录数（子查询一次算完）。"""
    return db.query_all(
        """
        SELECT p.*,
               (SELECT COUNT(*) FROM measurement_records m
                 WHERE m.project_id = p.id AND m.template_type = 'column') AS column_count,
               (SELECT COUNT(*) FROM measurement_records m
                 WHERE m.project_id = p.id AND m.template_type = 'beam')   AS beam_count
          FROM projects p
         ORDER BY p.id DESC
        """
    )


def get(project_id):
    return db.query_one("SELECT * FROM projects WHERE id = ?", (project_id,))


def list_defects(project_id):
    """项目关联的缺陷报告（倒序）。绑定字段在 M3 实现，这里先做只读展示。"""
    return db.query_all(
        "SELECT * FROM defects WHERE project_id = ? ORDER BY created_at DESC, id DESC",
        (project_id,),
    )


def delete_impact(project_id):
    """删除项目的影响面：检测记录分类计数 + 关联缺陷报告数。"""
    counts = {template_type: 0 for template_type in config.TEMPLATE_TYPES}
    for row in db.query_all(
        "SELECT template_type, COUNT(*) AS total FROM measurement_records"
        " WHERE project_id = ? GROUP BY template_type",
        (project_id,),
    ):
        if row["template_type"] in counts:
            counts[row["template_type"]] = row["total"]

    defect_row = db.query_one(
        "SELECT COUNT(*) AS total FROM defects WHERE project_id = ?", (project_id,)
    )
    counts["defects"] = defect_row["total"] if defect_row else 0
    counts["records"] = sum(counts[t] for t in config.TEMPLATE_TYPES)
    return counts


def build_delete_message(project, impact):
    """删除确认文案。措辞与 DB 语义一致：记录级联删除、缺陷报告解除绑定并保留。"""
    parts = [
        "确认删除项目「%s（%s）」？" % (project["house_name"], project["project_no"]),
        "将同时删除 %d 条检测记录（立柱 %d 条、横梁 %d 条）"
        % (impact["records"], impact.get(config.TEMPLATE_COLUMN, 0),
           impact.get(config.TEMPLATE_BEAM, 0)),
    ]
    if impact["defects"]:
        parts.append("关联的 %d 份缺陷报告将解除绑定并保留" % impact["defects"])
    else:
        parts.append("该项目没有关联的缺陷报告")
    return "；".join(parts) + "。"


# --------------------------------------------------------------------------
# 校验与写入
# --------------------------------------------------------------------------
def parse_form(form):
    """解析项目表单，返回 ``(data, errors)``；errors 的键即字段名。"""
    errors = {}
    data = {}

    for field in ("project_no", "house_name", "house_address", "client_org", "test_date"):
        data[field] = _clean(form.get(field)) or None

    if not data["project_no"]:
        errors["project_no"] = "项目编号不能为空"
    if not data["house_name"]:
        errors["house_name"] = "房屋名称不能为空"

    for field, (limit, label) in MAX_LENGTHS.items():
        value = data.get(field)
        if value and len(value) > limit:
            errors[field] = "%s不能超过 %d 个字符" % (label, limit)

    if data["test_date"] and not _is_valid_date(data["test_date"]):
        errors["test_date"] = "检测日期格式应为 YYYY-MM-DD"

    return data, errors


def create(data):
    """新建项目，返回新 id。项目编号重复由调用方捕获 IntegrityError 处理。"""
    with db.transaction() as conn:
        cursor = conn.execute(
            """
            INSERT INTO projects (project_no, house_name, house_address, client_org, test_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (data["project_no"], data["house_name"], data["house_address"],
             data["client_org"], data["test_date"]),
        )
        return cursor.lastrowid


def update(project_id, data):
    with db.transaction() as conn:
        cursor = conn.execute(
            """
            UPDATE projects
               SET project_no = ?, house_name = ?, house_address = ?,
                   client_org = ?, test_date = ?,
                   updated_at = datetime('now','localtime')
             WHERE id = ?
            """,
            (data["project_no"], data["house_name"], data["house_address"],
             data["client_org"], data["test_date"], project_id),
        )
        if cursor.rowcount == 0:
            raise LookupError("项目不存在：#%s" % project_id)


def delete(project_id):
    """删除项目：检测记录级联删除，关联缺陷报告 project_id 置空保留。"""
    with db.transaction() as conn:
        cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        if cursor.rowcount == 0:
            raise LookupError("项目不存在：#%s" % project_id)


def _is_valid_date(text):
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return False
    return True
