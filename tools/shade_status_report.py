# -*- coding: utf-8 -*-
"""给状态报告里的"状态行"上色（课程模板要求每行用颜色标注 Green / Yellow / Red）。

docx_create 只能生成黑白的表格，所以这里用 python-docx 后处理：
把 *状态总表* 的每一行数据行刷成浅绿底（#E8F5E9），并在"Status"单元格里
用深绿字突出 `[X] No major issues`。只动这一个表格，其余内容与样式保持不变。

用法：python tools/shade_status_report.py <docx 路径>
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import RGBColor

GREEN_FILL = "E8F5E9"      # 浅绿底
GREEN_TEXT = RGBColor(0x1E, 0x7B, 0x34)


def shade(cell, fill: str) -> None:
    """给单元格加底色（w:shd）。"""
    properties = cell._tc.get_or_add_tcPr()
    for existing in properties.findall(qn("w:shd")):
        properties.remove(existing)
    shd = properties.makeelement(qn("w:shd"), {
        qn("w:val"): "clear",
        qn("w:color"): "auto",
        qn("w:fill"): fill,
    })
    properties.append(shd)


def find_status_table(document):
    """状态总表 = 表头第二列写着 'Status' 的那张。"""
    for table in document.tables:
        if len(table.columns) < 3:
            continue
        header = [cell.text.strip() for cell in table.rows[0].cells]
        if len(header) >= 2 and header[1].lower() == "status":
            return table
    return None


def main(argv: list) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"× 文件不存在：{path}")
        return 1

    document = Document(str(path))
    table = find_status_table(document)
    if table is None:
        print("× 没找到状态总表（表头第二列应为 Status）")
        return 1

    shaded = 0
    for row in table.rows[1:]:                       # 跳过表头
        status_cell = row.cells[1]
        text = status_cell.text.strip()
        if "No major issues" not in text:
            continue                                  # 将来若有 Yellow/Red 行，这里按颜色分支
        for cell in row.cells:
            shade(cell, GREEN_FILL)
        for paragraph in status_cell.paragraphs:
            for run in paragraph.runs:
                run.font.color.rgb = GREEN_TEXT
                run.font.bold = True
        shaded += 1

    document.save(str(path))
    print(f"✅ 已给 {shaded} 行状态行刷上绿色底（{GREEN_FILL}）：{path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
