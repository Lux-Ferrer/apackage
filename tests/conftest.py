# -*- coding: utf-8 -*-
"""测试夹具。

所有测试都跑在 tmp_path 下的临时数据库上，不碰项目的 defects.db。
"""

from __future__ import annotations

import pytest

from webapp import create_app
from webapp import db as db_module


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
