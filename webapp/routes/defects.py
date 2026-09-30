# -*- coding: utf-8 -*-
"""缺陷检测填报（需求报告 3.3；M3 补齐隐患图片、相关规范、补充建议、绑定项目）。

模块边界：这里只负责**写入**（表单 + 提交）与 M0 迁移过来的单条导出工具；
查看 / 管理（列表、详情、图片、缩略图、删除）都在 ``routes/reports.py``（需求 3.4）。

校验分工与 M1 一致：**前端只做即时反馈，服务端才是权威**。
"""

from __future__ import annotations

from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, send_file, url_for)

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
    flash("报告已保存")
    return redirect(url_for("reports.detail", report_id=defect_id))


def _get_defect(defect_id: int):
    defect = defect_service.get(defect_id)
    if defect is None:
        abort(404)
    return defect


@bp.get("/<int:defect_id>")
def legacy_detail(defect_id: int):
    """M3 期间的旧详情链接 → 报告管理详情。

    需求 3.4 把"查看报告"划归报告管理，所以详情页搬到了 ``/reports/<id>``；
    这里用 308（永久重定向，保留请求方法）兜住旧书签与历史链接。
    """
    return redirect(url_for("reports.detail", report_id=defect_id), code=308)


@bp.get("/<int:defect_id>/export")
def export(defect_id: int):
    """单条缺陷记录导出（M0 迁移版，保留为内部工具；正式交付物是项目级报告）。"""
    defect = _get_defect(defect_id)
    reports_dir = Path(current_app.config["REPORTS_DIR"])
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / ("缺陷检测报告_%d.docx" % defect_id)

    word_report.save(word_report.build_defect_draft(defect), path)
    return send_file(path, as_attachment=True, download_name=path.name)
