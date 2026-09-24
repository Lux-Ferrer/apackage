# -*- coding: utf-8 -*-
"""检测记录录入：模板选择、表单、新增 / 编辑 / 删除。

编辑锁定（模板类型不可切换）在本模块体现两层：

- **路由层**：``edit`` / ``update`` 不接收任何模板参数，处理器也**不读取**表单里的
  ``template_type``；
- 模板类型的唯一来源是**数据库里的记录**，渲染与校验都用它。

第三层保证在服务层：``measurements.update_record`` 的 UPDATE 字段清单不含该列。
"""

from __future__ import annotations

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)

from .. import config
from ..services import measurements, thickness
from ..services import projects as project_service

bp = Blueprint("records", __name__)

KEEP_REQUIREMENT = "__keep__"      # 下拉里"保留历史条文"的哨兵值


def _project_or_404(project_id):
    project = project_service.get(project_id)
    if project is None:
        abort(404)
    return project


def _record_or_404(record_id):
    record = measurements.get_record(record_id)
    if record is None:
        abort(404)
    return record


# --------------------------------------------------------------------------
# 行构造（模板渲染用）
# --------------------------------------------------------------------------
def _row(index, face, readings):
    """一行检测面；``min_text`` 由服务端先算好，保证无 JS 时也能看到最小值。

    键名用 ``readings`` 而非 ``values``：Jinja 里 ``row.values`` 会命中 dict 自带的
    ``values()`` 方法，取值会静默变空。
    """
    return {
        "index": index,
        "face": face,
        "readings": readings,
        "min_text": thickness.face_min_text(readings),
    }


def _empty_rows(count: int = 1):
    return [
        _row(index, "", [""] * config.THICKNESS_VALUE_COUNT)
        for index in range(count)
    ]


def _rows_from_submitted(form):
    """校验失败回填：保留用户输入，并**保留原始下标**，使错误提示不错位。"""
    rows = []
    for index in range(config.FACE_MAX_COUNT):
        face = (form.get("face_%d" % index) or "").strip()
        readings = [
            (form.get("value_%d_%d" % (index, position)) or "").strip()
            for position in range(1, config.THICKNESS_VALUE_COUNT + 1)
        ]
        if not face and not any(readings):
            continue                                   # 空白行不回填（避免越填越长）
        rows.append(_row(index, face, readings))
    return rows or _empty_rows()


def _rows_from_record(record_id):
    rows = []
    for index, reading in enumerate(measurements.get_readings(record_id)):
        readings = [
            "" if value is None else thickness.format_mm(value)
            for value in thickness.readings_of_row(reading)
        ]
        rows.append(_row(index, reading["face"], readings))
    return rows or _empty_rows()


def _next_index(rows):
    return max((row["index"] for row in rows), default=-1) + 1


def _requirement_selection(raw):
    """下拉选中值归一化：'' -> None，数字 -> int，哨兵 -> 原样保留。"""
    text = (raw or "").strip()
    if text == KEEP_REQUIREMENT:
        return KEEP_REQUIREMENT
    try:
        return int(text)
    except ValueError:
        return None


CONSTRUCT_FIELDS = ("floor", "member_position", "size_result")


def _values(record=None, form=None):
    """构件级字段的回填值：优先用本次提交，其次用记录，最后空串。"""
    if form is not None:
        return {field: (form.get(field) or "") for field in CONSTRUCT_FIELDS}
    if record is not None:
        return {
            "floor": record["floor"],
            "member_position": record["member_position"],
            "size_result": record["size_result"] or "",
        }
    return {field: "" for field in CONSTRUCT_FIELDS}


def _table_errors(errors):
    """属于检测面表格的错误（面标签 / 读数），在表格上方集中提示。"""
    return [
        (field, message) for field, message in errors.items()
        if field.startswith("face_") or field.startswith("value_")
    ]


# --------------------------------------------------------------------------
# 渲染
# --------------------------------------------------------------------------
def _render_record_form(project, template_type, *, mode, record=None, rows=None,
                        errors=None, form=None, selected_requirement=None,
                        requirement_history=None):
    rows = rows or _empty_rows()
    errors = errors or {}
    return render_template(
        "records/form.html",
        project=project,
        template_type=template_type,
        template_title=config.TEMPLATE_TITLES[template_type],
        template_name=config.TEMPLATE_NAMES[template_type],
        requirement_options=config.REQUIREMENT_OPTIONS[template_type],
        requirement_label=config.REQUIREMENT_LABELS[template_type],
        face_suggestions=config.FACE_SUGGESTIONS[template_type],
        value_count=config.THICKNESS_VALUE_COUNT,
        face_max=config.FACE_MAX_COUNT,
        keep_requirement=KEEP_REQUIREMENT,
        mode=mode,
        record=record,
        rows=rows,
        next_index=_next_index(rows),
        values=_values(record=record, form=form),
        errors=errors,
        table_errors=_table_errors(errors),
        selected_requirement=selected_requirement,
        requirement_history=requirement_history,
    )


# --------------------------------------------------------------------------
# 模板选择 / 新增
# --------------------------------------------------------------------------
def _template_choices():
    """模板选择页的卡片数据。"""
    return [
        {
            "template_type": template_type,
            "name": config.TEMPLATE_NAMES[template_type],
            "title": config.TEMPLATE_TITLES[template_type],
            "faces": " / ".join(config.FACE_SUGGESTIONS[template_type]),
            "requirement_count": len(config.REQUIREMENT_OPTIONS[template_type]),
        }
        for template_type in config.TEMPLATE_TYPES
    ]


@bp.get("/projects/<int:project_id>/records/new")
def new(project_id):
    """无 ``?template=`` 时进模板选择页；带合法模板参数时进记录表单。"""
    project = _project_or_404(project_id)
    template_type = (request.args.get("template") or "").strip()
    if template_type not in config.TEMPLATE_TYPES:
        return render_template("records/choose_template.html", project=project,
                               choices=_template_choices())
    return _render_record_form(project, template_type, mode="create")


@bp.post("/projects/<int:project_id>/records/")
def create(project_id):
    project = _project_or_404(project_id)
    template_type = (request.args.get("template") or "").strip()
    if template_type not in config.TEMPLATE_TYPES:
        abort(400)

    data, errors = measurements.parse_record_form(request.form, template_type)
    if not errors:
        record_id = measurements.create_record(project_id, template_type, data)
        flash("检测记录已添加")
        return redirect(
            url_for("projects.detail", project_id=project_id) + "#record-%d" % record_id
        )

    return _render_record_form(
        project, template_type, mode="create",
        rows=_rows_from_submitted(request.form),
        errors=errors,
        form=request.form,
        selected_requirement=_requirement_selection(request.form.get("requirement_index")),
    ), 400


# --------------------------------------------------------------------------
# 编辑 / 更新 / 删除
# --------------------------------------------------------------------------
@bp.get("/records/<int:record_id>/edit")
def edit(record_id):
    record = _record_or_404(record_id)
    project = _project_or_404(record["project_id"])
    template_type = record["template_type"]              # 唯一来源：数据库

    selected = measurements.requirement_index_of(record["requirement_text"], template_type)
    history = record["requirement_text"] if (record["requirement_text"] and selected is None) else None

    return _render_record_form(
        project, template_type, mode="edit", record=record,
        rows=_rows_from_record(record_id),
        selected_requirement=selected,
        requirement_history=history,
    )


@bp.post("/records/<int:record_id>/update")
def update(record_id):
    record = _record_or_404(record_id)
    project = _project_or_404(record["project_id"])
    template_type = record["template_type"]              # 刻意不读表单里的 template_type

    data, errors = measurements.parse_record_form(request.form, template_type)
    if not errors:
        if request.form.get("requirement_index") == KEEP_REQUIREMENT:
            data["requirement_text"] = record["requirement_text"]
        try:
            measurements.update_record(record_id, data)
        except LookupError:
            abort(404)
        flash("检测记录已更新")
        return redirect(
            url_for("projects.detail", project_id=project["id"]) + "#record-%d" % record_id
        )

    return _render_record_form(
        project, template_type, mode="edit", record=record,
        rows=_rows_from_submitted(request.form),
        errors=errors,
        form=request.form,
        selected_requirement=_requirement_selection(request.form.get("requirement_index")),
    ), 400


@bp.post("/records/<int:record_id>/delete")
def delete(record_id):
    record = _record_or_404(record_id)
    try:
        measurements.delete_record(record_id)
    except LookupError:
        abort(404)
    flash("检测记录已删除")
    return redirect(url_for("projects.detail", project_id=record["project_id"]))
