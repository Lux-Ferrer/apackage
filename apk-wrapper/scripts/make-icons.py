#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 PWA 的图标写进 Android 工程的 mipmap 目录（替换 Capacitor 自带的默认图标）。

为什么要这一步：`npx cap add android` 生成的图标是 Capacitor 的默认 logo，
装到客户手机上会显示成"别人的 App"。

用哪张源图：`web/icons/icon-512-maskable.png`（蓝底 + 白色圆角方块 + 蓝色清单图标）。
它就是浏览器/主屏上实际显示的那个样子，所以 Android 也跟着它走，视觉才一致。

    python apk-wrapper/scripts/make-icons.py

生成（都在 android/app/src/main/res/ 下）：
    mipmap-*/ic_launcher.png            48…192px，原样缩放（蓝底白块）
    mipmap-*/ic_launcher_round.png      同上，圆形遮罩（老系统的圆形图标）
    mipmap-*/ic_launcher_foreground.png 自适应图标前景：把"外围蓝底"抠成透明，只留白色方块+图标
    values/ic_launcher_background.xml   自适应图标背景色 = 源图的外围蓝（从像素里取，不写死）
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]          # apk-wrapper/scripts → 仓库根
RES = ROOT / "apk-wrapper" / "android" / "app" / "src" / "main" / "res"
SOURCE = ROOT / "web" / "icons" / "icon-512-maskable.png"

BACKGROUND_XML = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="ic_launcher_background">#{color}</color>
</resources>
"""

DENSITIES = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}
LEGACY_SIZE = 48          # mdpi 基准
ADAPTIVE_SIZE = 108       # 自适应画布 108dp；内容放中间 68% 内，避开系统遮罩


def dominant_border_color(image: Image.Image) -> tuple:
    """取四角像素的众数当"外围底色"（比写死 #1668DC 稳：换图标也不用改代码）。"""
    width, height = image.size
    samples = [image.getpixel(point) for point in (
        (2, 2), (width - 3, 2), (2, height - 3), (width - 3, height - 3),
        (width // 2, 2), (width // 2, height - 3),
    )]
    return Counter(samples).most_common(1)[0][0]


def cut_out_border(image: Image.Image, border: tuple, tolerance: int = 18) -> Image.Image:
    """把接近外围底色的像素变透明，留下中间的白色圆角方块与图标。"""
    result = image.convert("RGBA")
    pixels = result.load()
    width, height = result.size
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if (abs(red - border[0]) <= tolerance and abs(green - border[1]) <= tolerance
                    and abs(blue - border[2]) <= tolerance):
                pixels[x, y] = (red, green, blue, 0)
    return result


def circular(image: Image.Image) -> Image.Image:
    size = image.size[0]
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    result = image.convert("RGBA")
    result.putalpha(mask.resize((size, size), Image.LANCZOS))
    return result


def main() -> int:
    if not SOURCE.exists():
        raise SystemExit(f"找不到源图标：{SOURCE}")
    base = Image.open(SOURCE).convert("RGBA")
    if base.size != (512, 512):
        base = base.resize((512, 512), Image.LANCZOS)
    border = dominant_border_color(base)
    foreground_source = cut_out_border(base, border)

    written = []
    for density, factor in DENSITIES.items():
        folder = RES / f"mipmap-{density}"
        if not folder.exists():
            raise SystemExit(f"没有这个目录：{folder}（先跑 npx cap add android）")

        legacy_size = round(LEGACY_SIZE * factor)
        legacy = base.resize((legacy_size, legacy_size), Image.LANCZOS)
        legacy.save(folder / "ic_launcher.png")
        circular(legacy).save(folder / "ic_launcher_round.png")

        canvas_size = round(ADAPTIVE_SIZE * factor)
        inner = round(canvas_size * 0.68)
        foreground = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        scaled = foreground_source.resize((inner, inner), Image.LANCZOS)
        offset = (canvas_size - inner) // 2
        foreground.paste(scaled, (offset, offset), scaled)
        foreground.save(folder / "ic_launcher_foreground.png")
        written.append(f"mipmap-{density}: {legacy_size}px / 前景 {canvas_size}px")

    (RES / "values" / "ic_launcher_background.xml").write_text(
        BACKGROUND_XML.format(color="%02X%02X%02X" % border[:3]), encoding="utf-8")

    print("✅ 图标已写入（底色 #%02X%02X%02X）" % border[:3])
    for line in written:
        print("   ·", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
