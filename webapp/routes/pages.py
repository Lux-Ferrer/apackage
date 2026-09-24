# -*- coding: utf-8 -*-
"""首页与模块导航。"""

from __future__ import annotations

from flask import Blueprint, render_template

from .. import config

bp = Blueprint("pages", __name__)

# 模块进度（随里程碑推进更新）
MODULES = (
    ("项目管理", "可用（M1）", "projects.index", True),
    ("立柱 / 横梁检测记录", "可用（M1，在项目详情内录入）", "projects.index", True),
    ("缺陷检测填报", "可用（M0 迁移版）", "defects.new", True),
    ("项目级 Word 导出", "M2 待开发（底座已就绪）", None, False),
    ("检测报告附页", "M3 待开发", None, False),
)


@bp.get("/")
def index():
    return render_template("index.html", modules=MODULES, config=config)
