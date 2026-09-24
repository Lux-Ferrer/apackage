# -*- coding: utf-8 -*-
"""SQLite 访问层：连接管理、建库、轻量查询助手。

约定：
- 连接一律开启 ``PRAGMA foreign_keys``（级联删除 / 置空依赖它，SQLite 默认关闭）；
- Flask 请求内用 :func:`get_db`，连接挂在 ``flask.g`` 上，请求结束自动关闭；
- 脚本/测试可直接用 :func:`connect` + :func:`init_db`，不依赖应用上下文。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import current_app, g

from . import config

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 1

# 旧版 PoC 库的 defects 表只有 6 列；新版多了这些列，用来识别"没重建的旧库"
_NEW_DEFECT_COLUMNS = ("project_id", "related_standards", "image_path", "reporter_name")


def connect(db_path=None) -> sqlite3.Connection:
    """打开一个 SQLite 连接（Row 工厂 + 外键约束）。"""
    path = Path(db_path) if db_path else config.DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path=None) -> None:
    """按 schema.sql 建表（幂等），并写入 schema 版本号。"""
    conn = connect(db_path)
    try:
        _reject_legacy_schema(conn)
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
        conn.commit()
    finally:
        conn.close()


def _reject_legacy_schema(conn) -> None:
    """检测到未重建的 PoC 旧库时给出明确指引，而不是静默产生错乱数据。"""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='defects'"
    ).fetchone()
    if row is None:
        return
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(defects)")}
    missing = [c for c in _NEW_DEFECT_COLUMNS if c not in columns]
    if missing:
        raise RuntimeError(
            "检测到旧版 PoC 数据库（defects 表缺少 %s）。"
            "请删除 defects.db 后重新启动（M0 搬迁时已备份为 defects.db.bak）。"
            % "、".join(missing)
        )


def schema_version(conn) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


# --------------------------------------------------------------------------
# Flask 集成
# --------------------------------------------------------------------------
def get_db() -> sqlite3.Connection:
    """取得当前请求的连接（懒创建）。"""
    if "db" not in g:
        g.db = connect(current_app.config.get("DB_PATH"))
    return g.db


def close_db(exc=None) -> None:
    """请求结束回收连接（注册为 teardown_appcontext）。"""
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


# --------------------------------------------------------------------------
# 查询助手（仅在应用/请求上下文内可用）
# --------------------------------------------------------------------------
def query_all(sql: str, params=()):
    return get_db().execute(sql, params).fetchall()


def query_one(sql: str, params=()):
    return get_db().execute(sql, params).fetchone()


def execute(sql: str, params=()) -> int:
    """执行写操作并提交，返回 lastrowid。"""
    conn = get_db()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.lastrowid
