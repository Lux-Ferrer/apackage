# -*- coding: utf-8 -*-
"""首页与模块导航。"""

from __future__ import annotations

from flask import Blueprint, render_template

from .. import config

bp = Blueprint("pages", __name__)

# 模块进度（随里程碑推进更新）
# 注意：这里的文案是演示时会被看到的「项目现状」，改里程碑时一并刷新，
# 不要留下"待开发"字样指向已经完成的功能。
MODULES = (
    ("项目管理", "可用（M1）", "projects.index", True),
    ("立柱 / 横梁检测记录", "可用（M1，在项目详情内录入）", "projects.index", True),
    ("项目级 Word 导出", "可用（M2，与真实客户报告逐属性一致）", "projects.index", True),
    ("缺陷检测填报", "可用（M3，含隐患图片 / 规范 / 建议 / 绑定项目）", "defects.new", True),
    ("检测报告附页", "可用（M3，随项目导出追加）", "projects.index", True),
    ("报告管理", "可用（M4，列表 / 筛选 / 详情 / 删除）", "reports.index", True),
)


@bp.get("/")
def index():
    return render_template("index.html", modules=MODULES, config=config)
