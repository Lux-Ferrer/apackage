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


@pytest.fixture
def make_image():
    """现场生成一张小图片用于上传（不向仓库提交二进制）。

    返回可直接塞进 Flask test client 的 ``(BytesIO, filename)`` 元组。
    """
    import io

    from PIL import Image

    def _make(size=(8, 8), image_format="PNG", color=(200, 30, 30), filename=None):
        buffer = io.BytesIO()
        Image.new("RGB", size, color).save(buffer, image_format)
        buffer.seek(0)
        return (buffer, filename or ("sample.%s" % image_format.lower()))

    return _make


@pytest.fixture
def make_upload():
    """构造可直接传给**服务层**的 FileStorage 替身（只需 filename 与 stream）。"""
    import io

    from PIL import Image

    class _Storage:
        def __init__(self, data, filename):
            self.filename = filename
            self.stream = io.BytesIO(data)

    def _make(size=(8, 8), image_format="PNG", filename=None, data=None):
        if data is None:
            buffer = io.BytesIO()
            Image.new("RGB", size, (200, 30, 30)).save(buffer, image_format)
            data = buffer.getvalue()
        return _Storage(data, filename or ("sample.%s" % image_format.lower()))

    return _make
