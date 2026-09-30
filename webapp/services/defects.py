# -*- coding: utf-8 -*-
"""缺陷检测报告：表单解析、读写、附页渲染数据装配。

分层约定与检测记录一致：
- :func:`parse_form` 是纯函数（不碰请求上下文），便于单测；
- 图片"落盘 + 入库"在一个逻辑单元里：**入库失败会删掉刚落的文件**，不留孤儿；
- 附页渲染数据（:func:`attachment_views`）在这里装配，``word_report`` 只负责排版。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .. import config, db
from . import images
from . import word_report as wr

CUSTOM_OPTION = config.CUSTOM_DEFECT_OPTION


def _clean(value):
    return "" if value is None else str(value).strip()


# --------------------------------------------------------------------------
# 表单解析与校验
# --------------------------------------------------------------------------
def parse_form(form):
    """解析缺陷填报表单（**不含图片**，图片由 :func:`images.validate_upload` 单独校验）。

    返回 ``(data, errors)``；errors 的键即表单字段名，便于模板就地报错。
    """
    errors = {}

    defect_type = _clean(form.get("defect_type"))
    if defect_type == CUSTOM_OPTION:
        defect_type = _clean(form.get("custom_defect_type"))
        if not defect_type:
            errors["custom_defect_type"] = "选择了「其他」时，请填写自定义缺陷类型"

    project_part = _clean(form.get("project_part"))
    risk_level = _clean(form.get("risk_level")) or config.DEFAULT_RISK_LEVEL
    rectification_plan = _clean(form.get("rectification_plan"))

    if not defect_type:
        errors["defect_type"] = "缺陷类型不能为空"
    if risk_level not in config.RISK_LEVELS:
        errors["risk_level"] = "隐患等级无效"
    if not project_part:
        errors["project_part"] = "工程部位不能为空"
    if not rectification_plan:
        errors["rectification_plan"] = "整改方案不能为空"

    project_id = _clean(form.get("project_id"))
    bound = None
    if project_id:
        if not project_id.isdigit() or not db.query_one(
                "SELECT id FROM projects WHERE id = ?", (int(project_id),)):
            errors["project_id"] = "绑定的项目不存在"
        else:
            bound = int(project_id)

    data = {
        "defect_type": defect_type,
        "project_part": project_part,
        "risk_level": risk_level,
        "rectification_plan": rectification_plan,
        "related_standards": _clean(form.get("related_standards")) or None,
        "extra_advice": _clean(form.get("extra_advice")) or None,
        "project_id": bound,
        "reporter_name": config.DEFAULT_REPORTER["name"],
        "reporter_department": config.DEFAULT_REPORTER["department"],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return data, errors


# --------------------------------------------------------------------------
# 写入
# --------------------------------------------------------------------------
def create(data, image_storage) -> int:
    """保存一条缺陷报告（含隐患图片）。

    图片先落盘再入库；**入库失败时把刚落的文件删掉**，避免留下孤儿文件。
    """
    image_path = images.save_upload(image_storage)
    try:
        with db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO defects
                    (project_id, defect_type, project_part, risk_level, rectification_plan,
                     related_standards, extra_advice, reporter_name, reporter_department,
                     image_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["project_id"], data["defect_type"], data["project_part"],
                 data["risk_level"], data["rectification_plan"], data["related_standards"],
                 data["extra_advice"], data["reporter_name"], data["reporter_department"],
                 image_path, data["created_at"]),
            )
            return cursor.lastrowid
    except Exception:
        images.remove(image_path)
        raise


# --------------------------------------------------------------------------
# 读取
# --------------------------------------------------------------------------
def get(defect_id):
    return db.query_one("SELECT * FROM defects WHERE id = ?", (defect_id,))


def get_with_project(report_id):
    """单条报告 + 绑定项目的编号/名称（与 :func:`list_reports` 同样的列集）。

    详情页的卡片视图与列表页共用 :func:`routes.reports._card`，所以这里也要带上
    项目两列 —— 否则 `_card` 取 ``house_name`` 会 IndexError。
    """
    return db.query_one(
        """
        SELECT d.*, p.project_no, p.house_name
          FROM defects d
          LEFT JOIN projects p ON p.id = d.project_id
         WHERE d.id = ?
        """,
        (report_id,),
    )


def list_for_project(project_id):
    """项目关联的缺陷报告（倒序）。删除项目时 project_id 被置空，故不会出现在这里。"""
    return db.query_all(
        "SELECT * FROM defects WHERE project_id = ? ORDER BY created_at DESC, id DESC",
        (project_id,),
    )


def count_for_project(project_id) -> int:
    row = db.query_one("SELECT COUNT(*) AS total FROM defects WHERE project_id = ?",
                       (project_id,))
    return row["total"] if row else 0


# --------------------------------------------------------------------------
# 报告管理（需求报告 3.4：列表 / 筛选 / 顶部统计 / 删除）
#
# 本组函数只读 + 一个 DELETE，与上面那条"填报 → 附页排版"的链路（parse_form /
# create / attachment_views / field_values / image_file_text / format_report_time）
# 没有任何交集 —— 后者的产物被冻结基线 tests/fixtures/generated_baseline.docx
# 与 tests/test_attachment_export.py 双重锁住，M4 一个字符都不动。
# --------------------------------------------------------------------------
def list_reports(risk_level=None):
    """报告列表（倒序），附带绑定项目的编号与名称。

    - ``LEFT JOIN`` 而不是内连接：缺陷报告可以不绑项目，内连接会把它们静默丢掉；
    - 按需拼 ``WHERE`` 而不是 ``(? IS NULL OR ...)``：后者会让 ``idx_defects_risk`` 失效；
    - ``created_at`` 精度只到秒，同秒内靠 ``id DESC`` 兜底，否则列表顺序会抖动。
    """
    sql = ["""
        SELECT d.*, p.project_no, p.house_name
          FROM defects d
          LEFT JOIN projects p ON p.id = d.project_id
    """]
    params = []
    if risk_level:
        sql.append("WHERE d.risk_level = ?")
        params.append(risk_level)
    sql.append("ORDER BY d.created_at DESC, d.id DESC")
    return db.query_all(" ".join(sql), tuple(params))


def stats() -> dict:
    """顶部统计：总数 + 高/中/低。

    一条 SQL 算完，**恒为全量**（不受列表筛选影响，需求 3.4b 与 3.4c 是两件事）。
    ``COALESCE`` 不可省：空表时 ``COUNT(*)`` 是 0，而 ``SUM(...)`` 对零行返回 NULL，
    页面会显示成「高 None」。
    """
    row = db.query_one(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN risk_level = '高' THEN 1 ELSE 0 END), 0) AS high,
               COALESCE(SUM(CASE WHEN risk_level = '中' THEN 1 ELSE 0 END), 0) AS medium,
               COALESCE(SUM(CASE WHEN risk_level = '低' THEN 1 ELSE 0 END), 0) AS low
          FROM defects
        """
    )
    if row is None:
        return {"total": 0, "high": 0, "medium": 0, "low": 0}
    return dict(row)


def delete(report_id: int):
    """删除一份报告：先落库删除，提交后再尽力删掉隐患图片。

    **顺序不能反**：先删文件的话，一旦 DELETE 失败就会留下一条指向不存在图片的记录
    （用户可见的数据损坏）；按这个顺序最坏只留下一个不可见的孤儿文件。

    需求 3.4e 的"删除后自动解除项目关联"不需要额外 SQL —— 关联就存在这一行的
    ``project_id`` 上，删掉这行关联自然消失，项目详情页也就不再列出它。
    """
    row = get(report_id)
    if row is None:
        raise LookupError("报告不存在：#%s" % report_id)

    with db.transaction() as conn:
        cursor = conn.execute("DELETE FROM defects WHERE id = ?", (report_id,))
        if cursor.rowcount == 0:
            raise LookupError("报告不存在：#%s" % report_id)

    images.remove(row["image_path"])      # remove() 本身吞掉缺失/越界，不会让删除失败
    return row


def delete_all() -> dict:
    """清除全部报告（需求 3.7c「清除全部报告」）。返回 ``{reports, images}``。

    与 :func:`delete` 同一套顺序：**先把行读出来、删库提交、再删文件** ——
    反过来的话一旦 DELETE 失败就会留下指向不存在图片的记录（用户可见的数据损坏）。
    这里先把全部 image_path 取出来，正是为了这个顺序。

    不可恢复，调用方必须已经过二次确认（``templates/me/index.html`` 的确认弹窗）。
    """
    rows = db.query_all("SELECT id, image_path FROM defects")
    if not rows:
        return {"reports": 0, "images": 0}

    with db.transaction() as conn:
        conn.execute("DELETE FROM defects")

    removed_images = 0
    for row in rows:
        if row["image_path"]:
            images.remove(row["image_path"])
            removed_images += 1
    return {"reports": len(rows), "images": removed_images}


# --------------------------------------------------------------------------
# 附页渲染数据
# --------------------------------------------------------------------------
def format_report_time(value) -> str:
    """报告时间按 ``yyyy-MM-dd HH:mm`` 显示（需求报告 4.4）。"""
    text = _clean(value)
    return text[:16] if len(text) >= 16 else text


def attachment_views(rows, workdir=None) -> list:
    """把缺陷行转成附页渲染数据。

    ``workdir`` 给出时会**现压**图片副本（渲染产物，不落库）；压不出来就标记缺失，
    由排版层降级显示，绝不让整份报告失败。
    """
    spec = wr.ATTACHMENT_SPEC
    views = []
    for row in rows:
        relative = row["image_path"]
        prepared = (images.export_copy(relative, workdir,
                                       max_pixels=int(spec["imageMaxPixels"]),
                                       quality=int(spec["imageJpegQuality"]))
                    if (workdir and relative) else None)

        width_twips = height_twips = 0
        if prepared:
            width_twips, height_twips = wr.fit_image_twips(prepared["width_px"],
                                                          prepared["height_px"])
        views.append({
            "defect": row,
            "original_name": images.original_name_from_path(relative),
            "image_path": prepared["path"] if prepared else None,
            "image_width_twips": width_twips,
            "image_height_twips": height_twips,
            "compressed": bool(prepared and prepared["compressed"]),
            "missing": bool(relative and not prepared),
        })
    return views


def image_file_text(view) -> str:
    """「图片文件」行的内容：原文件名（可追溯）+ 是否压缩 / 是否缺失。"""
    name = view.get("original_name")
    if not name:
        return config.EMPTY_TEXT
    if view.get("missing"):
        return "%s（文件缺失）" % name
    return "%s（已压缩）" % name if view.get("compressed") else name


def field_values(view) -> dict:
    """附页信息表的取值：按 :data:`config.ATTACHMENT_ORDER` 组装。"""
    defect = view["defect"]
    empty = config.EMPTY_TEXT
    return {
        "defect_type": defect["defect_type"],
        "project_part": defect["project_part"],
        "risk_level": defect["risk_level"],
        "rectification_plan": defect["rectification_plan"],
        "extra_advice": _clean(defect["extra_advice"]) or empty,
        "related_standards": _clean(defect["related_standards"]) or empty,
        "reporter": "%s（%s）" % (defect["reporter_name"], defect["reporter_department"]),
        "reported_at": format_report_time(defect["created_at"]),
        "image_file": image_file_text(view),
    }
