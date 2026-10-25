# -*- coding: utf-8 -*-
"""从 Python 侧导出 M5 前端要用的**数据资产**，保证"只有一份真相源"。

产出（都是生成物，不要手改）：

- ``web/app/config.js``            业务预置数据 ← ``webapp/config.py``
- ``web/app/report/spec.js``       版式规格     ← ``webapp/resources/report_layout.json``
- ``web/assets/report_layout.json`` 同一份 JSON 的副本（供前端 fetch 与人工查看）
- ``web/styles/app.css``         **界面样式** ← ``webapp/static/css/app.css``

为什么连 CSS 也生成
-------------------
M5 的前端要"长得跟 UI 阶段定下的壳一模一样"。把 CSS 手抄一份到 ``web/`` 会有两个真相源，
改了 Flask 侧忘了同步就会**两边慢慢走样**，而且几乎不可能靠肉眼发现。
生成一份 + ``--check`` 就能把"走样"变成一条会红的检查。
M5 自己新增的样式写在**手写文件** ``web/styles/m5.css`` 里（不参与生成），
这样"移植的"与"新增的"在文件层面就分开了。

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
import hashlib
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
STYLE_CSS = WEB_DIR / "styles" / "app.css"
SHELL_JS = WEB_DIR / "assets" / "shell.js"

SOURCE_CSS = ROOT / "webapp" / "static" / "css" / "app.css"

# ---- vendored 第三方库（浏览器端没有打包器，靠 importmap 把裸名指到这里）----
VENDOR_DIR = WEB_DIR / "vendor"
NODE_MODULES = ROOT / "node_modules"
VENDOR_FILES = {
    # 目标文件名 → node_modules 里的源文件
    "docx.mjs": NODE_MODULES / "docx" / "dist" / "index.mjs",
    "jszip.min.js": NODE_MODULES / "jszip" / "dist" / "jszip.min.js",
}
VENDOR_NOTE = (
    "/* vendored：由 tools/export_web_assets.py 从 node_modules 复制，请勿手改。\n"
    " * 来源：%s\n"
    " * 为什么 vendor 而不是用 CDN：本工具可能在没有外网的工地上用（需求 1.2），\n"
    " *   而且 M5-5 的 Service Worker 要把它一起缓存成离线可用的应用壳。\n"
    " * `python tools/export_web_assets.py --check` 会在依赖升级后提醒重新 vendor。\n"
    " */\n"
)

# ---- 二进制资产（原样复制；前端 fetch 它们）----
BINARY_ASSETS = {
    # 目标 → 源
    WEB_DIR / "assets" / "report_base.docx": ROOT / "webapp" / "resources" / "report_base.docx",
}

HEADER = """/* 本文件由 tools/export_web_assets.py 生成，请勿手改。
 * 真相源：%s
 * 重新生成：python tools/export_web_assets.py
 */
"""

CSS_HEADER = """/* 本文件由 tools/export_web_assets.py 生成，请勿手改。
 * 真相源：webapp/static/css/app.css
 * 重新生成：python tools/export_web_assets.py
 *
 * 为什么要生成而不是手抄：M5 的前端必须"长得跟 UI 阶段定下的壳一模一样"，
 * 手抄一份就有两个真相源，改了 Flask 侧忘了同步会慢慢走样（而且肉眼看不出来）。
 * M5 自己新增的样式在手写的 web/styles/m5.css 里，不混进来。
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
        "NOTE_TEXT": config.NOTE_TEXT,
        "PROJECT_INFO_FIELDS": [list(item) for item in config.PROJECT_INFO_FIELDS],
        "REPORT_FILENAME": config.REPORT_FILENAME,
        "ATTACHMENT_LABELS": dict(config.ATTACHMENT_LABELS),
        "ATTACHMENT_ORDER": list(config.ATTACHMENT_ORDER),
        "ATTACHMENT_EMPTY_FIELDS": list(config.ATTACHMENT_EMPTY_FIELDS),
        "ATTACHMENT_TITLE": config.ATTACHMENT_TITLE,
        "DEFAULT_REPORTER": dict(config.DEFAULT_REPORTER),
        # 「我的 / 关于」页要显示的应用信息（需求 3.7e）
        "APP_INFO": dict(config.APP_INFO),
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


def shell_assets() -> list:
    """离线可用所需的**全部文件**（相对 ``web/``，正斜杠，排序）。

    为什么要"算出来"而不是手写：Service Worker 最常见的失败就是**漏了一个文件** ——
    在线时一切正常，一断网就白屏，而且很难复现。这里按目录规则扫一遍，
    ``web/tests/pwa.test.mjs`` 再反向核对"源码里 import 到的每个模块都在清单里"。

    规则是**列举式**的（不是"扫全盘"）：只把运行时真正会 fetch 的东西放进去。
    ``tests/``、``assets/fixture_data.json``（闸门用）、``assets/report_layout.json``
    （只是给人和工具看的副本）都不进 —— 少缓存几十 KB，也少一份"到底是哪份"的困惑。
    """
    included = []

    def add(relative: Path) -> None:
        included.append(relative.as_posix())

    add(Path("index.html"))
    add(Path("manifest.webmanifest"))
    for name in ("app.css", "m5.css"):
        if (WEB_DIR / "styles" / name).exists():
            add(Path("styles") / name)
    add(Path("assets/report_base.docx"))
    for path in sorted((WEB_DIR / "app").rglob("*.js")):
        add(path.relative_to(WEB_DIR))
    for path in sorted((WEB_DIR / "vendor").glob("*")):
        if path.is_file():
            add(path.relative_to(WEB_DIR))
    for path in sorted((WEB_DIR / "icons").glob("*.png")):
        add(path.relative_to(WEB_DIR))
    return sorted(included)


def shell_version(assets: list) -> str:
    """内容指纹：任何一个被缓存的文件变了，版本号就变 → 安装新 SW、清掉旧缓存。"""
    digest = hashlib.sha256()
    for relative in assets:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((WEB_DIR / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:12]


def vendor_entries() -> dict:
    """要复制的第三方构建产物：``目标路径 → (源路径, 版本号)``。

    ``node_modules`` 不存在时返回空（没装 JS 依赖的机器上不该因此红掉 Python 侧的检查）。
    """
    entries = {}
    for target_name, source in VENDOR_FILES.items():
        if not source.exists():
            continue
        entries[VENDOR_DIR / target_name] = (source, package_version(source))
    return entries


def package_version(source: Path) -> str:
    """从 ``node_modules/<pkg>/package.json`` 读版本号（写进 vendor 文件头，便于追溯）。"""
    for parent in source.parents:
        manifest = parent / "package.json"
        if manifest.exists():
            try:
                return str(json.loads(manifest.read_text(encoding="utf-8")).get("version", "?"))
            except (ValueError, OSError):
                return "?"
    return "?"


def build(check_only: bool = False) -> int:
    sources = {
        CONFIG_JS: _render_module("webapp/config.py", "CONFIG", config_payload()),
        SPEC_JSON_COPY: json.dumps(config_payload_spec(), ensure_ascii=False, indent=2) + "\n",
        SPEC_JS: _render_module("webapp/resources/report_layout.json", "SPEC", config_payload_spec()),
        STYLE_CSS: CSS_HEADER + style_source(),
        SHELL_JS: shell_source(),
    }

    stale = [path for path, text in sources.items()
             if not path.exists() or path.read_text(encoding="utf-8") != text]

    # vendored 第三方库：二进制/压缩件，按字节比对
    vendor = {path: data for path, (source, data) in vendor_payloads().items()}
    stale += [path for path, data in vendor.items()
              if not path.exists() or path.read_bytes() != data]

    # 二进制资产（底座 docx）：原样复制，按字节比对
    assets = {path: source.read_bytes() for path, source in BINARY_ASSETS.items()}
    stale += [path for path, data in assets.items()
              if not path.exists() or path.read_bytes() != data]

    if check_only:
        if stale:
            print("以下生成物与真相源不同步，请运行：python tools/export_web_assets.py")
            for path in stale:
                print("  - %s" % path.relative_to(ROOT))
            return 1
        print("web/ 下的生成物与真相源一致 ✅（含 %d 个 vendored 库、%d 个二进制资产）"
              % (len(vendor), len(assets)))
        if not vendor:
            print("  ⚠ 没找到 node_modules，跳过第三方库比对（先 `npm install`）")
        return 0

    for path, text in sources.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print("已生成 %s" % path.relative_to(ROOT))

    for path, data in vendor.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print("已 vendor %s（%d KB）" % (path.relative_to(ROOT), len(data) // 1024))

    for path, data in assets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print("已复制 %s（%d KB）" % (path.relative_to(ROOT), len(data) // 1024))
    return 0


def vendor_payloads() -> dict:
    """``目标路径 → (源路径, 带版本头的字节)``。"""
    payloads = {}
    for target, (source, version) in vendor_entries().items():
        header = (VENDOR_NOTE % (source.relative_to(ROOT).as_posix()
                                 + "（v%s）" % version)).encode("utf-8")
        payloads[target] = (source, header + source.read_bytes())
    return payloads


def config_payload_spec() -> dict:
    """版式规格：原样读 JSON（它本来就是语言中立的）。"""
    path = config.RESOURCE_DIR / "report_layout.json"
    return json.loads(path.read_text(encoding="utf-8"))


def shell_source() -> str:
    """``web/assets/shell.js``：给 Service Worker 用的离线清单 + 版本号。"""
    assets = shell_assets()
    missing = [item for item in assets if not (WEB_DIR / item).exists()]
    if missing:
        raise SystemExit("离线清单里有不存在的文件：%s" % "、".join(missing))
    lines = [
        "/* 本文件由 tools/export_web_assets.py 生成，请勿手改。",
        " * 真相源：web/ 目录（规则见脚本里的 shell_assets()）",
        " * 重新生成：python tools/export_web_assets.py",
        " *",
        " * 用途：Service Worker 的离线预缓存清单 + 内容指纹版本号。",
        " * 版本号只取决于被缓存文件的内容 —— 改了任何一个文件，SW 都会装新版本并清掉旧缓存。",
        " */",
        "",
        "export const SHELL_VERSION = %s;" % json.dumps(shell_version(assets)),
        "",
        "export const SHELL_ASSETS = Object.freeze([",
    ]
    lines += ["    %s," % json.dumps(item, ensure_ascii=False) for item in assets]
    lines += ["]);", "", "export default SHELL_ASSETS;", ""]
    return "\n".join(lines)


def style_source() -> str:
    """界面样式的真相源：Flask 侧那份 CSS（逐字节复制，只加一个生成头）。"""
    return SOURCE_CSS.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 web/ 前端要用的数据资产")
    parser.add_argument("--check", action="store_true", help="只检查是否与真相源同步")
    args = parser.parse_args()
    return build(check_only=args.check)


if __name__ == "__main__":
    sys.exit(main())
