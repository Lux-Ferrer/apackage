# -*- coding: utf-8 -*-
"""缺陷检测填报（M3：补齐隐患图片、相关规范、补充建议、绑定项目）。

校验分工与 M1 一致：**前端只做即时反馈，服务端才是权威**。
"""

from __future__ import annotations

from pathlib import Path

from flask import (Blueprint, abort, current_app, redirect, render_template,
                   request, send_file, url_for)

from .. import config
from ..services import defects as defect_service
from ..services import images
from ..services import projects as project_service
from ..services import word_report

bp = Blueprint("defects", __name__, url_prefix="/defects")


def _form_context(form, errors):
    return {
        "defect_types": config.DEFECT_TYPES,
        "risk_levels": config.RISK_LEVELS,
        "default_risk_level": config.DEFAULT_RISK_LEVEL,
        "custom_option": config.CUSTOM_DEFECT_OPTION,
        "projects": project_service.list_options(),
        "reporter": config.DEFAULT_REPORTER,
        "max_image_mb": config.MAX_IMAGE_BYTES // (1024 * 1024),
        "allowed_image_types": config.ALLOWED_IMAGE_EXTENSIONS,
        "form": form,
        "errors": errors,
    }


@bp.get("/new")
def new():
    return render_template("defects/form.html", **_form_context({}, {}))


@bp.post("/")
def create():
    data, errors = defect_service.parse_form(request.form)

    image = request.files.get("image")
    image_error = images.validate_upload(image)
    if image_error:
        errors["image"] = image_error

    if errors:
        return render_template("defects/form.html",
                               **_form_context(request.form, errors)), 400

    defect_id = defect_service.create(data, image)
    return redirect(url_for("defects.detail", defect_id=defect_id))


def _get_defect(defect_id: int):
    defect = defect_service.get(defect_id)
    if defect is None:
        abort(404)
    return defect


@bp.get("/<int:defect_id>")
def detail(defect_id: int):
    return render_template("defects/success.html", defect=_get_defect(defect_id))


@bp.get("/<int:defect_id>/image")
def image(defect_id: int):
    """隐患图片原图（供详情页预览；路径越界或文件缺失一律 404）。"""
    defect = _get_defect(defect_id)
    if not defect["image_path"]:
        abort(404)
    try:
        path = images.absolute_path(defect["image_path"])
    except ValueError:
        abort(404)
    if not path.exists():
        abort(404)
    return send_file(path)


@bp.get("/<int:defect_id>/export")
def export(defect_id: int):
    """单条缺陷记录导出（M0 迁移版，保留为内部工具；正式交付物是项目级报告）。"""
    defect = _get_defect(defect_id)
    reports_dir = Path(current_app.config["REPORTS_DIR"])
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / ("缺陷检测报告_%d.docx" % defect_id)

    word_report.save(word_report.build_defect_draft(defect), path)
    return send_file(path, as_attachment=True, download_name=path.name)
