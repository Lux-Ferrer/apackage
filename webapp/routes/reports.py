# -*- coding: utf-8 -*-
"""报告管理（需求报告 3.4：列表 / 筛选 / 详情 / 删除）。

模块边界与需求对齐：
- **3.3 缺陷检测填报**（写入）留在 ``routes/defects.py``：``GET /defects/new``、``POST /defects/``；
- **3.4 报告管理**（查看 + 管理）在这个蓝图：``/reports/*``。

设计约定：**模板里不写业务逻辑**。所有派生字段（徽标类名、时间文案、缩略图 URL、
项目标签、图片是否存在）都由 :func:`_card` 预先算好，模板只做 ``{{ }}`` 输出。
这样将来把渲染搬到前端（静态壳 + JS）时，同一个 dict 直接 ``jsonify`` 出去即可，
不需要重新理解业务 —— 见 docs/management/M4-设计.md 第 6 节。
"""

from __future__ import annotations

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, send_file, url_for)

from .. import config
from ..services import defects as defect_service
from ..services import images

bp = Blueprint("reports", __name__, url_prefix="/reports")


def _report_or_404(report_id: int):
    report = defect_service.get(report_id)
    if report is None:
        abort(404)
    return report


# --------------------------------------------------------------------------
# 视图装配
# --------------------------------------------------------------------------
def _project_label(report) -> str:
    """绑定项目的显示文案；未绑定时为空串（模板据此决定要不要渲染这一行）。"""
    if not report["project_id"]:
        return ""
    return "%s（%s）" % (report["house_name"], report["project_no"])


def _card(report) -> dict:
    """一条报告的展示视图 —— 列表卡与将来的 JS 渲染器都只消费这个形状。

    故意做成纯函数（只依赖传入的 Row 与 Flask 的 url_for），便于单测各分支。
    """
    return {
        "id": report["id"],
        "defect_type": report["defect_type"],
        "project_part": report["project_part"],
        "risk_level": report["risk_level"],
        "badge_class": config.RISK_BADGE_CLASSES.get(report["risk_level"], "low"),
        "created_at_text": defect_service.format_report_time(report["created_at"]),
        "project_label": _project_label(report),
        "has_image": images.exists(report["image_path"]),
        "thumbnail_url": url_for("reports.thumbnail", report_id=report["id"]),
        "detail_url": url_for("reports.detail", report_id=report["id"]),
    }


def _level_param():
    """读取 ``?level=`` 筛选参数；非法值按"不筛选"处理并给出提示（不报 400）。

    ``?level=紧急`` 这种来自手打或旧链接，给错误页只会让人以为系统坏了；
    但也不能静默吞掉 —— 页面上会显示一行「未知的筛选值」提示。
    """
    level = (request.args.get("level") or "").strip()
    if not level:
        return None, None
    if level not in config.RISK_LEVELS:
        return None, "未知的筛选值「%s」，已显示全部报告。" % level
    return level, None


# --------------------------------------------------------------------------
# 列表
# --------------------------------------------------------------------------
@bp.get("/")
def index():
    level, warning = _level_param()

    reports = defect_service.list_reports(level)
    return render_template(
        "reports/list.html",
        cards=[_card(report) for report in reports],
        stats=defect_service.stats(),           # 恒为全量，不随筛选变化
        level=level,
        level_warning=warning,
        levels=config.RISK_LEVELS,
    )


# --------------------------------------------------------------------------
# 详情 / 图片
# --------------------------------------------------------------------------
@bp.get("/<int:report_id>")
def detail(report_id: int):
    # 用 get_with_project 而不是 get：详情页要显示绑定项目，且 _card 与列表页同一份实现
    report = defect_service.get_with_project(report_id)
    if report is None:
        abort(404)
    return render_template(
        "reports/detail.html",
        report=report,
        card=_card(report),
        original_name=images.original_name_from_path(report["image_path"]),
    )


@bp.get("/<int:report_id>/image")
def image(report_id: int):
    """隐患图片原图（详情页大图 / 点击看原图；路径越界或文件缺失一律 404）。"""
    report = _report_or_404(report_id)
    if not report["image_path"]:
        abort(404)
    try:
        path = images.absolute_path(report["image_path"])
    except ValueError:
        abort(404)
    if not path.exists():
        abort(404)
    return send_file(path)


@bp.get("/<int:report_id>/thumbnail")
def thumbnail(report_id: int):
    """列表缩略图：内存现压的 JPEG 字节（不落盘、不落库）。

    ``Cache-Control: immutable`` 的依据：落盘名含 uuid 前缀，且填报只有「新增」
    没有「改图」，所以同一个 URL 对应的字节在生命周期内不可能变化。
    """
    report = _report_or_404(report_id)
    data = images.thumbnail_bytes(report["image_path"]) if report["image_path"] else None
    if data is None:
        abort(404)
    response = current_app.response_class(data, mimetype="image/jpeg")
    response.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return response


# --------------------------------------------------------------------------
# 删除
# --------------------------------------------------------------------------
@bp.post("/<int:report_id>/delete")
def delete(report_id: int):
    try:
        report = defect_service.delete(report_id)
    except LookupError:
        abort(404)
    flash("报告已删除：#%d（%s）" % (report["id"], report["defect_type"]))
    return redirect(url_for("reports.index"))
