#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组装 Final Report 终稿：合并三个草稿 → 一份 Markdown → 一份按规范排版的 .docx。

排版按学校规范（06 Guidelines）：
  · 正文 Calibri 12pt、**双倍行距**
  · 页边距：**左 1.5"**、右 1"、上下 1"
  · 页眉留白；页脚**只有居中页码**
  · 图表居中，图注在图下方
  · 封面页按规范字段；目录用 TOC 域（Word 打开后自动更新页码）

用法::

    python tools/build_final_report.py                 # 生成 docs/release/final/Final-Report-v1.md + .docx
    python tools/build_final_report.py --no-docx       # 只合 Markdown
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
MGMT = ROOT / "docs" / "management"
OUT_MD = ROOT / "docs" / "release" / "final" / "Final-Report-v1.md"
OUT_DOCX = ROOT / "docs" / "release" / "final" / "Final-Report-v1.docx"

SOURCES = {
    "front": MGMT / "Final-Report-front-back.md",
    "ch45": MGMT / "Final-Report-draft-ch4-ch5.md",
    "ch67": MGMT / "Final-Report-draft-ch6-ch7.md",
}

TITLE = ("Faithful by Construction: An Offline-First Field Tool that Reproduces\n"
         "Corporate Inspection Reports Attribute by Attribute")

STUDENT = "Zeyu Jin"
NETID = "ZJ663"
SEMESTER = "Fall, 2026"

FIGURES = {
    "architecture": (
        ROOT / "deliverables/prp/architecture.png",
        "Figure 5.1 — System architecture. Left: the frozen Flask reference implementation that "
        "produced the accepted report. Right: the offline client that had to reproduce it. Both write "
        "the same Word document from the same layout specification; the difference is where the work "
        "and the data live."),
    "sensitivity": (
        ROOT / "deliverables/prp/gate-sensitivity.png",
        "Figure 7.1 — Gate sensitivity. Each of the poisoned documents is injected into a known-good "
        "report and must be caught at a specific comparison path, not merely rejected."),
    "convergence": (
        ROOT / "deliverables/prp/gate-convergence.png",
        "Figure 7.2 — Fidelity gate A convergence: 201 → 33 → 2 → 0 differences over four rounds, "
        "closed by eleven attribute-level patches without loosening the comparison."),
}


# ---------------------------------------------------------------------------
# 1. 合稿
# ---------------------------------------------------------------------------
def slice_between(text: str, start: str, end: str) -> str:
    try:
        begin = text.index(start)
    except ValueError:
        raise SystemExit(f"找不到起点标记：{start[:40]}")
    try:
        finish = text.index(end, begin)
    except ValueError:
        raise SystemExit(f"找不到终点标记：{end[:40]}")
    return text[begin:finish]


def drop_cn_notes(text: str) -> str:
    """删掉草稿里给审阅用的"## 中文对照…"块（到下一个一级标题或文件末尾为止）。"""
    return re.sub(r"\n## 中文对照.*?(?=\n# |\Z)", "\n", text, flags=re.S)


PAGES_JSON = ROOT / "_work" / "report-pages.json"

LIST_ITEMS = {
    "LOF": [
        ("Figure 5.1", "System architecture: the frozen reference implementation and the offline client"),
        ("Figure 7.1", "Gate sensitivity: seven poisoned documents, each caught at a specific comparison path"),
        ("Figure 7.2", "Fidelity gate A convergence: 201 → 33 → 2 → 0 differences over four rounds"),
    ],
    "LOT": [
        ("Table 4.1", "As-is versus to-be process"),
        ("Table 4.2", "Functional requirements (core)"),
        ("Table 4.3", "Alternatives against the deciding criteria"),
        ("Table 4.4", "Risk register with outcomes"),
        ("Table 5.1", "Layers, responsibilities and failure modes"),
        ("Table 5.2", "Object stores"),
        ("Table 5.3", "The eleven post-processing patches"),
        ("Table 7.1", "The verification layers"),
        ("Table 7.2", "What each gate compares, and what it cannot see"),
        ("Table 7.3", "The seven poisons"),
        ("Table 7.4", "What jsdom cannot see"),
        ("Table 7.5", "The nine defects"),
        ("Table 7.6", "Measured performance"),
        ("Table 8.1", "Requirement coverage at acceptance"),
    ],
}


def inject_lists(text: str) -> str:
    """把 <!--LOF--> / <!--LOT--> 换成真正的图表清单（页码来自 _work/report-pages.json）。

    页码是"建成之后从 PDF 里量出来再回填"的：先跑一遍不带页码的，量完再回填重跑。
    两遍之间行数不变，所以页码不会因为清单本身而漂移（脚本会自己校验）。
    """
    pages = {}
    if PAGES_JSON.exists():
        pages = json.loads(PAGES_JSON.read_text(encoding="utf-8"))

    for key, items in LIST_ITEMS.items():
        rows = ["| Number | Title | Page |", "| --- | --- | --- |"]
        for number, title in items:
            page = pages.get(number, "")
            rows.append(f"| {number} | {title} | {page} |")
        text = text.replace(f"<!--{key}-->", "\n".join(rows))
    return text


def assemble() -> str:
    for name, path in SOURCES.items():
        if not path.exists():
            raise SystemExit(f"缺少草稿：{path.relative_to(ROOT)}")

    front = SOURCES["front"].read_text(encoding="utf-8")
    ch45 = SOURCES["ch45"].read_text(encoding="utf-8")
    ch67 = SOURCES["ch67"].read_text(encoding="utf-8")

    head = slice_between(front, "# §1 Front matter", "# §8 Results")
    # 前置部分重整：封面由 docx 生成器画，目录用 TOC 域，其余（图表清单/缩写/致谢/声明）原样保留
    head = head[head.index("## 1.2 Abstract"):]
    head = head.replace("## 1.2 Abstract", "# Abstract", 1)
    head = head.replace("## 1.3 Front matter\n", "")
    head = inject_lists(head)
    # 草稿里每章末尾都有"中文对照"审阅块（内部用），合稿时先整体剔除再切片
    mid45 = drop_cn_notes(ch45)[len(ch45[: ch45.index("# Part B — §4")]):]
    mid67 = drop_cn_notes(ch67)
    mid67 = mid67[mid67.index("# §6 Implementation"):]
    tail = front[front.index("# §8 Results"):]

    # 章节标题统一成规范写法
    mid45 = mid45.replace("# Part B — §4 Requirements and Analysis (~1,200 words)",
                          "# §4 Requirements and analysis")
    mid45 = mid45.replace("# Part C — §5 System Design (~1,500 words)", "# §5 System design")
    mid67 = mid67.replace("# §6 Implementation (~1,800 words)", "# §6 Implementation")
    mid67 = mid67.replace("# §7 Evaluation and Quality Assurance (~2,100 words)",
                          "# §7 Evaluation and quality assurance")
    mid67 = mid67.replace("# §6 Implementation", "# §6 Implementation", 1)

    # 轮次口径与图 7.1 一致（图上标 Round 1–4）
    mid45 = mid45.replace("converging 201 → 33 → 2 → 0 differences over three rounds",
                          "converging 201 → 33 → 2 → 0 differences over four rounds")
    mid67 = mid67.replace("After three convergence rounds the diff count went 201 → 33 → 2 → 0",
                          "After four convergence rounds the diff count went 201 → 33 → 2 → 0")

    # 插图（锚点找不到就报错，避免"图悄悄丢了"）
    mid45, n1 = insert_before_marker(
        mid45, "## 5.2 Data model", figure_markdown("architecture"), required=True)
    mid67, n2 = insert_before_marker(
        mid67, "Asserting the *path* of the failure", figure_markdown("sensitivity"), required=True)
    mid67, n3 = insert_before_marker(
        mid67, "Zero differences in our own comparator", figure_markdown("convergence"), required=True)
    print(f"· 已插入插图 {n1 + n2 + n3} 张")

    parts = [head.rstrip(), "---", mid45.strip(), mid67.strip(), tail.strip()]
    return "\n\n".join(parts) + "\n"


def figure_markdown(key: str) -> str:
    path, caption = FIGURES[key]
    return f"![{caption}]({path.relative_to(ROOT).as_posix()})"


def insert_after_marker(text: str, marker: str, block: str, required: bool = False) -> tuple[str, int]:
    if marker not in text:
        if required:
            raise SystemExit(f"插图锚点没找到：{marker[:50]}")
        return text, 0
    index = text.index(marker) + len(marker)
    # 跳到该段末尾（marker 后面可能还有半句话）
    line_end = text.index("\n", index) if "\n" in text[index:] else len(text)
    return text[:line_end] + "\n\n" + block + text[line_end:], 1


def insert_before_marker(text: str, marker: str, block: str, required: bool = False) -> tuple[str, int]:
    if marker not in text:
        if required:
            raise SystemExit(f"插图锚点没找到：{marker[:50]}")
        return text, 0
    index = text.index(marker)
    return text[:index] + block + "\n\n" + text[index:], 1


# ---------------------------------------------------------------------------
# 2. Markdown → docx
# ---------------------------------------------------------------------------
def set_base_styles(document: Document) -> None:
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(12)
    normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.DOUBLE
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.space_before = Pt(0)
    # 中文字体（正文里偶有中文术语）
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "SimSun")

    for level, size in ((1, 18), (2, 14), (3, 12.5)):
        style = document.styles[f"Heading {level}"]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0x1F, 0x3B, 0x5C)
        style.paragraph_format.space_before = Pt(18 if level == 1 else 12)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        style.paragraph_format.keep_with_next = True


def set_page_numbering(section, fmt: str | None = None, start: int | None = None) -> None:
    """给某一节设置页码格式（lowerRoman / decimal）与起始值。

    `w:pgNumType` 在 CT_SectPr 里有固定次序（pgSz → pgMar → … → pgNumType → cols → docGrid），
    所以不能直接 append，必须插在 cols/docGrid 之前，否则 Word 会报文档损坏。
    """
    sect_pr = section._sectPr
    existing = sect_pr.find(qn("w:pgNumType"))
    if existing is not None:
        sect_pr.remove(existing)
    element = OxmlElement("w:pgNumType")
    if fmt:
        element.set(qn("w:fmt"), fmt)
    if start is not None:
        element.set(qn("w:start"), str(start))
    for tag in ("w:cols", "w:docGrid", "w:printerSettings"):
        anchor = sect_pr.find(qn(tag))
        if anchor is not None:
            anchor.addprevious(element)
            return
    sect_pr.append(element)


def add_page_number_footer(section, numbering: bool = True) -> None:
    """页脚：只有居中的页码（规范 41）。numbering=False 时页脚留空（封面页）。"""
    footer = section.footer
    footer.is_linked_to_previous = False
    paragraph = footer.paragraphs[0]
    paragraph.text = ""
    if not numbering:
        return
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    field_begin = OxmlElement("w:fldChar")
    field_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    field_end = OxmlElement("w:fldChar")
    field_end.set(qn("w:fldCharType"), "end")
    run._r.append(field_begin)
    run._r.append(instr)
    run._r.append(field_end)


def add_toc_field(document: Document) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-3" \\h \\z \\u'
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t")
    placeholder.text = "Right-click and choose Update Field to build the table of contents."
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for element in (begin, instr, separate, placeholder, end):
        run._r.append(element)


def add_title_page(document: Document) -> None:
    def center(text: str, size: float, bold: bool = False, space_after: float = 12) -> None:
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        paragraph.paragraph_format.space_after = Pt(space_after)
        run = paragraph.add_run(text)
        run.font.size = Pt(size)
        run.bold = bold

    # 封面版式照 06 Guidelines 的 Sample Cover Page（文本框里的字段顺序）：
    #   标题 / Applied Technical Project / Final Report / by / 姓名 / NETID / 学期年份 / 学位与院校段
    center("", 12, space_after=48)
    center(TITLE, 20, bold=True, space_after=18)
    center("Applied Technical Project", 13, space_after=2)
    center("Final Report", 13, space_after=24)
    center("by", 12, space_after=6)
    center(STUDENT, 14, bold=True, space_after=4)
    center(NETID, 12, space_after=4)
    center(SEMESTER, 12, space_after=30)
    center("A paper submitted in partial fulfillment of the requirements for the degree of", 12, space_after=6)
    center("Master of Science", 14, bold=True, space_after=20)
    center("at the", 12, space_after=6)
    center("Division of Programs in Business", 12, space_after=2)
    center("School of Professional Studies", 12, space_after=2)
    center("New York University", 12, bold=True, space_after=24)
    center("Sponsoring organization: MCC Central Research Institute of Building and Construction (Shenzhen) Co., Ltd.",
           10, space_after=0)
    document.add_page_break()


INLINE_BOLD = re.compile(r"\*\*(.+?)\*\*")
INLINE_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def add_runs(paragraph, text: str) -> None:
    """把 **粗体** / *斜体* / `代码` 拆成 run（其余原样）。"""
    tokens = re.split(r"(\*\*.+?\*\*|(?<!\*)\*[^*]+\*(?!\*)|`[^`]+`)", text)
    for token in tokens:
        if not token:
            continue
        if token.startswith("**") and token.endswith("**"):
            paragraph.add_run(token[2:-2]).bold = True
        elif token.startswith("`") and token.endswith("`") and len(token) > 2:
            run = paragraph.add_run(token[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(10.5)
        elif token.startswith("*") and token.endswith("*") and len(token) > 2:
            paragraph.add_run(token[1:-1]).italic = True
        else:
            paragraph.add_run(token)


def add_table(document: Document, rows: list[list[str]]) -> None:
    header, body = rows[0], rows[1:]
    table = document.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for index, cell_text in enumerate(header):
        cell = table.rows[0].cells[index]
        cell.text = ""
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        add_runs(paragraph, cell_text)
        for run in paragraph.runs:
            run.bold = True
            run.font.size = Pt(10)
    for row in body:
        cells = table.add_row().cells
        for index, cell_text in enumerate(row[: len(header)]):
            paragraph = cells[index].paragraphs[0]
            paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
            add_runs(paragraph, cell_text)
            for run in paragraph.runs:
                run.font.size = Pt(10)
    spacer = document.add_paragraph()
    spacer.paragraph_format.space_after = Pt(6)
    spacer.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE


def add_figure(document: Document, alt: str, rel_path: str) -> None:
    path = ROOT / rel_path
    if not path.exists():
        raise SystemExit(f"缺少插图：{rel_path}")
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(6)
    paragraph.add_run().add_picture(str(path), width=Inches(6.0))
    caption = document.add_paragraph()
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    caption.paragraph_format.space_after = Pt(12)
    run = caption.add_run(alt)
    run.font.size = Pt(9)
    run.italic = True


def convert(markdown: str) -> Document:
    document = Document()
    section = document.sections[0]
    section.left_margin = Inches(1.5)
    section.right_margin = Inches(1.0)
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)
    set_base_styles(document)

    # 规范 41：封面不编号、也不带页脚；前置页用罗马数字；正文从阿拉伯数字 1 开始
    add_page_number_footer(section, numbering=False)
    add_title_page(document)

    front = document.add_section(WD_SECTION.NEW_PAGE)
    front.left_margin = Inches(1.5)
    front.right_margin = Inches(1.0)
    front.top_margin = Inches(1.0)
    front.bottom_margin = Inches(1.0)
    set_page_numbering(front, fmt="lowerRoman", start=1)
    add_page_number_footer(front)

    # 目录页：用普通粗体段落（不用 Heading，避免目录把自己列进去）
    toc_title = document.add_paragraph()
    toc_title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    toc_title.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    toc_title.paragraph_format.space_after = Pt(12)
    toc_run = toc_title.add_run("Table of contents")
    toc_run.bold = True
    toc_run.font.size = Pt(18)
    toc_run.font.color.rgb = RGBColor(0x1F, 0x3B, 0x5C)
    add_toc_field(document)
    document.add_page_break()

    lines = markdown.split("\n")
    index = 0
    first_heading = True
    while index < len(lines):
        line = lines[index]

        if line.startswith("![") and "](" in line:
            alt = line[2:line.index("](")]
            src = line[line.index("](") + 2: line.rindex(")")]
            add_figure(document, alt, src)
            index += 1
            continue

        if line.startswith("|"):
            block = []
            while index < len(lines) and lines[index].startswith("|"):
                row = lines[index].strip()
                if not re.fullmatch(r"\|[\s:|-]+\|", row):
                    cells = [cell.strip() for cell in row.strip("|").split("|")]
                    block.append(cells)
                index += 1
            if block:
                add_table(document, block)
            continue

        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            level = len(heading[1])
            text = heading[2].strip()
            if level == 1:
                if text.startswith("§2"):
                    # 正文起点：切到新一节，页码改用阿拉伯数字并从 1 开始
                    body = document.add_section(WD_SECTION.NEW_PAGE)
                    body.left_margin = Inches(1.5)
                    body.right_margin = Inches(1.0)
                    body.top_margin = Inches(1.0)
                    body.bottom_margin = Inches(1.0)
                    set_page_numbering(body, fmt="decimal", start=1)
                    add_page_number_footer(body)
                    first_heading = False
                elif not first_heading:
                    document.add_page_break()
                first_heading = False
                if text.startswith("#"):
                    text = text.lstrip("# ").strip()
            paragraph = document.add_heading(level=level)
            add_runs(paragraph, text)
            index += 1
            continue

        if line.strip() in ("---", "***"):
            index += 1
            continue

        if line.startswith("- ") or line.startswith("* "):
            paragraph = document.add_paragraph(style="List Bullet")
            paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.DOUBLE
            add_runs(paragraph, line[2:].strip())
            index += 1
            continue

        if line.startswith("> "):
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Inches(0.4)
            add_runs(paragraph, line[2:].strip())
            for run in paragraph.runs:
                run.italic = True
            index += 1
            continue

        if not line.strip():
            index += 1
            continue

        # 段落：连续非空行合并
        block = [line.strip()]
        index += 1
        while index < len(lines) and lines[index].strip() \
                and not re.match(r"^(#{1,3}\s|\||!\[|- |\* |> |---)", lines[index]):
            block.append(lines[index].strip())
            index += 1
        paragraph = document.add_paragraph()
        add_runs(paragraph, " ".join(block))

    return document


def main() -> int:
    parser = argparse.ArgumentParser(description="组装 Final Report 终稿")
    parser.add_argument("--no-docx", action="store_true", help="只生成 Markdown")
    args = parser.parse_args()

    markdown = assemble()
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(markdown, encoding="utf-8")
    words = len(re.findall(r"[A-Za-z][A-Za-z'-]*", markdown))
    print(f"✅ Markdown：{OUT_MD.relative_to(ROOT)}（英文词数约 {words}）")

    if args.no_docx:
        return 0

    document = convert(markdown)
    document.save(OUT_DOCX)
    print(f"✅ DOCX：{OUT_DOCX.relative_to(ROOT)}（{OUT_DOCX.stat().st_size / 1024:.0f} KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
