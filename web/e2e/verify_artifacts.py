# -*- coding: utf-8 -*-
"""校验浏览器里真实下载到的产物（docx / 备份 zip），结果以 JSON 打印给 Playwright 断言。

为什么要用 Python 而不只是 JSZip 检查一下
------------------------------------------
1. **python-docx 能打开它** 是"Word/WPS 也能打开"的最强代理：
   库的解析比 zip 解包严格得多（关系、内容类型、XML 结构都要对）；
2. 图片尺寸/像素内容用 Pillow 读，可以断言**方向是否真的摆正**（红带在顶部），
   这是"看图"级的验证，比比对字符串可靠；
3. 附页份数、报告人、表结构这些都能从 docx 模型里直接读出来。

用法::

    python web/e2e/verify_artifacts.py docx  _work/e2e/artifacts/xxx.docx
    python web/e2e/verify_artifacts.py backup _work/e2e/artifacts/xxx.zip
"""

from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from pathlib import Path

from PIL import Image

RED_DOMINANT = "红"
BAND_NAMES = ["红", "绿", "蓝", "黄"]


def band_at(image: Image.Image, position: str) -> str:
    """取某个区域的主色带名（用于方向断言）。`position` 取 top/bottom/left/right。"""
    width, height = image.size
    if position == "top":
        box = (0, 0, width, max(1, height // 8))
    elif position == "bottom":
        box = (0, height - max(1, height // 8), width, height)
    elif position == "left":
        box = (0, 0, max(1, width // 8), height)
    else:
        box = (width - max(1, width // 8), 0, width, height)

    crop = image.crop(box).convert("RGB").resize((1, 1), Image.BOX)
    red, green, blue = crop.getpixel((0, 0))
    if red > green + 60 and red > blue + 60:
        return "红"
    if green > red + 40 and green > blue + 20:
        return "绿"
    if blue > red + 40 and blue > green + 40:
        return "蓝"
    if red > 150 and green > 130 and blue < 120:
        return "黄"
    return f"未知({red},{green},{blue})"


def verify_docx(path: Path) -> dict:
    import docx                                            # noqa: PLC0415 - 只有这个子命令需要

    document = docx.Document(str(path))
    paragraphs = [item.text for item in document.paragraphs]
    texts = [cell.text for table in document.tables for row in table.rows
             for cell in row.cells]
    full_text = "\n".join(paragraphs + texts)

    with zipfile.ZipFile(path) as archive:
        # ⚠️ 要排掉目录条目（`word/media/` 本身也以它开头、大小 0、PIL 读不了）
        media_names = [item.filename for item in archive.infolist()
                       if item.filename.startswith("word/media/") and not item.is_dir()]
        media = []
        for name in media_names:
            raw = archive.read(name)
            with Image.open(io.BytesIO(raw)) as image:
                media.append({
                    "name": name,
                    "bytes": len(raw),
                    "width": image.size[0],
                    "height": image.size[1],
                    "format": image.format,
                    # 四条边的主色带：用来断言"图片真的是正的"（见 make_fixtures.py 的约定）
                    "bands": {position: band_at(image.convert("RGB"), position)
                              for position in ("top", "bottom", "left", "right")},
                    # 左上角像素：透明 PNG 被"铺白底"后这里必须是白，否则就是黑底
                    "corner": list(image.convert("RGB").getpixel((2, 2))),
                })

    return {
        "ok": True,
        "path": str(path),
        "size_kb": round(path.stat().st_size / 1024, 1),
        "paragraphs": len(paragraphs),
        "tables": len(document.tables),
        "table_rows": [len(table.rows) for table in document.tables],
        "attachment_pages": full_text.count("检测报告附页（"),
        "has_column_title": "幕墙立柱截面尺寸检测结果" in full_text,
        "has_beam_title": "幕墙横梁截面尺寸检测结果" in full_text,
        "compress_marks": full_text.count("（已压缩）"),
        "reporter_lines": sorted({
            line.strip() for line in full_text.splitlines() if "（检测" in line or "（幕墙" in line
        }),
        # 附页信息表里的「图片文件」行：用来核对"图与附页是否对得上"
        "image_names": sorted(set(re.findall(r"[\w\u4e00-\u9fff-]+\.(?:png|jpg|jpeg|PNG|JPG)",
                                              full_text))),
        "media": media,
        "missing_image_marks": full_text.count("（图片缺失"),
        "text_tail": full_text[-400:],
    }


def verify_backup(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if "backup.json" not in names:
            raise SystemExit("× 备份里没有 backup.json")
        data = json.loads(archive.read("backup.json").decode("utf-8"))
        # 同样要排掉目录条目（`images/` 会命中前缀且大小为 0）
        image_entries = [item.filename for item in archive.infolist()
                         if item.filename.startswith("images/") and not item.is_dir()]
        images = []
        for name in image_entries:
            raw = archive.read(name)
            with Image.open(io.BytesIO(raw)) as image:
                images.append({
                    "name": name,
                    "bytes": len(raw),
                    "width": image.size[0],
                    "height": image.size[1],
                    "format": image.format,
                })
        # 缩略图不该进备份（设计上是可重建的派生值）
        thumbs = [row for row in data.get("tables", {}).get("images", []) if "thumb" in row]

    return {
        "ok": True,
        "path": str(path),
        "size_kb": round(path.stat().st_size / 1024, 1),
        "format": data.get("format"),
        "version": data.get("version"),
        "counts": data.get("counts"),
        "tables": {key: len(value) for key, value in data.get("tables", {}).items()},
        "image_files": len(image_entries),
        "images": images,
        "thumbnail_rows": len(thumbs),
    }


def verify_image(path: Path) -> dict:
    """单张图片：尺寸 + 四边色带（用于断言缩略图/导出副本是否摆正）。"""
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        return {
            "ok": True,
            "path": str(path),
            "width": image.size[0],
            "height": image.size[1],
            "format": image.format,
            "bands": {position: band_at(rgb, position)
                      for position in ("top", "bottom", "left", "right")},
        }


def main(argv: list) -> int:
    if len(argv) != 3 or argv[1] not in ("docx", "backup", "image"):
        print(__doc__)
        return 2
    path = Path(argv[2])
    if not path.exists():
        print(json.dumps({"ok": False, "error": f"文件不存在：{path}"}, ensure_ascii=False))
        return 1
    try:
        if argv[1] == "docx":
            result = verify_docx(path)
        elif argv[1] == "backup":
            result = verify_backup(path)
        else:
            result = verify_image(path)
    except Exception as error:                             # noqa: BLE001 - 校验失败要原样报出来
        print(json.dumps({"ok": False, "error": f"{type(error).__name__}: {error}"},
                         ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
