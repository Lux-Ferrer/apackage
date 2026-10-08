# -*- coding: utf-8 -*-
"""证明**闸门不是摆设**：往产物里下"毒"，看闸门抓不抓得住。

为什么需要这个工具
------------------
闸门绿了只说明"两个文件在这些属性上相等"。但**相等**也可能是因为"这个属性根本没被比对"
—— 那是最危险的一种绿：看起来验过了，其实验的是空气。
M5-3 加附页时正好踩到这个盲区：段落指纹里原本**完全没有图片**，
一张图嵌错尺寸、嵌错文件、或者干脆漏嵌，闸门都会照样说"全部一致"。

所以这个工具做两件事：
  1. **阴性对照**：原样的一对文件必须 0 差异（否则说明有假阳性，绿得没意义）；
  2. **阳性对照**：逐个下毒 —— 每个毒都必须被抓到，且抓到的路径要落在预期的那一类上。

毒的种类（每一项对应闸门的一个比对维度）：
  ``image_extent``  把一张图的显示尺寸（``wp:extent/@cx``）改小 → 应落在段落 ``images``
  ``image_media``   把媒体部件换成另一种尺寸的图（"嵌错了文件"）→ 应落在顶层 ``media``
  ``drop_drawing``  删掉一个 ``<w:drawing>``（"漏嵌了"）→ 应落在段落 ``images``
  ``table_text``    改一个字 → 应落在表格文本
  ``table_merge``   删掉一个 ``<w:vMerge/>`` → 应落在合并网格 ``grid``
  ``row_height``    改一个行高 → 应落在 ``table[...].rows[...]``
  ``bold_label``    去掉附页标签的 ``<w:b/>`` → 应落在 run 属性

用法::

    python tools/verify_gate_sensitivity.py                  # 默认测附页产物
    python tools/verify_gate_sensitivity.py --expected A --actual B
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.compare_report_with_sample import run_pair_comparison    # noqa: E402

DEFAULT_EXPECTED = ROOT / "tests" / "fixtures" / "attachment_baseline.docx"
DEFAULT_ACTUAL = ROOT / "_work" / "js_generated_attachments.docx"


# --------------------------------------------------------------------------
# 下毒
# --------------------------------------------------------------------------
def _replace_document(source: Path, target: Path, transform) -> Path:
    """把 docx 复制一份，只改 ``word/document.xml``。"""
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/document.xml":
                data = transform(data.decode("utf-8")).encode("utf-8")
            dst.writestr(item, data)
    return target


def poison_image_extent(xml: str) -> str:
    """第一张图的显示宽度减半（模拟"尺寸算错"）。"""
    return xml.replace('cx="5588000" cy="4191000"', 'cx="2794000" cy="4191000"', 1)


def poison_drop_drawing(xml: str) -> str:
    """删掉第一个图片段落里的 drawing（模拟"漏嵌了"）。"""
    return xml.replace("<w:drawing>", "<w:drawing-removed>", 1).replace(
        "</w:drawing>", "</w:drawing-removed>", 1)


def poison_table_text(xml: str) -> str:
    """把第一处「密封胶开裂」改一个字。"""
    return xml.replace("密封胶开裂", "密封胶开列", 1)


def poison_table_merge(xml: str) -> str:
    """删掉一个纵向合并的续格标记（模拟"合并结构变了"）。"""
    return xml.replace("<w:vMerge/>", "<w:vMerge w:val=\"continue\"/>", 1)


def poison_row_height(xml: str) -> str:
    """把第一个 400 的行高改成 500。"""
    return xml.replace('<w:trHeight w:val="400"/>', '<w:trHeight w:val="500"/>', 1)


def poison_bold_label(xml: str) -> str:
    """去掉附页标签的加粗（模拟"样式没对上"）。"""
    return xml.replace("<w:rPr><w:b/><w:bCs/></w:rPr><w:t xml:space=\"preserve\">缺陷类型",
                       "<w:rPr/><w:t xml:space=\"preserve\">缺陷类型", 1)


def poison_image_media(source: Path, target: Path) -> Path:
    """把第一个媒体部件换成另一尺寸的图（模拟"嵌错了文件"）。"""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (320, 200), (10, 20, 30)).save(buffer, "JPEG", quality=70)
    replacement = buffer.getvalue()

    replaced = False
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            is_media = item.filename.startswith("word/media/") and not item.filename.endswith("/")
            if is_media and not replaced:
                data = replacement
                replaced = True
            dst.writestr(item, data)
    if not replaced:
        raise SystemExit("产物里没有媒体部件，无法测 image_media")
    return target


# 每项：(名字, 期望落在哪个路径前缀上, 说明)
DOCUMENT_POISONS = (
    ("image_extent", "images", "图片显示尺寸改小"),
    ("drop_drawing", "images", "删掉一个 drawing（漏嵌）"),
    ("table_text", "table[", "表格文本改一个字"),
    ("table_merge", "grid", "vMerge 续格标记被写成 val=\"continue\""),
    ("row_height", "rows[", "行高 400 → 500"),
    ("bold_label", "run_props", "附页标签去掉加粗"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="验证对拍闸门对图片/文本/合并结构确实敏感")
    parser.add_argument("--expected", default=str(DEFAULT_EXPECTED))
    parser.add_argument("--actual", default=str(DEFAULT_ACTUAL))
    args = parser.parse_args()

    expected, actual = Path(args.expected), Path(args.actual)
    for label, path in (("期望文件", expected), ("实际文件", actual)):
        if not path.exists():
            print("找不到%s：%s" % (label, path))
            print("  先跑：node tools/js/generate_from_fixture.mjs")
            return 2

    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        # 1) 阴性对照：原样必须 0 差异
        result = run_pair_comparison(expected, actual)
        baseline_diffs = len(result["diffs"])
        print("阴性对照（原样一对）：%s"
              % ("0 差异 ✅" if baseline_diffs == 0 else "竟然有 %d 处差异 ❌" % baseline_diffs))
        if baseline_diffs:
            for path, exp, act in result["diffs"][:5]:
                print("    %s 期望=%r 实际=%r" % (path, exp, act))
            failures.append("阴性对照不为 0（有假阳性）")

        # 2) 阳性对照：逐个下毒
        print("\n阳性对照（逐个下毒，每个都必须被抓到）：")
        print("| 毒 | 说明 | 抓到 | 落在 |")
        print("| --- | --- | --- | --- |")
        rows = []
        for name, expected_prefix, note in DOCUMENT_POISONS:
            poisoned = tmpdir / ("%s.docx" % name)
            _replace_document(actual, poisoned, globals()["poison_%s" % name])
            caught, hit = _probe(expected, poisoned)
            ok = caught and expected_prefix in hit
            rows.append((name, note, caught, hit, ok))

        poisoned = poison_image_media(actual, tmpdir / "image_media.docx")
        caught, hit = _probe(expected, poisoned)
        rows.append(("image_media", "媒体部件换成 320×200", caught, hit, caught and "media" in hit))

        for name, note, caught, hit, ok in rows:
            print("| `%s` | %s | %s | `%s` |"
                  % (name, note, "✅" if caught else "❌ 没抓到", hit or "—"))
            if not ok:
                failures.append("%s：期望落在 `%s`，实际 %s"
                                % (name, _expected_prefix(name), hit or "没抓到任何差异"))

    if failures:
        print("\n结果：不合格 %d 项 ❌" % len(failures))
        for item in failures:
            print("  - %s" % item)
        return 1

    print("\n结果：闸门对这些维度都敏感 ✅（阴性 0 差异 + %d 项下毒全部被抓到）" % len(rows))
    return 0


def _expected_prefix(name: str) -> str:
    for poison, prefix, _note in DOCUMENT_POISONS:
        if poison == name:
            return prefix
    return "media"


def _probe(expected: Path, poisoned: Path):
    """返回（是否抓到差异, 命中的路径列表）。

    保留**完整路径**（只做去重与截断）：路径本身就是证据 ——
    "抓到差异"还不够，要看它抓的是不是**该抓的那个属性**
    （比如去掉加粗应当落在 `run_props`，而不是笼统地"表格有差异"）。
    """
    result = run_pair_comparison(expected, poisoned)
    diffs = result["diffs"]
    if not diffs:
        return False, ""
    paths = sorted({path for path, _e, _a in diffs})
    hit = ", ".join(paths[:3])
    if len(paths) > 3:
        hit += " 等 %d 条" % len(paths)
    return True, hit


if __name__ == "__main__":
    sys.exit(main())
