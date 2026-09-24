# -*- coding: utf-8 -*-
"""缺陷检测填报。

M0：把 PoC 的表单/校验/存储/导出迁移进蓝图，字段保持 4 项必填。
M3：补齐隐患图片、相关规范、补充建议、绑定项目，并把导出换成"检测报告附页"格式。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import (Blueprint, abort, current_app, redirect, render_template,
                   request, send_file, url_for)

from .. import config, db
from ..services import word_report

bp = Blueprint("defects", __name__, url_prefix="/defects")


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------
def validate_form(form):
    """校验填报表单，返回 (数据字典, 错误信息)。"""
    defect_type = (form.get("defect_type") or "").strip()
    if defect_type == config.CUSTOM_DEFECT_OPTION:
        defect_type = (form.get("custom_defect_type") or "").strip()
        if not defect_type:
            return None, "选择了「其他」时，请填写自定义缺陷类型"

    project_part = (form.get("project_part") or "").strip()
    risk_level = (form.get("risk_level") or config.DEFAULT_RISK_LEVEL).strip()
    rectification_plan = (form.get("rectification_plan") or "").strip()

    if not defect_type:
        return None, "缺陷类型不能为空"
    if risk_level not in config.RISK_LEVELS:
        return None, "隐患等级无效"
    if not project_part:
        return None, "工程部位不能为空"
    if not rectification_plan:
        return None, "整改方案不能为空"

    data = {
        "defect_type": defect_type,
        "project_part": project_part,
        "risk_level": risk_level,
        "rectification_plan": rectification_plan,
        "reporter_name": config.DEFAULT_REPORTER["name"],
        "reporter_department": config.DEFAULT_REPORTER["department"],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return data, None


def _form_context(form, error):
    return {
        "defect_types": config.DEFECT_TYPES,
        "risk_levels": config.RISK_LEVELS,
        "default_risk_level": config.DEFAULT_RISK_LEVEL,
        "custom_option": config.CUSTOM_DEFECT_OPTION,
        "form": form,
        "error": error,
    }


# --------------------------------------------------------------------------
# 路由
# --------------------------------------------------------------------------
@bp.get("/new")
def new():
    return render_template("defects/form.html", **_form_context({}, None))


@bp.post("/")
def create():
    data, error = validate_form(request.form)
    if error:
        return render_template("defects/form.html",
                               **_form_context(request.form, error)), 400

    defect_id = db.execute(
        """
        INSERT INTO defects
            (defect_type, project_part, risk_level, rectification_plan,
             reporter_name, reporter_department, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (data["defect_type"], data["project_part"], data["risk_level"],
         data["rectification_plan"], data["reporter_name"],
         data["reporter_department"], data["created_at"]),
    )
    return redirect(url_for("defects.detail", defect_id=defect_id))


def _get_defect(defect_id: int):
    defect = db.query_one("SELECT * FROM defects WHERE id = ?", (defect_id,))
    if defect is None:
        abort(404)
    return defect


@bp.get("/<int:defect_id>")
def detail(defect_id: int):
    return render_template("defects/success.html", defect=_get_defect(defect_id))


@bp.get("/<int:defect_id>/export")
def export(defect_id: int):
    """导出单条缺陷记录为 Word（M0 临时版：A4 底座；M3 换成附页格式）。"""
    defect = _get_defect(defect_id)
    reports_dir = Path(current_app.config["REPORTS_DIR"])
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / ("缺陷检测报告_%d.docx" % defect_id)

    word_report.save(word_report.build_defect_draft(defect), path)
    return send_file(path, as_attachment=True, download_name=path.name)
