# -*- coding: utf-8 -*-
"""从真实报告里裁剪出对拍基准：**只保留两张检测表**及其必要的段落骨架。

背景
----
客户真实报告（`docs/samples/A06YG-2026-001…doc`）第 12-13 页是表2-4（立柱）与表2-5（横梁），
是全项目唯一需要逐属性对齐的对象。整份报告转换后 32MB，不适合作为 git 基准，
因此这里把它裁剪成"两张检测表 + 我们这一层的段落骨架"，体积降到几十 KB。

裁剪规则
--------
- 每张表保留：表头 2 行 + 真实数据行；
- **丢掉 `/` 填充行**（真实表的固定行数填充，明确不在范围内）；
- 丢掉「备注 / 检测示意图 / 结论」等行（它们在同一表格元素内，但不在范围内）；
- 表格之外的正文（封面、目录、其他附件）全部丢弃，只放回我们自己的骨架：
  信息段 5 行 → 章节标题 → 表 → 空段 → 章节标题 → 表 → 空段 → 备注 → 文末空段。

**权威边界**：表格（表级/行级/单元格级全部属性）以真实报告为准；
段落骨架是我们自己的（客户端那部分结构不在范围内），故不构成对外承诺。

用法::

    python tools/build_fixture.py                      # 用默认源文件
    python tools/build_fixture.py --source <docx> --output <fixture.docx>
"""

from __future__ import annotations

import argparse
import copy
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lxml import etree                                          # noqa: E402

from webapp import config                                       # noqa: E402
from webapp.services import word_report as wr                   # noqa: E402

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

DEFAULT_SOURCE = config.BASE_DIR / "_work" / "A06YG_full.docx"

# 信息段的取值：**故意脱敏**。
# 它是我们自己的段落骨架（客户端那部分结构不在范围内），与表格逐属性对拍无关；
# 真实报告里的房屋地点/委托单位等属于不必要进入仓库的信息，故不从中提取。
FIXTURE_INFO = {
    "project_no": "A06YG-2026-001",
    "house_name": "示例项目（脱敏）",
    "house_address": "",
    "client_org": "",
    "test_date": "",
}


def text_of(element) -> str:
    return "".join(node.text or "" for node in element.iter(W + "t"))


def find_detection_tables(root):
    """找出立柱/横梁截面尺寸检测表：表头首行含「楼层」，末列含「立柱」或「横梁」。"""
    found = {}
    for tbl in root.iter(W + "tbl"):
        rows = tbl.findall(W + "tr")
        if not rows:
            continue
        header = [text_of(tc) for tc in rows[0].findall(W + "tc")]
        if not any("楼层" in cell for cell in header):
            continue
        last = header[-1]
        if "立柱截面" in last and "column" not in found:
            found["column"] = tbl
        elif "横梁截面" in last and "beam" not in found:
            found["beam"] = tbl
    return found


def crop_table(tbl):
    """裁掉 `/` 填充行与「备注」及其后的行，返回 ``(新表格元素, 数据行数)``。

    ⚠️ 只能跳过**明确写着 ``/`` 的填充行**：纵向合并的续行（同一构件的第 2 个检测面）
    首格是空的，必须保留，否则会把 B/H 两面里的 H 行整行删掉、合并结构也随之破坏。
    """
    rows = tbl.findall(W + "tr")
    keep = [0, 1]
    for index, tr in enumerate(rows[2:], start=2):
        cells = tr.findall(W + "tc")
        first = text_of(cells[0]).strip() if cells else ""
        if first.startswith("备注"):
            break                                   # 备注及其后（示意图/结论）全部丢弃
        if first == "/":
            continue                                # 固定行数填充，不在范围内
        keep.append(index)

    cropped = copy.deepcopy(tbl)
    for index, tr in enumerate(cropped.findall(W + "tr")):
        if index not in keep:
            cropped.remove(tr)
    return cropped, len(keep) - 2


def extract_info(root) -> dict:
    """返回信息段取值（脱敏的固定值）。

    保留函数是为了将来需要"从真实报告取信息段"时有个落点；当前刻意不提取，
    见 :data:`FIXTURE_INFO` 的说明。
    """
    return dict(FIXTURE_INFO)


def build(source=None, output=None) -> Path:
    source = Path(source or DEFAULT_SOURCE)
    output = Path(output or config.GOLDEN_SAMPLE)
    if not source.exists():
        raise SystemExit(
            "找不到转换后的报告：%s\n"
            "请先用 Word 把 .doc 转成 .docx（见 tools/README 或 M3 交接说明）" % source)

    with zipfile.ZipFile(source) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))

    tables = find_detection_tables(root)
    missing = [key for key in ("column", "beam") if key not in tables]
    if missing:
        raise SystemExit("报告里没找到这些检测表：%s" % "、".join(missing))

    cropped = {key: crop_table(tbl) for key, tbl in tables.items()}
    for key, (tbl, data_rows) in cropped.items():
        print("  %s 表：裁剪后 %d 行（表头 2 + 数据 %d）"
              % ({"column": "立柱", "beam": "横梁"}[key],
                 len(tbl.findall(W + "tr")), data_rows))

    info = extract_info(root)
    print("  信息段取值：%s" % info)

    doc = wr.new_document()
    wr.apply_a4_layout(doc)                         # 应用真实报告的页面参数

    for line in wr.info_lines(info):
        wr.add_info_line(doc, line)

    body = doc.element.body
    sect_pr = body.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sectPr")
    for template_type in config.TEMPLATE_TYPES:
        wr.add_section_title(doc, config.TEMPLATE_TITLES[template_type])
        sect_pr.addprevious(cropped[template_type][0])   # 表格插在 sectPr 之前
        wr.add_spacer(doc)

    wr.add_note(doc, config.NOTE_TEXT)
    wr.add_trailing_empty(doc)

    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="从真实报告裁剪出对拍基准")
    parser.add_argument("--source", help="转换后的真实报告 .docx（默认 _work/A06YG_full.docx）")
    parser.add_argument("--output", help="输出的裁剪版 fixture（默认 tests/fixtures/检测表_真实裁剪.docx）")
    args = parser.parse_args()

    output = build(args.source, args.output)
    print("已生成对拍基准：%s（%d 字节）" % (output, output.stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
