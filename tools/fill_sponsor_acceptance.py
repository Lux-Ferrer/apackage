#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""填写学校的两份甲方验收文件（Part 1 计划 / Part 2 结果），数据全部取自本项目真实交付物。

设计取舍
--------
* **不改原模板**：填入后的文件另存为 `... - Zeyu Jin.docx`，模板保持空白可复用；
* **保留原格式**：只改写既有段落的文字（复用第一个 run 的字体），新增段落用 XML 深拷贝继承样式；
* **不编造**：导师/甲方姓名、联系方式、签字、评分一律留空 —— 这些必须真人填。

用法::

    python tools/fill_sponsor_acceptance.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

from docx import Document
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parent.parent
FINAL = ROOT / "docs" / "release" / "final"
PART1 = FINAL / "07-Part1 SponsorsProjectAcceptanceDocument V3.3.docx"
PART2 = FINAL / "07-Part2 SponsorsProjectAcceptanceDocument V3.3.docx"

STUDENT = "Zeyu Jin"
TITLE = ("Curtain Wall Inspection Report Tool: An Offline-First Mobile Web Application "
         "for On-Site Inspection Records and Word Report Generation")
SPONSOR_ORG = "MCC Central Research Institute of Building and Construction (Shenzhen) Co., Ltd."
PLANNED_START, PLANNED_END = "September 10, 2026", "December 5, 2026"
ACTUAL_START, ACTUAL_END = "September 10, 2026", "November 24, 2026"

GOAL = ("Deliver a server-less, offline-capable mobile tool that lets MCC field inspectors record curtain-wall "
        "column and beam cross-section measurements (five thickness readings per detection face, with the "
        "minimum calculated automatically) and defect findings on site, and generate the client's existing "
        "Word inspection report - including defect-report attachment pages - in the same layout the client "
        "uses today.")

OBJECTIVES = [
    ("Report-layout fidelity",
     "By December 5, 2026, every generated .docx shall match the approved client report template "
     "attribute-for-attribute, measured by three independent comparison gates (replicated frozen baseline; the "
     "client's real cropped report; a language-neutral fingerprint self-check) showing zero differences in body "
     "text, tables, rows, cells and embedded images; a sensitivity test must additionally catch 7 of 7 "
     "deliberately injected layout defects."),
    ("Functional scope coverage",
     "By December 5, 2026, 100% of the 43 in-scope requirements in the traceability matrix shall be implemented "
     "and verified - project management, column/beam records (5 readings per face, automatic minimum, up to 6 "
     "faces), defect reporting with photo capture, report management, project-level Word export with optional "
     "attachment pages, and backup/restore - evidenced by 598 automated tests (348 Python + 250 front-end) and "
     "21 real-browser end-to-end cases, all passing."),
    ("Offline, server-less operation",
     "By December 5, 2026, a complete working session (create project -> record measurements -> defect report -> "
     "export Word -> export backup) shall run with zero external network requests and no back-end service, "
     "verified on a real Android device while the application's own network access is blocked at the OS level."),
    ("Field usability on real phones",
     "By December 5, 2026, all primary tap targets shall be at least 44x44 px, the Save action shall remain "
     "visible and tappable when the soft keyboard is open, and the hardware Back key shall return to the previous "
     "screen instead of exiting the form - verified by 21 desktop end-to-end cases and 14 on-device assertions."),
    ("Deliverable and handover readiness",
     "By December 5, 2026, a versioned delivery package (static web bundle plus Android APK) shall be "
     "reproducible with a recorded SHA-256, accompanied by a deployment guide, an end-user manual and the signed "
     "acceptance report, with zero open P0/P1 defects at acceptance."),
]

EVIDENCE = [
    "Gate A (frozen baseline, plain and with attachment pages), Gate B (client's real cropped report) and "
    "Gate C (no-Python self-check) all report 0 differences; the 7 injected defects are all caught.",
    "348 Python tests + 250 front-end tests + 21 Playwright cases green; requirement traceability matrix shows "
    "43 rows implemented, 2 implemented with agreed adaptations, 1 optional item not built, 2 rows and 3 "
    "modules out of scope by agreement.",
    "On the emulator, all 30 page resources were served from the app bundle with 0 external requests; export "
    "still produced a valid 13 KB .docx with the app's network access blocked (iptables, per-application UID).",
    "Measured on device: action bar rises to the keyboard edge (bar bottom 478 px = keyboard top), Save stays "
    "visible; hardware Back returns to the previous screen and only exits at a root tab.",
    "dist/mcc-inspection-tool-v1.0.3.zip (67 files) + APK (versionCode 3, versionName 1.0.3), SHA-256 recorded "
    "for every artifact; deployment guide, end-user manual (8 pages) and acceptance report delivered; no open "
    "P0/P1 defects at acceptance.",
]


def set_text(paragraph: Paragraph, text: str) -> None:
    """改写段落文字但保留第一段的格式。"""
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def insert_after(paragraph: Paragraph, text: str) -> Paragraph:
    """在段落后面插一段（深拷贝原段落，继承样式），返回新段落。"""
    new_xml = copy.deepcopy(paragraph._p)
    paragraph._p.addnext(new_xml)
    inserted = Paragraph(new_xml, paragraph._parent)
    set_text(inserted, text)
    return inserted


def find(document: Document, prefix: str) -> Paragraph | None:
    for paragraph in document.paragraphs:
        if paragraph.text.strip().startswith(prefix):
            return paragraph
    return None


# --------------------------------------------------------------------------
# PART 1：项目计划
# --------------------------------------------------------------------------
def fill_part1() -> Path:
    doc = Document(PART1)

    fields = {
        "Project Title:": f"Project Title: {TITLE}",
        "Student Name:": f"Student Name: {STUDENT}",
        "Sponsoring Organization:": f"Sponsoring Organization: {SPONSOR_ORG}",
        "Project Sponsor Name and Title:": "Project Sponsor Name and Title: ____________________________ (to be completed by sponsor)",
        "Project Sponsor Contact Information": "Project Sponsor Contact Information (email and phone): ____________________________________",
    }
    for prefix, replacement in fields.items():
        paragraph = find(doc, prefix)
        if paragraph is None:
            raise SystemExit(f"Part 1 里找不到：{prefix}")
        set_text(paragraph, replacement)

    goal = find(doc, "Project Goal")
    if goal is None:
        raise SystemExit("Part 1 里找不到 Project Goal")
    set_text(goal, f"Project Goal: {GOAL}")

    # 三个占位的 Objective 段落 → 填前三条，再复制补两条（指南要求至少 3 条，建议 5 条）
    anchors = []
    for index in (1, 2, 3):
        anchor = find(doc, f"Objective #{index}")
        if anchor is None:
            raise SystemExit(f"Part 1 里找不到 Objective #{index}")
        anchors.append(anchor)
        name, detail = OBJECTIVES[index - 1]
        set_text(anchor, f"Objective #{index} - {name}: {detail}")

    last = anchors[-1]
    for index in (4, 5):
        name, detail = OBJECTIVES[index - 1]
        last = insert_after(last, f"Objective #{index} - {name}: {detail}")

    target = FINAL / f"07-Part1 SponsorsProjectAcceptanceDocument V3.3 - {STUDENT}.docx"
    doc.save(target)
    return target


# --------------------------------------------------------------------------
# PART 2：项目结果
# --------------------------------------------------------------------------
def fill_part2() -> Path:
    doc = Document(PART2)

    dates = find(doc, "Planned Start Date:")
    if dates is None:
        raise SystemExit("Part 2 里找不到日期段")
    set_text(dates,
             f"Planned Start Date: {PLANNED_START}\t\tPlanned End Date: {PLANNED_END}")
    actual = find(doc, "Actual    Start Date:")
    if actual is None:
        raise SystemExit("Part 2 里找不到 Actual 日期段")
    set_text(actual,
             f"Actual    Start Date: {ACTUAL_START}\t\tActual    End Date: {ACTUAL_END}")

    goal_line = find(doc, "Project Goal Was the project goal achieved")
    if goal_line is None:
        raise SystemExit("Part 2 里找不到 Goal 判定行")
    set_text(goal_line, "Project Goal: Was the project goal achieved as planned?  Yes.  "
                        "The tool is delivered and in use on real devices; every objective below was measured "
                        "against the metric fixed at project start.")

    # 三条 Objective 标题（正文与 Part 1 完全一致）
    for index in (1, 2, 3):
        heading = find(doc, f"Project Objective #{index}")
        if heading is None:
            raise SystemExit(f"Part 2 里找不到 Project Objective #{index}")
        name, detail = OBJECTIVES[index - 1]
        set_text(heading, f"Project Objective #{index} - {name}: {detail}")

    # 三句"has or has not been met"判定语，按文档顺序对应 #1~#3
    verdicts = [p for p in doc.paragraphs if p.text.strip().startswith("Did the student")]
    if len(verdicts) < 3:
        raise SystemExit(f"Part 2 里应有 3 句 Objective 判定语，实际 {len(verdicts)}")
    for index, paragraph in enumerate(verdicts[:3], start=1):
        set_text(paragraph,
                 f"Did the student's project meet this objective with associated measures and metrics as "
                 f"established at project inception?  Objective #{index} HAS BEEN MET.  "
                 f"Evidence: {EVIDENCE[index - 1]}  Sponsor Initials: ______")

    # 额外的两条（Part 1 里加了 #4/#5，这里也补上，保持两文件一致）
    tail = verdicts[2]
    for index in (4, 5):
        name, detail = OBJECTIVES[index - 1]
        heading = insert_after(tail, f"Project Objective #{index} - {name}: {detail}")
        verdict = insert_after(heading,
                               f"Did the student's project meet this objective with associated measures and "
                               f"metrics as established at project inception?  Objective #{index} HAS BEEN MET.  "
                               f"Evidence: {EVIDENCE[index - 1]}  Sponsor Initials: ______")
        tail = verdict

    note = find(doc, "PROJECT ACCEPTANCE Sponsor:")
    if note is not None:
        set_text(note,
                 "PROJECT ACCEPTANCE - Sponsor: Please show your evaluation of student's work, add comments, "
                 "and sign below. (Evaluation, acceptance option and signatures are left for the sponsor and "
                 "the student to complete.)")

    target = FINAL / f"07-Part2 SponsorsProjectAcceptanceDocument V3.3 - {STUDENT}.docx"
    doc.save(target)
    return target


def main() -> int:
    part1 = fill_part1()
    print(f"✅ {part1.relative_to(ROOT)}")
    part2 = fill_part2()
    print(f"✅ {part2.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
