# -*- coding: utf-8 -*-
"""从 Python 侧导出 M5 前端要用的**数据资产**，保证"只有一份真相源"。

产出（都是生成物，不要手改）：

- ``web/app/config.js``            业务预置数据 ← ``webapp/config.py``
- ``web/app/report/spec.js``       版式规格     ← ``webapp/resources/report_layout.json``
- ``web/assets/report_layout.json`` 同一份 JSON 的副本（供前端 fetch 与人工查看）

为什么用"生成 .js"而不是"运行时 import JSON"
--------------------------------------------
JSON 模块导入（``import data from './x.json' with { type: 'json' }``）在浏览器与 Node 里的
支持度不一，会给 PWA 与 Node 侧的差异清单工具带来无谓的兼容问题。生成成普通 ES 模块
（``export const CONFIG = {...}``）则两边都能直接 ``import``，不需要 fetch、不需要 fs。

同步性怎么保证：``web/tests/assets.test.mjs`` 会重新读 ``webapp/config.py`` 与
``report_layout.json`` 的当前值，与生成物逐键比对 —— 改了 Python 侧忘了跑本脚本，
测试会红。

用法::

    python tools/export_web_assets.py
    python tools/export_web_assets.py --check    # 只检查是否同步（CI/测试用，不同步则退出码 1）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 只读 webapp 的**数据**模块；不会创建应用、不会碰数据库文件。
# （webapp/__init__.py 在 import 时只定义 create_app，不执行任何副作用）
from webapp import config                                   # noqa: E402

WEB_DIR = ROOT / "web"
CONFIG_JS = WEB_DIR / "app" / "config.js"
SPEC_JS = WEB_DIR / "app" / "report" / "spec.js"
SPEC_JSON_COPY = WEB_DIR / "assets" / "report_layout.json"

HEADER = """/* 本文件由 tools/export_web_assets.py 生成，请勿手改。
 * 真相源：%s
 * 重新生成：python tools/export_web_assets.py
 */
"""


def config_payload() -> dict:
    """前端需要的业务预置数据（与 webapp/config.py 逐键一致）。"""
    return {
        # 模板
        "TEMPLATE_COLUMN": config.TEMPLATE_COLUMN,
        "TEMPLATE_BEAM": config.TEMPLATE_BEAM,
        "TEMPLATE_TYPES": list(config.TEMPLATE_TYPES),
        "TEMPLATE_NAMES": dict(config.TEMPLATE_NAMES),
        "TEMPLATE_TITLES": dict(config.TEMPLATE_TITLES),
        "TEMPLATE_SHORT_NAMES": dict(config.TEMPLATE_SHORT_NAMES),
        "REQUIREMENT_LABELS": dict(config.REQUIREMENT_LABELS),
        "REQUIREMENT_OPTIONS": {k: list(v) for k, v in config.REQUIREMENT_OPTIONS.items()},
        "FACE_SUGGESTIONS": {k: list(v) for k, v in config.FACE_SUGGESTIONS.items()},
        "THICKNESS_VALUE_COUNT": config.THICKNESS_VALUE_COUNT,
        "FACE_MAX_COUNT": config.FACE_MAX_COUNT,
        # 缺陷
        "RISK_LEVELS": list(config.RISK_LEVELS),
        "DEFAULT_RISK_LEVEL": config.DEFAULT_RISK_LEVEL,
        "DEFECT_TYPES": list(config.DEFECT_TYPES),
        "CUSTOM_DEFECT_OPTION": config.CUSTOM_DEFECT_OPTION,
        "RISK_BADGE_CLASSES": dict(config.RISK_BADGE_CLASSES),
        # 文案与文件名
        "EMPTY_TEXT": config.EMPTY_TEXT,
        "REPORT_FILENAME": config.REPORT_FILENAME,
        "ATTACHMENT_LABELS": dict(config.ATTACHMENT_LABELS),
        "ATTACHMENT_ORDER": list(config.ATTACHMENT_ORDER),
        "ATTACHMENT_EMPTY_FIELDS": list(config.ATTACHMENT_EMPTY_FIELDS),
        "ATTACHMENT_TITLE": config.ATTACHMENT_TITLE,
        "DEFAULT_REPORTER": dict(config.DEFAULT_REPORTER),
        # 图片
        "MAX_IMAGE_BYTES": config.MAX_IMAGE_BYTES,
        "ALLOWED_IMAGE_EXTENSIONS": list(config.ALLOWED_IMAGE_EXTENSIONS),
        "ALLOWED_IMAGE_FORMATS": list(config.ALLOWED_IMAGE_FORMATS),
        "THUMBNAIL_MAX_PIXELS": config.THUMBNAIL_MAX_PIXELS,
        "THUMBNAIL_JPEG_QUALITY": config.THUMBNAIL_JPEG_QUALITY,
        # 项目字段长度上限（原在 services/projects.py 的 MAX_LENGTHS）
        "PROJECT_FIELD_LIMITS": {
            "project_no": [50, "项目编号"],
            "house_name": [100, "房屋名称"],
            "house_address": [200, "房屋地点"],
            "client_org": [100, "委托单位"],
        },
    }


def _render_module(header_source: str, const_name: str, payload: dict) -> str:
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return "%s\nexport const %s = Object.freeze(%s);\n\nexport default %s;\n" % (
        HEADER % header_source, const_name, body, const_name)


def build(check_only: bool = False) -> int:
    sources = {
        CONFIG_JS: _render_module("webapp/config.py", "CONFIG", config_payload()),
        SPEC_JSON_COPY: json.dumps(config_payload_spec(), ensure_ascii=False, indent=2) + "\n",
        SPEC_JS: _render_module("webapp/resources/report_layout.json", "SPEC", config_payload_spec()),
    }

    stale = [path for path, text in sources.items()
             if not path.exists() or path.read_text(encoding="utf-8") != text]

    if check_only:
        if stale:
            print("以下生成物与真相源不同步，请运行：python tools/export_web_assets.py")
            for path in stale:
                print("  - %s" % path.relative_to(ROOT))
            return 1
        print("web/ 下的生成物与真相源一致 ✅")
        return 0

    for path, text in sources.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print("已生成 %s" % path.relative_to(ROOT))
    return 0


def config_payload_spec() -> dict:
    """版式规格：原样读 JSON（它本来就是语言中立的）。"""
    path = config.RESOURCE_DIR / "report_layout.json"
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 web/ 前端要用的数据资产")
    parser.add_argument("--check", action="store_true", help="只检查是否与真相源同步")
    args = parser.parse_args()
    return build(check_only=args.check)


if __name__ == "__main__":
    sys.exit(main())
