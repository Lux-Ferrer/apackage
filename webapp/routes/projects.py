# -*- coding: utf-8 -*-
"""项目管理：列表 / 新建 / 详情 / 编辑 / 删除。"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, send_file, url_for)

from ..services import defects as defect_service
from ..services import measurements, word_report
from ..services import projects as project_service

bp = Blueprint("projects", __name__, url_prefix="/projects")

FORM_FIELDS = ("project_no", "house_name", "house_address", "client_org", "test_date")


def _project_or_404(project_id):
    project = project_service.get(project_id)
    if project is None:
        abort(404)
    return project


def _render_form(form, errors, project=None):
    return render_template("projects/form.html", form=form, errors=errors, project=project)


@bp.get("/")
def index():
    return render_template("projects/list.html", projects=project_service.list_with_counts())


@bp.get("/new")
def new():
    return _render_form({}, {})


@bp.post("/")
def create():
    data, errors = project_service.parse_form(request.form)
    if not errors:
        try:
            project_id = project_service.create(data)
        except sqlite3.IntegrityError:
            errors["project_no"] = "项目编号「%s」已存在，请换一个" % data["project_no"]
        else:
            flash("项目已创建：%s（%s）" % (data["house_name"], data["project_no"]))
            return redirect(url_for("projects.detail", project_id=project_id))
    return _render_form(request.form, errors), 400


@bp.get("/<int:project_id>")
def detail(project_id):
    project = _project_or_404(project_id)
    groups = measurements.grouped_by_template(project_id)
    counts = {group["template_type"]: group["count"] for group in groups}
    report_rows = defect_service.list_for_project(project_id)

    return render_template(
        "projects/detail.html",
        project=project,
        groups=groups,
        counts=counts,
        counts_text=measurements.describe_counts(counts),
        defects=report_rows,
        defect_count=len(report_rows),
        delete_message=project_service.build_delete_message(
            project, project_service.delete_impact(project_id)
        ),
    )


@bp.get("/<int:project_id>/edit")
def edit(project_id):
    project = _project_or_404(project_id)
    form = {field: project[field] for field in FORM_FIELDS}
    return _render_form(form, {}, project)


@bp.post("/<int:project_id>/update")
def update(project_id):
    project = _project_or_404(project_id)
    data, errors = project_service.parse_form(request.form)
    if not errors:
        try:
            project_service.update(project_id, data)
        except sqlite3.IntegrityError:
            errors["project_no"] = "项目编号「%s」已被其他项目使用" % data["project_no"]
        except LookupError:
            abort(404)
        else:
            flash("项目已更新")
            return redirect(url_for("projects.detail", project_id=project_id))
    return _render_form(request.form, errors, project), 400


@bp.post("/<int:project_id>/delete")
def delete(project_id):
    project = _project_or_404(project_id)
    try:
        project_service.delete(project_id)
    except LookupError:
        abort(404)
    flash("项目已删除：%s（%s）" % (project["house_name"], project["project_no"]))
    return redirect(url_for("projects.index"))


@bp.get("/<int:project_id>/export")
def export(project_id):
    """导出项目级 Word 检测报告：`项目编号_房屋名称_检测报告.docx`。

    ``attachments=1`` 时在正文之后追加关联缺陷报告的附页（每份独立成页）。
    附页里的图片是**导出时现压**的副本（渲染产物，不落库）。
    """
    project = _project_or_404(project_id)
    groups = measurements.grouped_by_template(project_id)
    report_rows = defect_service.list_for_project(project_id)
    with_attachments = request.args.get("attachments") == "1" and bool(report_rows)

    filename = word_report.report_filename(project)
    reports_dir = Path(current_app.config["REPORTS_DIR"])
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / filename

    with tempfile.TemporaryDirectory() as workdir:
        attachments = (defect_service.attachment_views(report_rows, workdir)
                       if with_attachments else None)
        doc = word_report.build_project_report(project, groups, attachments=attachments)
        word_report.save(doc, path)

    return send_file(path, as_attachment=True, download_name=filename)
