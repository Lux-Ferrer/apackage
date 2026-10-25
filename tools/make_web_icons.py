# -*- coding: utf-8 -*-
"""生成 PWA 图标（``web/icons/``）。

为什么用脚本画而不是找一张图：**可复现**。图标要进仓库、要出现在"添加到主屏幕"上，
将来改配色时应该能一条命令重画，而不是找到当初那个人问 PNG 在哪。

画法：强调色底 + 一张"表格式"白色标记（三条横线 + 左边一列），
与工具本身的气质一致（它生成的就是表格报告）。不写中文字 —— 小尺寸下会糊。

产出：
  ``icon-192.png``            普通图标（主屏幕 / 任务栏）
  ``icon-512.png``            高分辨率（启动画面 / 商店）
  ``icon-512-maskable.png``   可遮罩图标（Android 会裁成圆形/圆角，**内容要留安全边距**）

用法::

    python tools/make_web_icons.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "web" / "icons"

ACCENT = (22, 104, 220)          # 与 webapp/static/css/app.css 的 --accent 一致
WHITE = (255, 255, 255)


def draw_icon(size: int, *, padding_ratio: float = 0.0, radius_ratio: float = 0.22) -> Image.Image:
    """画一张图标。``padding_ratio`` 为可遮罩图标的安全边距（Android 会裁掉外圈）。"""
    image = Image.new("RGB", (size, size), ACCENT)
    pen = ImageDraw.Draw(image)

    inner = size * (1 - 2 * padding_ratio)
    offset = size * padding_ratio
    radius = inner * radius_ratio

    # 白色圆角"纸面"
    pen.rounded_rectangle(
        [offset, offset, offset + inner, offset + inner],
        radius=radius, fill=WHITE,
    )

    # 表格标记：左边一列 + 三条横线（用强调色画在白纸上）
    line_width = max(2, int(inner * 0.045))
    left = offset + inner * 0.20
    right = offset + inner * 0.80
    top = offset + inner * 0.24
    row_height = (inner * 0.52) / 3
    column = offset + inner * 0.38

    pen.line([left, top, left, top + row_height * 3], fill=ACCENT, width=line_width)
    pen.line([column, top, column, top + row_height * 3], fill=ACCENT, width=line_width)
    for index in range(4):
        y = top + row_height * index
        pen.line([left, y, right, y], fill=ACCENT, width=line_width)

    return image


def main() -> int:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        ("icon-192.png", 192, 0.0),
        ("icon-512.png", 512, 0.0),
        # 可遮罩：Android 可能把外圈 10% 裁掉，所以内容收进 80% 的圆里
        ("icon-512-maskable.png", 512, 0.10),
    ]
    for name, size, padding in targets:
        icon = draw_icon(size, padding_ratio=padding)
        path = ICON_DIR / name
        icon.save(path, "PNG", optimize=True)
        print("已生成 %s（%d×%d，%d KB）"
              % (path.relative_to(ROOT), size, size, path.stat().st_size // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
