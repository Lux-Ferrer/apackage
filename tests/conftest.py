# -*- coding: utf-8 -*-
"""测试夹具。

所有测试都跑在 tmp_path 下的临时数据库上，不碰项目的 defects.db。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 让 `pytest` 与 `python -m pytest` 都能导入 webapp / tools
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp import create_app          # noqa: E402
from webapp import db as db_module     # noqa: E402


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "DB_PATH": str(tmp_path / "test.db"),
        "REPORTS_DIR": str(tmp_path / "reports"),
        "UPLOADS_DIR": str(tmp_path / "uploads"),
    })


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def conn(tmp_path):
    """一个已建表的独立连接（不依赖 Flask 上下文）。"""
    path = tmp_path / "unit.db"
    db_module.init_db(path)
    connection = db_module.connect(path)
    yield connection
    connection.close()


@pytest.fixture
def ctx(app):
    """服务层测试用的应用上下文（db.get_db / db.transaction 需要它）。"""
    with app.app_context():
        yield
