# -*- coding: utf-8 -*-
"""应用工厂。

M0 底座：拆包完成（路由 / 数据访问 / Word 服务分离），启动时按 schema.sql 建库。
业务模块按 M1~M3 逐步填充，见 docs/management/后续开发计划.md。
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, request

from . import config, db


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)

    app.config.from_mapping(
        SECRET_KEY="dev",                       # 登录不在范围内，仅占位
        DB_PATH=str(config.DB_PATH),
        REPORTS_DIR=str(config.REPORTS_DIR),
        UPLOADS_DIR=str(config.UPLOADS_DIR),
        MAX_CONTENT_LENGTH=config.MAX_IMAGE_BYTES,   # 单张隐患图片 ≤20MB
    )
    if test_config:
        app.config.update(test_config)

    _ensure_directories(app)
    db.init_db(app.config["DB_PATH"])

    from .routes import defects, me, pages, projects, records, reports

    app.register_blueprint(pages.bp)
    app.register_blueprint(projects.bp)
    app.register_blueprint(records.bp)
    app.register_blueprint(defects.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(me.bp)

    app.teardown_appcontext(db.close_db)

    # 模板全局：隐患等级 → 徽标类名。报告管理列表 / 详情 / 项目详情三处都用它，
    # 做成全局常量而不是每个路由各传一次，避免漏传导致模板渲染报错。
    app.jinja_env.globals["risk_badge_classes"] = config.RISK_BADGE_CLASSES
    app.jinja_env.globals["app_info"] = config.APP_INFO
    app.context_processor(_navigation_context)
    return app


def _navigation_context() -> dict:
    """底部 Tab / 顶栏导航的高亮态：按端点前缀推导。

    放在 context_processor 里而不是每个 ``render_template`` 传参 —— 全站每个页面都需要它，
    漏传一处就会丢掉高亮，而这类 bug 只有肉眼能发现。
    """
    endpoint = request.endpoint or ""
    prefix = endpoint.split(".")[0]
    return {"active_tab": config.TAB_BY_ENDPOINT_PREFIX.get(prefix, config.DEFAULT_TAB)}


def _ensure_directories(app: Flask) -> None:
    for key in ("REPORTS_DIR", "UPLOADS_DIR"):
        Path(app.config[key]).mkdir(parents=True, exist_ok=True)
