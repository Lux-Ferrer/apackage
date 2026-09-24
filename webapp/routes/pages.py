# -*- coding: utf-8 -*-
"""首页与模块导航。"""

from __future__ import annotations

from flask import Blueprint, render_template

from .. import config

bp = Blueprint("pages", __name__)

# 模块进度（M0 基线，随里程碑推进更新）
MODULES = (
    ("缺陷检测填报", "可用（M0 迁移完成）", "defects.new", True),
    ("项目管理", "M1 待开发", "projects.index", False),
    ("立柱 / 横梁检测记录", "M1 待开发", "projects.index", False),
    ("项目级 Word 导出", "M2 待开发（底座已就绪）", "projects.index", False),
    ("检测报告附页", "M3 待开发", "projects.index", False),
)


@bp.get("/")
def index():
    return render_template("index.html", modules=MODULES, config=config)
