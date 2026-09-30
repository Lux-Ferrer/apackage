# -*- coding: utf-8 -*-
"""「我的」（需求报告 3.7）。

范围对照（详见 docs/management/UI-设计.md 第 1.4 节）：

- a) 用户信息卡 —— 做。取 ``config.DEFAULT_REPORTER``；工号为空则不显示那一行（3.7a"有则显示"）；
- b) 数据概览 —— 做，但**换内容**：速记在范围外，改为 项目数 / 检测记录数 / 报告数；
- c) 数据管理：清除全部**速记** —— 不做（速记范围外）；
- c) 数据管理：清除全部**报告** —— 做，见 :func:`clear_reports`；
- d) 退出登录 —— 不做（登录范围外）；
- e) 应用信息 —— 做，并承载原首页的「模块进度」表（``pages.about``）。
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, url_for

from .. import config, db
from ..services import defects as defect_service

bp = Blueprint("me", __name__, url_prefix="/me")

# 数据概览的计数来源。表名是硬编码字面量（不是用户输入），拼接安全。
_OVERVIEW_TABLES = (("projects", "projects"),
                    ("records", "measurement_records"),
                    ("reports", "defects"))


def overview() -> dict:
    """数据概览：项目数 / 检测记录数 / 报告数（每条一次 COUNT，共 3 次查询）。"""
    result = {}
    for key, table in _OVERVIEW_TABLES:
        row = db.query_one("SELECT COUNT(*) AS total FROM %s" % table)
        result[key] = row["total"] if row else 0
    return result


@bp.get("/")
def index():
    return render_template(
        "me/index.html",
        reporter=config.DEFAULT_REPORTER,
        overview=overview(),
    )


@bp.post("/reports/clear")
def clear_reports():
    """清除全部缺陷报告（含隐患图片）。不可恢复，模板侧有二次确认弹窗。

    数据管理是本应用唯一的破坏性入口，所以这里把"删了什么"如实回显：
    条数 + 项目关联一并消失（需求 3.4e 的语义）。
    """
    removed = defect_service.delete_all()
    if removed["reports"]:
        flash("已清除全部报告：%d 份（其中 %d 份附有隐患图片，图片文件已一并删除）"
              % (removed["reports"], removed["images"]))
    else:
        flash("没有可清除的报告")
    return redirect(url_for("me.index"))
