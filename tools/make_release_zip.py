# -*- coding: utf-8 -*-
"""把 ``web/`` 打包成可直接交付 / 内网部署的静态包。

产出::

    dist/mcc-inspection-tool-v1.0.0.zip
    dist/mcc-inspection-tool-v1.0.0.zip.sha256

包内结构（解压后是一层目录，不会把文件甩一地）::

    mcc-inspection-tool/
    ├── index.html · sw.js · manifest.webmanifest · VERSION.txt
    ├── 客户部署与使用说明.md
    ├── serve_static.py                （临时演示用的静态服务器）
    ├── deploy/nginx.conf.example · web.config.example
    ├── app/ · assets/ · icons/ · styles/ · vendor/

**不打包**的东西（以及为什么）::

    tests/                    开发期测试，与运行时无关
    assets/fixture_data.json  对拍闸门用的夹具数据（含开发期的人名/部门）
    node_modules/ .git/       依赖与版本库
    *.bak *.map __pycache__   临时文件

三道自检（任何一条不满足就拒绝产出，而不是"打个包先看看"）::

    1. 必需文件齐（index.html / app/main.js / app/product.js / vendor/…）；
    2. 禁止项一个都没有（tests、夹具数据、备份文件、Node 依赖）；
    3. 离线清单（assets/shell.js 里的 SHELL_ASSETS）里列的每个文件都真的在包里 ——
       漏一个的话，Service Worker 装不上 → **断网就白屏**，而且在线时完全正常。

用法::

    python tools/make_release_zip.py
    python tools/make_release_zip.py --version 1.0.1     # 临时改包名（会与 product.js 不一致，仅供试打）
    python tools/make_release_zip.py --keep-stage        # 保留解包前的暂存目录，便于人工检查
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
RELEASE_SRC = ROOT / "docs" / "release"
DIST_DIR = ROOT / "dist"
STAGE_ROOT = ROOT / "_work" / "release-stage"
PACKAGE_DIR_NAME = "mcc-inspection-tool"

# ---- 不进包的文件/目录（按相对 web/ 的路径匹配）----
EXCLUDE_DIRS = {"tests", "node_modules", ".git", "__pycache__"}
EXCLUDE_FILES = {
    "assets/fixture_data.json",     # 对拍夹具（含开发期人名），运行时不需要
    "package.json",                 # 只是给 Node 声明 ESM 作用域，浏览器用不到
}
EXCLUDE_SUFFIXES = {".bak", ".map", ".pyc", ".log"}
EXCLUDE_PREFIXES = ("._",)          # macOS 的 ._ 资源分叉文件

# ---- 必需文件（少一个就是交付事故，宁可红）----
REQUIRED = [
    "index.html",
    "sw.js",
    "manifest.webmanifest",
    "app/main.js",
    "app/product.js",
    "app/repo/profile.js",
    "app/views/profile.js",
    "app/report/engine.js",
    "assets/shell.js",
    "assets/report_base.docx",
    "styles/app.css",
    "styles/m5.css",
    "vendor/docx.mjs",
    "vendor/jszip.js",
    "vendor/jszip.min.js",
    "icons/icon-192.png",
    "icons/icon-512.png",
    "icons/icon-512-maskable.png",
]

# ---- 要在包里额外放进去的交付文档 ----
RELEASE_FILES = {
    "客户部署与使用说明.md": RELEASE_SRC / "客户部署与使用说明.md",
    "serve_static.py": RELEASE_SRC / "serve_static.py",
    "deploy/nginx.conf.example": RELEASE_SRC / "nginx.conf.example",
    "deploy/web.config.example": RELEASE_SRC / "web.config.example",
}


def read_product_version() -> str:
    """从 ``web/app/product.js`` 读版本号（版本号只该有这一处真相源）。"""
    source = (WEB_DIR / "app" / "product.js").read_text(encoding="utf-8")
    match = re.search(r"version:\s*'([0-9]+\.[0-9]+\.[0-9]+)'", source)
    if not match:
        raise SystemExit("× 没能从 web/app/product.js 里读到 version（格式：version: '1.0.0'）")
    return match.group(1)


def read_shell_version() -> str:
    source = (WEB_DIR / "assets" / "shell.js").read_text(encoding="utf-8")
    match = re.search(r'SHELL_VERSION\s*=\s*"([0-9a-f]{12})"', source)
    return match.group(1) if match else "?"


def read_shell_assets() -> list:
    """离线清单里列的文件（SW 会逐个预缓存，缺一个就装不上）。"""
    source = (WEB_DIR / "assets" / "shell.js").read_text(encoding="utf-8")
    block = re.search(r"SHELL_ASSETS\s*=\s*Object\.freeze\(\[(.*?)\]\)", source, re.S)
    if not block:
        raise SystemExit("× 没能解析 assets/shell.js 里的 SHELL_ASSETS")
    return re.findall(r'"([^"]+)"', block.group(1))


def is_excluded(relative: Path) -> bool:
    parts = relative.parts
    if any(part in EXCLUDE_DIRS for part in parts[:-1]) or parts[0] in EXCLUDE_DIRS:
        return True
    if relative.as_posix() in EXCLUDE_FILES:
        return True
    if relative.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    if relative.name.startswith(EXCLUDE_PREFIXES):
        return True
    return False


def stage(stage_dir: Path) -> list:
    """把 web/ 与交付文档复制到暂存目录，返回暂存目录里的文件（相对 package 目录）。"""
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    package_dir = stage_dir / PACKAGE_DIR_NAME
    package_dir.mkdir(parents=True)

    copied = []
    for source in sorted(WEB_DIR.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(WEB_DIR)
        if is_excluded(relative):
            continue
        target = package_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(relative.as_posix())

    for relative, source in RELEASE_FILES.items():
        if not source.exists():
            raise SystemExit(f"× 缺少交付文档：{source.relative_to(ROOT)}")
        target = package_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(relative)

    return sorted(copied)


def write_version_file(package_dir: Path, version: str) -> None:
    """VERSION.txt：现场排查第一眼看的东西（版本 / 构建时间 / 离线缓存版本）。"""
    lines = [
        f"产品名称：建筑幕墙检测报告工具",
        f"版本：v{version}",
        f"离线缓存版本（SHELL_VERSION）：{read_shell_version()}",
        f"构建时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "部署与使用：见同目录的《客户部署与使用说明.md》。",
        "改默认报告人：编辑 app/product.js 里的 DEFAULT_PROFILE（或在界面「我的 → 个人信息配置」里填）。",
        "",
    ]
    (package_dir / "VERSION.txt").write_text("\n".join(lines), encoding="utf-8")


def verify(package_dir: Path) -> None:
    problems = []

    for relative in REQUIRED:
        if not (package_dir / relative).exists():
            problems.append(f"缺少必需文件：{relative}")

    for path in package_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(package_dir).as_posix()
        if relative in ("VERSION.txt",) or relative in RELEASE_FILES:
            continue
        if any(part in EXCLUDE_DIRS for part in path.relative_to(package_dir).parts[:-1]):
            problems.append(f"不该进包：{relative}")
        if relative == "assets/fixture_data.json":
            problems.append("不该进包：assets/fixture_data.json（开发期夹具）")

    # 离线清单里的文件必须真的在包里（漏一个 → SW 装不上 → 断网白屏）
    for relative in read_shell_assets():
        if not (package_dir / relative).exists():
            problems.append(f"离线清单引用了包里没有的文件：{relative}")

    # 交付版不该带调试输出
    for path in sorted((package_dir / "app").rglob("*.js")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = re.sub(r"//.*$", "", line)
            if re.search(r"console\.(log|debug)\s*\(", code) or "debugger" in code:
                problems.append(
                    f"调试输出残留：{path.relative_to(package_dir)}:{number}  {line.strip()}")

    # 产品身份与文档里的版本号必须一致
    version = read_product_version()
    if f"v{version}" not in (package_dir / "VERSION.txt").read_text(encoding="utf-8"):
        problems.append("VERSION.txt 里的版本号与 app/product.js 不一致")

    if problems:
        print("× 打包自检未通过：")
        for problem in problems:
            print(f"  - {problem}")
        raise SystemExit(1)


def build_zip(package_dir: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                archive.write(path, Path(PACKAGE_DIR_NAME) / path.relative_to(package_dir))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="打包交付版静态包（.zip）")
    parser.add_argument("--version", default=None, help="覆盖包名里的版本号（默认取 app/product.js）")
    parser.add_argument("--keep-stage", action="store_true", help="保留暂存目录便于人工检查")
    args = parser.parse_args(argv)

    product_version = read_product_version()
    version = args.version or product_version

    print(f"· 版本：v{product_version}｜离线缓存版本：{read_shell_version()}")
    files = stage(STAGE_ROOT)
    package_dir = STAGE_ROOT / PACKAGE_DIR_NAME
    write_version_file(package_dir, product_version)
    print(f"· 暂存完成：{len(files) + 1} 个文件"
          f"（已排除 tests/ 、夹具数据、备份文件与 Node 依赖）")

    verify(package_dir)

    output = DIST_DIR / f"{PACKAGE_DIR_NAME}-v{version}.zip"
    build_zip(package_dir, output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (output.with_suffix(output.suffix + ".sha256")).write_text(
        f"{digest}  {output.name}\n", encoding="utf-8")

    size_kb = output.stat().st_size / 1024
    print(f"✅ 已生成 {output.relative_to(ROOT)}（{size_kb:.0f} KB）")
    print(f"   sha256 {digest}")
    print(f"   校验文件 {output.with_suffix(output.suffix + '.sha256').relative_to(ROOT)}")

    # 人类可读的清单（也便于评审时核对"交付包里到底有什么"）
    manifest = {
        "product": "建筑幕墙检测报告工具",
        "version": product_version,
        "shell_version": read_shell_version(),
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "file_count": len(files) + 1,
        "files": sorted(files + ["VERSION.txt"]),
    }
    (DIST_DIR / f"{PACKAGE_DIR_NAME}-v{version}.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not args.keep_stage:
        shutil.rmtree(STAGE_ROOT, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
