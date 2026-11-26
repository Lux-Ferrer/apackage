#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 PDF 逐页导出成 PNG（可选：拼一张总览缩略图、打包成 zip）。

用法::

    python tools/pdf_to_images.py dist/Jin_Zeyu_..._FinalReport.pdf
    python tools/pdf_to_images.py dist/xxx.pdf --dpi 200 --zip --contact-sheet

输出默认放在 PDF 同目录、以 PDF 名命名的 `<name>_pages/` 里：
    page-001.png … page-0NN.png（零填充，方便按文件名排序）
    _contact-sheet.png（全部页缩略拼图，一眼看完整本）
"""

from __future__ import annotations

import argparse
import math
import zipfile
from pathlib import Path

import pymupdf
from PIL import Image


def render(pdf_path: Path, out_dir: Path, dpi: int, prefix: str) -> list[Path]:
    document = pymupdf.open(pdf_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    width = len(str(document.page_count))
    written: list[Path] = []
    for index, page in enumerate(document, start=1):
        target = out_dir / f"{prefix}{index:0{width}d}.png"
        page.get_pixmap(dpi=dpi).save(target)
        written.append(target)
    print(f"· 渲染 {len(written)} 页 → {out_dir}")
    return written


def contact_sheet(images: list[Path], target: Path, columns: int = 9, thumb_width: int = 240) -> None:
    """把每页缩略成小图拼成一张总览（灰底、带页号）。"""
    thumbs = []
    for path in images:
        with Image.open(path) as page:
            ratio = thumb_width / page.width
            thumbs.append(page.convert("RGB").resize((thumb_width, int(page.height * ratio))))

    if not thumbs:
        return
    tile_w, tile_h = thumbs[0].size
    rows = math.ceil(len(thumbs) / columns)
    gap = 8
    sheet = Image.new(
        "RGB",
        (columns * tile_w + gap * (columns + 1), rows * tile_h + gap * (rows + 1)),
        (235, 238, 242),
    )
    for index, thumb in enumerate(thumbs):
        column, row = index % columns, index // columns
        sheet.paste(thumb, (gap + column * (tile_w + gap), gap + row * (tile_h + gap)))
    sheet.save(target)
    print(f"· 总览图 → {target}（{sheet.width}×{sheet.height}）")


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF → 逐页 PNG")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--prefix", default="page-")
    parser.add_argument("--out", type=Path, default=None, help="输出目录（默认 <pdf 同目录>/<pdf 名>_pages）")
    parser.add_argument("--zip", action="store_true", help="额外打包成 <name>_pages.zip")
    parser.add_argument("--contact-sheet", action="store_true", help="额外生成总览缩略图")
    args = parser.parse_args()

    pdf_path = args.pdf if args.pdf.is_absolute() else (Path.cwd() / args.pdf)
    if not pdf_path.exists():
        raise SystemExit(f"找不到 PDF：{pdf_path}")

    out_dir = args.out or pdf_path.with_name(f"{pdf_path.stem}_pages")
    images = render(pdf_path, out_dir, args.dpi, args.prefix)

    if args.contact_sheet:
        contact_sheet(images, out_dir / "_contact-sheet.png")

    total = sum(path.stat().st_size for path in images)
    print(f"· 合计 {total / 1024 / 1024:.1f} MB（{args.dpi} dpi）")

    if args.zip:
        archive = out_dir.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(out_dir.iterdir()):
                if path.is_file():
                    bundle.write(path, path.name)
        print(f"· 压缩包 → {archive}（{archive.stat().st_size / 1024 / 1024:.1f} MB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
