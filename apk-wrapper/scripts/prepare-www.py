#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把交付包解到 apk-wrapper/www —— APK 里装着的就是这个目录。

为什么不直接软链接到 dist/ 里的解压目录：Windows 上软链接要管理员权限，
而且 Capacitor 会把 www 整个**拷进** android/app/src/main/assets/public，
链接与否对最终 APK 没有区别。干脆每次从 zip 重新解一遍，来源永远只有一个：交付包。

会做三件事：
  1. 从 ``dist/mcc-inspection-tool-v<版本>.zip`` 解到 ``www/``（先清空，避免残留旧文件）；
  2. 校验 ``www/VERSION.txt`` 里的版本与 ``web/app/product.js`` 一致（防止装错版本的包）；
  3. 打印 www 的文件数，便于和交付包核对。

用法::

    python apk-wrapper/scripts/prepare-www.py
    python apk-wrapper/scripts/prepare-www.py --zip ..\\dist\\mcc-inspection-tool-v1.0.1.zip
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]          # apk-wrapper/
ROOT = HERE.parent                                   # 仓库根
WEB = HERE / "www"


def product_version() -> str:
    text = (ROOT / "web" / "app" / "product.js").read_text(encoding="utf-8")
    match = re.search(r"version:\s*'([0-9.]+)'", text)
    if not match:
        raise SystemExit("在 web/app/product.js 里没找到 version")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="把交付包解到 apk-wrapper/www")
    parser.add_argument("--zip", type=Path, default=None,
                        help="交付包路径（默认取 dist/ 下版本号最新的那个）")
    args = parser.parse_args()

    version = product_version()
    if args.zip is None:
        candidates = sorted((ROOT / "dist").glob("mcc-inspection-tool-v*.zip"))
        if not candidates:
            raise SystemExit("dist/ 里没有交付包，先跑 python tools/make_release_zip.py")
        archive = candidates[-1]
    else:
        archive = args.zip if args.zip.is_absolute() else (ROOT / args.zip)
    if not archive.exists():
        raise SystemExit(f"找不到交付包：{archive}")

    with tempfile.TemporaryDirectory() as scratch:
        zipfile.ZipFile(archive).extractall(scratch)
        roots = [item for item in Path(scratch).iterdir() if item.is_dir()]
        if len(roots) != 1:
            raise SystemExit(f"交付包里应当只有一层目录，实际有：{[r.name for r in roots]}")
        staged = roots[0]

        if WEB.exists():
            shutil.rmtree(WEB)
        shutil.copytree(staged, WEB)

    files = sorted(path for path in WEB.rglob("*") if path.is_file())
    version_line = next((line for line in (WEB / "VERSION.txt").read_text(encoding="utf-8").splitlines()
                         if line.startswith("版本：")), "版本：?")
    packaged = version_line.split("：", 1)[1].strip().lstrip("v")

    print(f"交付包：{archive.relative_to(ROOT)}")
    print(f"www    ：{len(files)} 个文件")
    if packaged != version:
        raise SystemExit(f"版本不一致：交付包里是 {packaged}，product.js 里是 {version}")
    print(f"✅ 版本一致：v{packaged}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
