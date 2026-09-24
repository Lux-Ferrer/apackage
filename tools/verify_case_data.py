# -*- coding: utf-8 -*-
"""用真实案例数据验收 M1 录入链路与 M2 导出内容（O2 内容对拍）。

两段：
1. **录入**：把 ``docs/samples/检测结果案例.xlsx`` 的立柱 10 行、横梁 5 行
   通过 Flask test client 走完整 HTTP 链路录入，回查数据库逐面比对最小值；
2. **导出**：调用项目级导出，把生成文档的表格内容与案例数据**逐格比对**
   （楼层/构件位置/尺寸结果/检测面/5 个读数/最小值/条文）。

条文列做**归一化比较**（去空白、统一全/半角标点）：案例 xlsx 是 OCR 转录，
标点可能失真；原始差异记为 WARN 而不是失败。

用法（项目根目录，不需要启动服务器）::

    python tools/verify_case_data.py
"""

from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lxml import etree                                          # noqa: E402

from case_data import (BEAM_SHEET, CASE_FILE, COLUMN_SHEET,     # noqa: E402
                       expected_rows, read_case, submit)
from webapp import create_app                                   # noqa: E402
from webapp.services import measurements                        # noqa: E402
from webapp.services.measurements import normalize_clause       # noqa: E402

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

PROJECT = {
    "project_no": "JCZG",
    "house_name": "金骐智谷",
    "house_address": "深圳市南山区",
    "client_org": "中冶",
    "test_date": "2026-09-03",
}

failures: list = []
warnings: list = []


def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("  | " + detail if detail else ""))
    if not ok:
        failures.append(name)


def warn(name, detail):
    item = "%s：%s" % (name, detail)
    if item in warnings:                        # 同一差异只提示一次
        return
    print("  WARN  " + item)
    warnings.append(item)


def export_tables(client, project_id, workdir):
    """导出报告并解析出各表的"一行一个检测面"文本网格。"""
    response = client.get("/projects/%d/export" % project_id)
    if response.status_code != 200:
        raise SystemExit("导出失败：HTTP %s" % response.status_code)

    path = Path(workdir) / "export.docx"
    path.write_bytes(response.data)
    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))

    tables = []
    for tbl in root.find(W + "body").findall(W + "tbl"):
        rows = []
        for tr in tbl.findall(W + "tr"):
            rows.append(["".join(node.text or "" for node in tc.iter(W + "t"))
                         for tc in tr.findall(W + "tc")])
        tables.append(rows)
    return tables


def main() -> int:
    if not CASE_FILE.exists():
        raise SystemExit("找不到案例文件：%s" % CASE_FILE)

    with tempfile.TemporaryDirectory() as tmp:
        app = create_app({
            "TESTING": True,
            "DB_PATH": str(Path(tmp) / "verify.db"),
            "REPORTS_DIR": str(Path(tmp) / "reports"),
            "UPLOADS_DIR": str(Path(tmp) / "uploads"),
        })
        client = app.test_client()
        client.post("/projects/", data=PROJECT)

        column_cases, column_order = read_case(COLUMN_SHEET)
        beam_cases, beam_order = read_case(BEAM_SHEET)
        check("解析案例数据（立柱 10 面 / 横梁 5 面）",
              len(column_order) == 10 and len(beam_order) == 5,
              "立柱 %d 面，横梁 %d 面" % (len(column_order), len(beam_order)))

        column_groups = submit(client, 1, "column", column_cases, column_order)
        beam_groups = submit(client, 1, "beam", beam_cases, beam_order)
        check("按构件提交（立柱 5 条 / 横梁 5 条）",
              len(column_groups) == 5 and len(beam_groups) == 5,
              "立柱 %d 条，横梁 %d 条" % (len(column_groups), len(beam_groups)))

        with app.app_context():
            groups = measurements.grouped_by_template(1)
            counts = {group["template_type"]: group["count"] for group in groups}
            check("落库分类计数 立柱 5 / 横梁 5", counts == {"column": 5, "beam": 5}, str(counts))

            stored = {}
            for group in groups:
                for item in group["records"]:
                    record = item["record"]
                    for face in item["faces"]:
                        stored[(record["floor"], record["member_position"], face["face"])] = face
            check("落库检测面数 = 15", len(stored) == 15, "%d 个" % len(stored))

            mismatches = [
                "%s App=%s 案例=%s" % (key, stored[key]["min_text"], case["expected_min"])
                for cases in (column_cases, beam_cases)
                for key, case in cases.items()
                if key not in stored or stored[key]["min_text"] != case["expected_min"]
            ]
            check("15 个检测面的最小值与案例一致", not mismatches,
                  "；".join(mismatches) if mismatches else "全部一致")

            multi = [item for group in groups if group["template_type"] == "column"
                     for item in group["records"] if len(item["faces"]) == 2]
            check("立柱 5 条记录各含 2 个检测面（纵向合并的依据）", len(multi) == 5,
                  "%d 条" % len(multi))

        detail = client.get("/projects/1").get_data(as_text=True)
        check("详情页显示 立柱 5 条 · 横梁 5 条", "立柱 5 条 · 横梁 5 条" in detail)

        # ---- O2：导出内容与案例逐格比对 ----
        tables = export_tables(client, 1, tmp)
        check("导出文档含两张表（立柱 + 横梁，不含玻璃）", len(tables) == 2, "%d 张" % len(tables))

        for table_index, (template_type, sheet_cases) in enumerate(
                (("column", (column_cases, column_order)), ("beam", (beam_cases, beam_order)))):
            cases, order = sheet_cases
            expected = expected_rows(cases, order)
            actual = tables[table_index][2:]              # 跳过 2 行表头

            if len(expected) != len(actual):
                check("%s 表数据行数" % template_type, False,
                      "期望 %d 行，实际 %d 行" % (len(expected), len(actual)))
                continue

            data_failures = []
            for row_index, (want_row, got_row) in enumerate(zip(expected, actual)):
                for column, (want, got) in enumerate(zip(want_row, got_row)):
                    if column == 10:                       # 条文列：归一化比较
                        if normalize_clause(want) != normalize_clause(got):
                            data_failures.append("r%d 条文：案例=%r 报告=%r" % (row_index, want, got))
                        elif want != got:
                            warn("条文列原始文本差异（已归一化通过）",
                                 "案例=%r 报告=%r" % (want, got))
                    elif want != got:
                        data_failures.append("r%d c%d：案例=%r 报告=%r" % (row_index, column, want, got))

            check("%s 表内容与案例逐格一致（%d 行 × 11 列）"
                  % ({"column": "立柱", "beam": "横梁"}[template_type], len(expected)),
                  not data_failures,
                  "；".join(data_failures[:5]) if data_failures else "全部一致")

    print()
    if warnings:
        print("WARN %d 条（不判失败，供人工确认）：" % len(warnings))
        for item in warnings:
            print("  - %s" % item)
    print("结论：%s" % ("全部通过" if not failures else "存在失败：" + "、".join(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
