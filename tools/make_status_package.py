#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「Project Status Update Meeting」要上传的材料打成一个包。

产出::

    deliverables/status_update_package/
    ├── ReadMe.txt                  给教授的封面说明（英文，~150 词）
    ├── WBS_Update.pdf              当前 WBS（表格 + 状态 + 甘特图，A3 横版一页）
    ├── UI_Screenshots.pdf          三张界面证据（数据录入 / 报告列表 / 项目详情）
    ├── Sample_Report.docx          真实导出的 Word 样例（4 条记录 + 3 份附页）
    ├── QA_Evidence_Summary.md      测试证据摘要（从《交付验收报告》第 4、5 节抽取）
    └── QA_Evidence_Summary.pdf     同一份内容的 PDF（上传用）

    deliverables/status_update_package.zip   上面这个文件夹的压缩包

输入（都由脚本或前一步生成，脚本会检查是否齐）
------------------------------------------------
* ``deliverables/Current_WBS_Update.pdf``     ← ``python tools/make_current_wbs.py``
* ``_work/status/0*.png`` + ``Sample_Report.docx`` ← ``node web/e2e/capture-status-shots.mjs``
* ``docs/management/交付验收报告-v1.0.1.md``  ← 测试证据的来源

QA 摘要为什么是"抽取"而不是"手抄"
-----------------------------------
手抄的数字迟早会和报告对不上。这里直接按二级标题切出《交付验收报告》的第 4、5 节，
标题降一级后拼起来 —— 报告改了，这里跟着变。

用法::

    python tools/make_status_package.py            # 组装（会重新生成截图 PDF 与摘要）
    python tools/make_status_package.py --zip      # 组装并打 zip
"""

from __future__ import annotations

import argparse
import re
import shutil
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DELIVERABLES = ROOT / "deliverables"
PACKAGE = DELIVERABLES / "status_update_package"
ZIP_PATH = DELIVERABLES / "status_update_package.zip"

WBS_PDF = DELIVERABLES / "Current_WBS_Update.pdf"
SHOTS_DIR = ROOT / "_work" / "status"
ACCEPTANCE = ROOT / "docs" / "management" / "交付验收报告-v1.0.1.md"

FONT_DIR = Path(__import__("matplotlib").get_data_path()) / "fonts" / "ttf"
FONT_REGULAR = FONT_DIR / "DejaVuSans.ttf"
FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"

INK = (17, 24, 39)
MUTED = (107, 114, 128)
ACCENT = (31, 78, 121)
RULE = (203, 213, 225)

SHOTS = [
    ("01-数据录入.png",
     "Inspection record entry",
     ["Five thickness readings per face; the minimum is computed automatically",
      "as you type (here 2.99 mm) and rolled up into the face summary."]),
    ("02-报告列表.png",
     "Report management",
     ["Reports are listed with risk badges (高/中/低), photo thumbnails and the",
      "bound project. Counters at the top double as filters."]),
    ("03-项目详情.png",
     "Project detail and one-click export",
     ["Export with or without the defect reports as attachment pages.",
      "The whole report is generated on the device; nothing is uploaded."]),
]

README = """\
Project Status Update — Work Product Drafts
============================================

This submission contains the updated WBS and the actual product deliverables for the
NYU capstone project "Curtain Wall Inspection Report Tool".

1. WBS_Update.pdf — the current WBS and Gantt chart (40 tasks) with status as of
   Nov 12, 2026: 33 completed, 3 in progress, 4 planned. Green bars are completed work.
2. UI_Screenshots.pdf — three screens of the shipped product on a 375x812 mobile
   viewport: inspection record entry, report management, and project detail.
3. Sample_Report.docx — a real Word report exported by the application: 4 inspection
   records plus 3 defect reports as attachment pages, matching the client's format.
4. QA_Evidence_Summary.md / .pdf — the verification evidence behind the v1.0.1 release:
   348 Python tests, 239 front-end tests, 16 layout-fidelity gates with zero
   differences against the frozen baseline, 21 desktop browser E2E cases and
   14 Android assertions, all green.

Everything is produced from the same repository and the same release package
(53 files, sha256 245f5c9...), so the numbers in the report, the screenshots and the
sample document refer to the same build.
"""


# --------------------------------------------------------------------------
# 1) QA 摘要：按二级标题从验收报告里切出第 4、5 节
# --------------------------------------------------------------------------
def extract_sections(markdown: str, titles: tuple) -> str:
    """把 `## <title>` 到下一个 `## ` 之间的内容取出来（标题降一级）。"""
    lines = markdown.splitlines()
    kept: list = []
    for title in titles:
        pattern = re.compile(rf"^##\s+{re.escape(title)}\b")
        start = next((index for index, line in enumerate(lines) if pattern.match(line)), None)
        if start is None:
            raise SystemExit(f"验收报告里找不到章节：{title}")
        end = next((index for index in range(start + 1, len(lines))
                    if lines[index].startswith("## ")), len(lines))
        block = lines[start:end]
        block[0] = block[0].replace("## ", "### ", 1)
        kept.extend(block)
        kept.append("")
    return "\n".join(kept)


def build_qa_summary() -> Path:
    source = ACCEPTANCE.read_text(encoding="utf-8")
    body = extract_sections(source, ("4. 质量证据", "5. 交付过程中发现并修复的缺陷"))

    header = f"""\
# QA Evidence Summary — Curtain Wall Inspection Report Tool v1.0.1

## At a glance

| Layer | Size | Result |
| --- | --- | --- |
| Python unit / integration (reference implementation) | **348 tests** | all green |
| Front-end Node tests (data layer, engine, images, backup, keyboard) | **239 tests** | all green |
| Layout-fidelity gates (`python tools/verify_all.py`, 16 steps) | **3 independent gates + 7 injected-defect controls** | **0 differences** vs the frozen baseline, 7/7 injections caught |
| Desktop real-browser E2E (Playwright, 375×812) | **21 cases** | all green, zero console errors |
| Android real-browser regression (MuMu + MAA taps + CDP) | **14 assertions** | all green, zero console errors |
| Defects found and fixed during delivery | **9** (3 × P0) | each has a regression test + a positive control |

Re-run everything with:

```powershell
python tools/verify_all.py     # 16 gates: 348 Python + 239 front-end tests
npm run test:e2e               # 21 desktop E2E cases against the delivered zip
npm run test:android           # 14 assertions on a real Android browser
```

Release package: `mcc-inspection-tool-v1.0.1.zip` — 53 files / 465 KB /
sha256 `245f5c92…` / offline cache version `e904c3b9321a`.

---

## Appendix — the original tables (Chinese, from the acceptance report, sections 4 and 5)

"""
    path = PACKAGE / "QA_Evidence_Summary.md"
    path.write_text(header + body, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# 2) 界面截图 → 多页 PDF（每页一张 + 说明）
# --------------------------------------------------------------------------
PAGE_W, PAGE_H = 1240, 1754          # A4 @150dpi
MARGIN = 110

# 字体：截图里有中文，说明文字里也会出现「高/中/低」这类词 ——
# DejaVuSans 没有 CJK 字形（会画成方框），所以优先用系统的微软雅黑，实在没有才退回。
CJK_CANDIDATES = [
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/msyhbd.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
]


def load_font(size: int, *, bold: bool = False):
    candidates = ([CJK_CANDIDATES[1], CJK_CANDIDATES[2], CJK_CANDIDATES[0]] if bold
                  else [CJK_CANDIDATES[0], CJK_CANDIDATES[2]])
    for path in candidates:
        if path and path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)


def build_screenshots_pdf() -> Path:
    path = PACKAGE / "UI_Screenshots.pdf"
    pages: list = []
    for index, (filename, title, caption) in enumerate(SHOTS, start=1):
        image_path = SHOTS_DIR / filename
        if not image_path.exists():
            raise SystemExit(f"缺少截图：{image_path}（先跑 node web/e2e/capture-status-shots.mjs）")
        with Image.open(image_path) as raw:
            shot = raw.convert("RGB")

        page = Image.new("RGB", (PAGE_W, PAGE_H), "white")
        draw = ImageDraw.Draw(page)
        title_font = load_font(34, bold=True)
        sub_font = load_font(20)
        caption_font = load_font(21)
        label_font = load_font(22, bold=True)

        draw.text((MARGIN, 78), "Curtain Wall Inspection Report Tool — UI Evidence",
                  font=title_font, fill=ACCENT)
        draw.text((MARGIN, 126),
                  f"Delivered package v1.0.1  ·  mobile viewport 375×812  ·  "
                  f"Figure {index} of {len(SHOTS)}",
                  font=sub_font, fill=MUTED)
        draw.line((MARGIN, 166, PAGE_W - MARGIN, 166), fill=RULE, width=2)

        # 截图：按可用高度等比缩放到页面里，居中
        box_top = 210
        caption_height = 28 + 26 * len(caption) + 20
        box_bottom = PAGE_H - MARGIN - caption_height
        available_w = PAGE_W - 2 * MARGIN
        available_h = box_bottom - box_top
        scale = min(available_w / shot.width, available_h / shot.height)
        target = (max(1, int(shot.width * scale)), max(1, int(shot.height * scale)))
        page.paste(shot.resize(target, Image.LANCZOS),
                   ((PAGE_W - target[0]) // 2, box_top))

        # 说明
        y = box_bottom + 16
        draw.text((MARGIN, y), title, font=label_font, fill=INK)
        y += 30
        for line in caption:
            draw.text((MARGIN, y), line, font=caption_font, fill=MUTED)
            y += 26

        pages.append(page)

    first, rest = pages[0], pages[1:]
    first.save(path, format="PDF", resolution=150.0, save_all=True, append_images=rest)
    return path


# --------------------------------------------------------------------------
# 3) 组装 + 打包
# --------------------------------------------------------------------------
def assemble() -> list:
    if not WBS_PDF.exists():
        raise SystemExit("缺少 WBS PDF：先跑 python tools/make_current_wbs.py")
    sample = SHOTS_DIR / "Sample_Report.docx"
    if not sample.exists():
        raise SystemExit("缺少样例报告：先跑 node web/e2e/capture-status-shots.mjs")

    PACKAGE.mkdir(parents=True, exist_ok=True)
    for stale in PACKAGE.iterdir():                 # 每次重来，避免残留上一次的旧文件
        stale.unlink() if stale.is_file() else shutil.rmtree(stale)

    (PACKAGE / "ReadMe.txt").write_text(README, encoding="utf-8")
    shutil.copy2(WBS_PDF, PACKAGE / "WBS_Update.pdf")
    shutil.copy2(sample, PACKAGE / "Sample_Report.docx")

    made = [
        build_qa_summary(),
        build_screenshots_pdf(),
        PACKAGE / "WBS_Update.pdf",
        PACKAGE / "Sample_Report.docx",
        PACKAGE / "ReadMe.txt",
    ]
    return sorted(made)


def zip_package() -> Path:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PACKAGE.rglob("*")):
            if path.is_file():
                archive.write(path, Path(PACKAGE.name) / path.relative_to(PACKAGE))
    return ZIP_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="组装进度会议上传材料")
    parser.add_argument("--zip", action="store_true", help="组装后再打成一个 zip")
    parser.add_argument("--zip-only", action="store_true",
                        help="只打包，不重新组装（QA 摘要 PDF 是外部步骤生成的，别覆盖掉）")
    args = parser.parse_args()

    if args.zip_only:
        archive = zip_package()
        print(f"✅ 压缩包：{archive.relative_to(ROOT)}（{archive.stat().st_size / 1024:.1f} KB）")
        return 0

    files = assemble()
    print(f"✅ 材料已放入 {PACKAGE.relative_to(ROOT)}/（{len(files)} 个文件）")
    for path in files:
        print(f"   · {path.name:<26} {path.stat().st_size / 1024:6.1f} KB")
    print("   下一步：QA_Evidence_Summary.pdf 由 _work/status/QA_Evidence_Summary.docx 用 Word 转出")
    print("           （见 docs/management/status_update_package说明.md），然后再 --zip-only 打包")
    if args.zip:
        archive = zip_package()
        print(f"✅ 压缩包：{archive.relative_to(ROOT)}（{archive.stat().st_size / 1024:.1f} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
