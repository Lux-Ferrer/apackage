#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给《用户操作手册》的截图加红框标注，输出到 docs/release/manual/。

输入
----
* `_work/manual/*.png`          —— 在模拟器里按真实操作拍的（720×1245 或 720×1280）
* `_work/manual/boxes.json`     —— 每个红框在**设备像素**里的矩形（拍照时用 DOM 量的，不靠眼看）
* `_work/manual/boxes-backup.json` —— 数据管理页两张（1.0.3 网页版补拍）

输出
----
* `docs/release/manual/<原名>.png` —— 统一裁掉状态栏 + 画红框 + 角标文字

为什么要裁状态栏：10 张图里有 8 张来自 APK（带 Android 状态栏）、2 张来自网页版（没有），
裁掉顶部 36px 之后，手册里的图框高度一致，看起来是同一台设备。

用法::

    python tools/make_manual_images.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "_work" / "manual"
OUT = ROOT / "docs" / "release" / "manual"

STATUS_BAR = 36          # 设备像素：状态栏高度（裁掉）
RED = (225, 29, 72)      # rose-600，红框比纯红更耐看
LABEL_BG = (225, 29, 72)
WHITE = (255, 255, 255)
RADIUS = 10
WIDTH = 5

CJK_FONTS = [
    Path("C:/Windows/Fonts/msyhbd.ttc"),
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in CJK_FONTS:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    raise SystemExit("找不到中文字体（msyh.ttc / simhei.ttf）")


def draw_box(draw, box, font, image_width: int) -> None:
    x, y, w, h = box["x"], box["y"] - STATUS_BAR, box["w"], box["h"]
    draw.rounded_rectangle((x - 4, y - 4, x + w + 4, y + h + 4), radius=RADIUS,
                           outline=RED, width=WIDTH)

    label = box.get("label") or ""
    if not label:
        return
    # 角标：优先放框内左上角，放不下就贴到框上方
    pad_x, pad_y = 10, 5
    text_w = draw.textlength(label, font=font)
    chip_w, chip_h = int(text_w) + pad_x * 2, font.size + pad_y * 2
    chip_x = x - 4
    chip_y = y - 4 - chip_h - 4
    if chip_y < 0:                      # 顶上放不下 → 塞进框内
        chip_y = y + 6
    # 靠右的边缘框：角标不能溢出画布，否则会被裁掉
    chip_x = max(2, min(chip_x, image_width - chip_w - 2))
    draw.rounded_rectangle((chip_x, chip_y, chip_x + chip_w, chip_y + chip_h),
                           radius=6, fill=LABEL_BG)
    draw.text((chip_x + pad_x, chip_y + pad_y - 2), label, font=font, fill=WHITE)


def main() -> int:
    if not SRC.exists():
        raise SystemExit(f"缺少截图目录：{SRC}（先跑 _work/manual/capture.mjs）")

    boxes: dict[str, list] = {}
    for name in ("boxes.json", "boxes-backup.json"):
        path = SRC / name
        if path.exists():
            boxes.update(json.loads(path.read_text(encoding="utf-8")))

    OUT.mkdir(parents=True, exist_ok=True)
    font = load_font(26)

    made = []
    for path in sorted(SRC.glob("[0-9]*.png")):
        with Image.open(path) as raw:
            image = raw.convert("RGB")
        # 裁掉状态栏（网页版截图本来就没有，按高度判断，避免裁掉内容）
        if image.height in (1245, 1280):
            image = image.crop((0, STATUS_BAR, image.width, image.height))
        elif image.height > 1245:
            image = image.crop((0, STATUS_BAR, image.width, image.height))

        draw = ImageDraw.Draw(image)
        count = 0
        for box in boxes.get(path.name, []):
            if box:
                draw_box(draw, box, font, image.width)
                count += 1

        target = OUT / path.name
        image.save(target, format="PNG", optimize=True)
        made.append((path.name, count, image.size))

    print(f"✅ 已生成 {len(made)} 张标注图 → {OUT.relative_to(ROOT)}")
    for name, count, size in made:
        print(f"   · {name:26} 红框 {count} 个  {size[0]}×{size[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
