# -*- coding: utf-8 -*-
"""M5-0 侦察的验证器：用**闸门自己的比较口径**核对"6 个补丁是否把差异抹平"。

为什么不另写一套判断：本阶段要回答的是"这些差异闸门到底抓不抓"，
所以必须复用 ``tools/compare_report_with_sample.py`` 的
``section_fingerprint`` / ``table_fingerprint`` / ``cell_fingerprint`` ——
另写一套判断只会引入"比闸门松或紧"的不确定性。

用法::

    node tools/js/prototype_postprocess.mjs            # 先产出 _work/spike.docx 与 _work/spike_patched.docx
    python tools/verify_docx_patches.py                # 核对，6 项全绿则退出码 0

    # 或指定文件
    python tools/verify_docx_patches.py --fixture <基线.docx> --raw <库原始.docx> --patched <打补丁.docx>
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lxml import etree                                                    # noqa: E402

from tools.compare_report_with_sample import (cell_fingerprint,           # noqa: E402
                                             section_fingerprint,
                                             table_fingerprint)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# 样例里的行下标：表头 1 行 → 第一条数据行 1、续行 2；基线：表头 2 行 → 数据行 2、续行 3
RAW_DATA_ROW, RAW_CONT_ROW = 1, 2
FIX_DATA_ROW, FIX_CONT_ROW = 2, 3


def body_of(path: Path):
    with zipfile.ZipFile(path) as archive:
        return etree.fromstring(archive.read("word/document.xml")).find(W + "body")


def font_probe(path: Path) -> tuple:
    with zipfile.ZipFile(path) as archive:
        styles = archive.read("word/styles.xml").decode("utf-8")
        theme = archive.read("word/theme/theme1.xml").decode("utf-8")
    return ('w:eastAsiaTheme="minorEastAsia"' in styles,
            'w:ascii="Times New Roman"' in styles,
            "等线" in theme)


def main() -> int:
    parser = argparse.ArgumentParser(description="核对 docx JS 输出的 6 个补丁")
    parser.add_argument("--fixture", default="tests/fixtures/检测表_真实裁剪.docx")
    parser.add_argument("--raw", default="_work/spike.docx")
    parser.add_argument("--patched", default="_work/spike_patched.docx")
    args = parser.parse_args()

    paths = {name: Path(value) for name, value in
             (("基线", args.fixture), ("库原始", args.raw), ("打补丁后", args.patched))}
    for label, path in paths.items():
        if not path.exists():
            raise SystemExit("找不到%s：%s（先跑 node tools/js/prototype_postprocess.mjs）" % (label, path))

    bodies = {label: body_of(path) for label, path in paths.items()}
    sects = {label: section_fingerprint(body.find(W + "sectPr")) for label, body in bodies.items()}
    tables = {label: table_fingerprint(body.findall(W + "tbl")[0]) for label, body in bodies.items()}

    failures = []

    def check(label, expected, raw, patched):
        ok = patched == expected
        print("\n%s" % label)
        print("  基线期望 : %s" % (expected,))
        print("  库原始   : %s   %s" % (raw, "← 差异，闸门会抓" if raw != expected else "（本来就一致）"))
        print("  打补丁后 : %s   %s" % (patched, "✅ 一致" if ok else "❌ 仍不一致"))
        if not ok:
            failures.append(label)

    print("=" * 78)
    print("用闸门口径核对 6 个补丁（基线 fixture vs 库原始 vs 打补丁后）")
    print("=" * 78)

    check("① docGrid", sects["基线"]["docGrid"], sects["库原始"]["docGrid"], sects["打补丁后"]["docGrid"])
    check("② tblLook", tables["基线"]["tblLook"], tables["库原始"]["tblLook"], tables["打补丁后"]["tblLook"])
    check("③ trHeight（第一条数据行）",
          tables["基线"]["rows"][FIX_DATA_ROW]["trHeight"],
          tables["库原始"]["rows"][RAW_DATA_ROW]["trHeight"],
          tables["打补丁后"]["rows"][RAW_DATA_ROW]["trHeight"])
    check("④ tblCellMar", tables["基线"]["tblCellMar"], tables["库原始"]["tblCellMar"],
          tables["打补丁后"]["tblCellMar"])

    print("\n⑤ 续行格")
    cells = {}
    for label, (row, table) in (("基线", (FIX_CONT_ROW, tables["基线"])),
                                ("库原始", (RAW_CONT_ROW, tables["库原始"])),
                                ("打补丁后", (RAW_CONT_ROW, tables["打补丁后"]))):
        cells[label] = table["rows"][row]["cells"][0]
    for key in ("vMerge", "vAlign", "tcMar", "paragraphs"):
        expected, raw, patched = (cells["基线"][key], cells["库原始"][key], cells["打补丁后"][key])
        ok = patched == expected
        note = "✅ 一致" if ok else "❌ 仍不一致"
        if key == "paragraphs" and raw == expected:
            note = "（本来就一致）"
        print("  %-11s 基线=%-42s 库原始=%-42s 打补丁后=%s %s"
              % (key, expected, raw, patched, note))
        if not ok:
            failures.append("⑤ 续行格 %s" % key)

    print("\n⑥ styles.xml / theme1.xml（字体来源）")
    fonts = {label: font_probe(path) for label, path in paths.items()}
    for label, value in fonts.items():
        print("  %-8s eastAsiaTheme=%s ascii=TimesNewRoman:%s theme含等线=%s"
              % (label, *value))
    if fonts["打补丁后"] != fonts["基线"]:
        failures.append("⑥ 字体来源")
        print("  ❌ 与基线不同")
    else:
        print("  ✅ 与基线一致")

    print("\n" + "=" * 78)
    if failures:
        print("结论：仍有 %d 项不一致：%s" % (len(failures), failures))
        return 1
    print("结论：6 个补丁全部把差异抹平 ✅（另外 2 处差异由闸门口径自然吸收，不需要补丁）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
