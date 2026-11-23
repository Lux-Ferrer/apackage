#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""替换 Capacitor 的默认启动图（splash）为品牌图：品牌蓝底 + 居中图标。

不换的话，APK 启动瞬间会闪一下 Capacitor 的默认画面 —— 给客户看到会很出戏。

    python apk-wrapper/scripts/make-splash.py

做法：保留工程里每个 splash 的**原始尺寸**，只换内容（蓝底 + 图标居中，
图标高度取短边的 22%），所以任何屏幕比例都不会拉伸变形。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "apk-wrapper" / "android" / "app" / "src" / "main" / "res"
SOURCE = ROOT / "web" / "icons" / "icon-512-maskable.png"
BRAND = (22, 104, 220)          # 与 ic_launcher_background / 界面主色一致


def main() -> int:
    if not SOURCE.exists():
        raise SystemExit(f"找不到源图标：{SOURCE}")
    icons = [path for path in sorted(RES.glob("drawable*/splash.png"))]
    if not icons:
        raise SystemExit("没找到 splash.png（先跑 npx cap add android）")

    icon = Image.open(SOURCE).convert("RGBA")
    for path in icons:
        with Image.open(path) as current:
            width, height = current.size
        canvas = Image.new("RGB", (width, height), BRAND)
        side = max(48, round(min(width, height) * 0.22))
        scaled = icon.resize((side, side), Image.LANCZOS)
        canvas.paste(scaled, ((width - side) // 2, (height - side) // 2), scaled)
        canvas.save(path, format="PNG")

    print(f"✅ 已替换 {len(icons)} 张启动图（{BRAND[0]:02X}{BRAND[1]:02X}{BRAND[2]:02X} 底 + 居中图标）")
    print(f"   目录：{RES.relative_to(ROOT)}/drawable*/splash.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
