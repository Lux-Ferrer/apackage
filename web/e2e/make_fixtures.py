# -*- coding: utf-8 -*-
"""生成 E2E 测试用的图片夹具（真实浏览器要真字节，不能靠 mock）。

为什么不用仓库里已有的图：需要**精确已知**的尺寸与像素内容来断言方向/缩放，
而且不能把用户/客户的照片带进测试。这里现场生成，尺寸与色带都是"可验证的约定"。

约定：
  - `*_h.png`：四条**水平**色带（存储像素从上到下：红 / 绿 / 蓝 / 黄）；
  - `rotated_exif.jpg`：四条**竖直**色带（存储像素从左到右：红 / 绿 / 蓝 / 黄），
    并带 EXIF Orientation=6 —— 含义是"显示时顺时针转 90°"。
    EXIF 规范里 Orientation=6 表示"存储的第 0 行是显示时的**右侧**"，
    于是存储的**左侧**（红带）转到显示时的**顶部**。
    摆正后的结果因此是 800×1200，且**顶部四分之一是红的**。
    这条断言能同时抓住两种错：EXIF 完全没摆正（红会留在左边、尺寸仍是 1200×800），
    以及摆了两次（红会跑到右边/底部）。

用法（由 `web/e2e/global-setup.mjs` 调用）::

    python web/e2e/make_fixtures.py --out _work/e2e/fixtures
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

BANDS = [
    (220, 40, 40),      # 红
    (40, 170, 80),      # 绿
    (50, 90, 200),      # 蓝
    (230, 190, 40),     # 黄
]


def bands_image(width: int, height: int, direction: str = "h") -> Image.Image:
    """四条等宽的色带。`direction='h'` 水平（从上到下），`'v'` 竖直（从左到右）。"""
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for index, color in enumerate(BANDS):
        if direction == "h":
            top = round(height * index / len(BANDS))
            bottom = round(height * (index + 1) / len(BANDS)) - 1
            draw.rectangle([0, top, width - 1, bottom], fill=color)
        else:
            left = round(width * index / len(BANDS))
            right = round(width * (index + 1) / len(BANDS)) - 1
            draw.rectangle([left, 0, right, height - 1], fill=color)
    return image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="_work/e2e/fixtures")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # 主流程：竖拍尺寸（800×1600，未超过 1600 → 附页不显示「已压缩」）
    bands_image(800, 1600).save(out / "portrait.png")

    # 小图（截图那种尺寸）
    bands_image(640, 480).save(out / "small.png")

    # 大图（2400×1800 > 1600 → 走等比缩放，附页里应显示「已压缩」）
    bands_image(2400, 1800).save(out / "large.png", quality=92)

    # 带 EXIF 方向：存储 1200×800（竖直色带），Orientation=6 → 显示 800×1200，红在顶部
    rotated = bands_image(1200, 800, direction="v")
    exif = Image.Exif()
    exif[0x0112] = 6
    rotated.save(out / "rotated_exif.jpg", quality=92, exif=exif)

    # 带透明通道的 PNG：左上角必须变成**白色**（不是黑色）—— 渲染进 JPEG 前要铺白底，
    # 否则导出的附页会出现一大块黑（PNG 转 JPEG 的经典坑）。
    alpha = bands_image(800, 600).convert("RGBA")
    alpha_pixels = alpha.load()
    for y in range(300):
        for x in range(400):
            alpha_pixels[x, y] = (0, 0, 0, 0)
    alpha.save(out / "alpha.png")

    for path in sorted(out.glob("*")):
        with Image.open(path) as image:
            orientation = (image.getexif() or {}).get(0x0112, 1)
            print(f"{path.name}: 存储 {image.size[0]}×{image.size[1]}，EXIF 方向 {orientation}，"
                  f"{path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
