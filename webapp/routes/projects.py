# -*- coding: utf-8 -*-
"""项目管理与检测记录（M1 实现，当前为占位页）。"""

from __future__ import annotations

from flask import Blueprint, render_template

from .. import config

bp = Blueprint("projects", __name__, url_prefix="/projects")


@bp.get("/")
def index():
    """M1 占位：项目管理 CRUD 与立柱/横梁检测记录录入将在本模块实现。"""
    return render_template("projects/placeholder.html", config=config)
