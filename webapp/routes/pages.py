# -*- coding: utf-8 -*-
"""首页落地与「关于」页。

- ``/`` **重定向到「项目」Tab** —— 首屏是工具本身，不是开发状态表；
- ``/about`` 是原来的「模块进度」表，入口在「我的 → 应用信息」。
  它在答辩时有用（一屏展示范围符合性与里程碑进度），但不该挡在日常使用前面。
"""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, url_for

from .. import config

bp = Blueprint("pages", __name__)

# 模块进度（演示时会被看到的「项目现状」，改里程碑时一并刷新，
# 不要留下"待开发"字样指向已经完成的功能 —— 有测试锁住这一点）
MODULES = (
    ("项目管理", "可用（M1）", "projects.index", True),
    ("立柱 / 横梁检测记录", "可用（M1，在项目详情内录入）", "projects.index", True),
    ("项目级 Word 导出", "可用（M2，与真实客户报告逐属性一致）", "projects.index", True),
    ("缺陷检测填报", "可用（M3，含隐患图片 / 规范 / 建议 / 绑定项目）", "defects.new", True),
    ("检测报告附页", "可用（M3，随项目导出追加）", "projects.index", True),
    ("报告管理", "可用（M4，列表 / 筛选 / 详情 / 删除）", "reports.index", True),
    ("移动端界面", "可用（UI，底部 Tab + 检测面折叠录入）", "projects.index", True),
)


@bp.get("/")
def index():
    """落地页 = 「项目」Tab。"""
    return redirect(url_for("projects.index"))


@bp.get("/about")
def about():
    return render_template("about.html", modules=MODULES, config=config)
