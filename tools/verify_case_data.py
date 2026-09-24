# -*- coding: utf-8 -*-
"""用真实案例数据验收录入链路：docs/samples/检测结果案例.xlsx。

做两件事：
1. 把案例里的立柱 10 行、横梁 5 行数据结构化成"一个构件一条记录（多面）"；
2. 通过 Flask test client 走完整 HTTP 链路录入，再回查数据库，
   逐面比对 App 算出的最小值与案例 Excel 的"最小值"列。

用法（项目根目录）::

    python tools/verify_case_data.py

不需要启动服务器；使用临时数据库，不碰 defects.db。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import openpyxl                                               # noqa: E402
except ImportError:                                               # pragma: no cover
    raise SystemExit(
        "本工具需要 openpyxl，请先安装开发依赖：\n"
        "    python -m pip install -r requirements-dev.txt"
    )

from webapp import create_app                                     # noqa: E402

CASE_FILE = Path(__file__).resolve().parent.parent / "docs" / "samples" / "检测结果案例.xlsx"
COLUMN_SHEET = "幕墙立柱截面尺寸检测结果案例"
BEAM_SHEET = "幕墙横梁截面尺寸检测结果案例"


def read_case(sheet_name):
    """解析案例 sheet -> ``{(楼层, 构件位置, 面): {...}}``（保持出现顺序）。

    案例里"一个构件的多个检测面"用了**纵向合并单元格**（立柱 A4:A5 / B4:B5 / C4:C5），
    openpyxl 只在合并区左上角给值，因此对 楼层 / 构件位置 / 尺寸结果 向下填充。
    """
    sheet = openpyxl.load_workbook(CASE_FILE, data_only=True)[sheet_name]
    cases, order = {}, []
    last = {"floor": None, "position": None, "size": None}

    for row in sheet.iter_rows(values_only=True):
        floor, position, size, face = row[0], row[1], row[2], row[3]

        if floor not in (None, "", "/", "楼层"):
            last["floor"] = floor
        if position not in (None, "", "/", "检测构件位置"):
            last["position"] = position
        if size not in (None, "", "/", "尺寸检测结果 m×n (mm×mm)"):
            last["size"] = size

        # 跳过表头行与 "/" 占位行：数据里的面标签只有 B / H / t 这种短文本
        if not isinstance(face, str) or len(face) > 3 or face in ("/", "检测面", "面"):
            continue
        if last["floor"] in (None, "", "/") or last["position"] in (None, "", "/"):
            continue

        readings = [row[4 + index] for index in range(5)]
        if any(value is None for value in readings):
            continue

        key = (str(last["floor"]), str(last["position"]), face)
        cases[key] = {
            "size": str(last["size"]),
            "readings": readings,
            "expected_min": "%.2f" % float(row[9]),
        }
        order.append(key)

    return cases, order


def group_by_member(cases, order):
    """把"一面一行"合并成"一构件一记录"：{(楼层, 构件位置): [面, ...]}。"""
    grouped = {}
    for key in order:
        grouped.setdefault((key[0], key[1]), []).append(key)
    return grouped


def submit(client, project_id, template_type, cases, order):
    """按构件逐个提交（一次提交 = 一条记录 + 它的多个检测面）。"""
    grouped = group_by_member(cases, order)
    for (floor, position), keys in grouped.items():
        payload = {
            "floor": floor,
            "member_position": position,
            "size_result": cases[keys[0]]["size"],
            "requirement_index": "0",
        }
        for index, key in enumerate(keys):
            payload["face_%d" % index] = key[2]
            for position_in_face, value in enumerate(cases[key]["readings"], start=1):
                payload["value_%d_%d" % (index, position_in_face)] = str(value)

        response = client.post(
            "/projects/%d/records/?template=%s" % (project_id, template_type), data=payload
        )
        if response.status_code not in (200, 302):
            raise SystemExit("提交失败：%s %s -> HTTP %s" % (floor, position, response.status_code))
    return grouped


def main() -> int:
    if not CASE_FILE.exists():
        raise SystemExit("找不到案例文件：%s" % CASE_FILE)

    failures = []

    def check(name, ok, detail=""):
        print(("  PASS  " if ok else "  FAIL  ") + name + ("  | " + detail if detail else ""))
        if not ok:
            failures.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        app = create_app({
            "TESTING": True,
            "DB_PATH": str(Path(tmp) / "verify.db"),
            "REPORTS_DIR": str(Path(tmp) / "reports"),
            "UPLOADS_DIR": str(Path(tmp) / "uploads"),
        })
        client = app.test_client()

        client.post("/projects/", data={
            "project_no": "JCZG", "house_name": "金骐智谷",
            "house_address": "深圳市南山区", "client_org": "中冶", "test_date": "2026-09-03",
        })

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
            from webapp import db
            from webapp.services import measurements

            groups = measurements.grouped_by_template(1)
            counts = {group["template_type"]: group["count"] for group in groups}
            check("落库分类计数 立柱 5 / 横梁 5",
                  counts == {"column": 5, "beam": 5}, str(counts))

            stored = {}
            for group in groups:
                for item in group["records"]:
                    record = item["record"]
                    for face in item["faces"]:
                        stored[(record["floor"], record["member_position"], face["face"])] = face

            check("落库检测面数 = 15", len(stored) == 15, "%d 个" % len(stored))

            mismatches = []
            for cases in (column_cases, beam_cases):
                for key, case in cases.items():
                    face = stored.get(key)
                    if face is None:
                        mismatches.append("%s 未落库" % (key,))
                    elif face["min_text"] != case["expected_min"]:
                        mismatches.append("%s App=%s 案例=%s"
                                          % (key, face["min_text"], case["expected_min"]))
            check("15 个检测面的最小值与案例完全一致", not mismatches,
                  "；".join(mismatches) if mismatches else "全部一致")

            # 四列纵向合并的前置条件：立柱每个构件确实有 2 个面
            multi = [item for group in groups if group["template_type"] == "column"
                     for item in group["records"] if len(item["faces"]) == 2]
            check("立柱 5 条记录各含 2 个检测面（M2 纵向合并的依据）", len(multi) == 5,
                  "%d 条" % len(multi))

            # 尺寸结果已规范化为 ×
            sizes = {row["size_result"] for row in
                     db.query_all("SELECT size_result FROM measurement_records")}
            check("尺寸结果规范化为 ×", sizes == {"63×164", "82×76"}, str(sorted(sizes)))

        detail = client.get("/projects/1").get_data(as_text=True)
        check("详情页显示 立柱 5 条 · 横梁 5 条", "立柱 5 条 · 横梁 5 条" in detail)
        for expected in ("2.10", "2.52", "2.99"):
            check("详情页展示最小值 %s" % expected, expected in detail)

    print()
    print("结论：%s" % ("全部通过" if not failures else "存在失败：" + "、".join(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
