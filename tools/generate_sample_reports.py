# -*- coding: utf-8 -*-
"""生成 5 份样例报告 —— 章程 Objective 3 的可提交证据。

章程原文的度量是：

    "Five sample reports generated from test data match the client's template
     in structure and formatting by December 1, 2026"

做法：用 ``docs/samples/检测结果案例.xlsx`` 的真实检测数据造 5 个项目
（项目编号 / 房屋名称 / 地点 / 委托单位 / 检测日期 各不相同，检测数据相同），
逐个走**真实的导出链路**（Flask 路由），把生成的 .docx 落到
``deliverables/samples/``，并写一份清单。

结构一致性由 ``tools/compare_report_with_sample.py`` 单独验证并产出
``deliverables/fidelity-report.md``。

用法（项目根目录，不需要启动服务器）::

    python tools/generate_sample_reports.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from case_data import BEAM_SHEET, COLUMN_SHEET, read_case, submit   # noqa: E402
from webapp import config                                           # noqa: E402
from webapp import create_app                                       # noqa: E402

# 5 个样例项目：检测数据相同（来自案例），项目信息各不相同
SAMPLE_PROJECTS = [
    {"project_no": "JCZG", "house_name": "金骐智谷", "house_address": "深圳市南山区",
     "client_org": "中冶", "test_date": "2026-09-03"},
    {"project_no": "JC2Q", "house_name": "金骐智谷二期", "house_address": "深圳市南山区",
     "client_org": "中冶", "test_date": "2026-09-10"},
    {"project_no": "HXDS", "house_name": "华兴大厦", "house_address": "广州市天河区",
     "client_org": "华兴地产", "test_date": "2026-09-18"},
    {"project_no": "ZJGC", "house_name": "中建广场", "house_address": "珠海市香洲区",
     "client_org": "中建三局", "test_date": "2026-10-08"},
    {"project_no": "BLYY", "house_name": "宝利医院", "house_address": "东莞市南城区",
     "client_org": "宝利集团", "test_date": "2026-10-15"},
]


def filename_from_response(response) -> str:
    """从 Content-Disposition 里取真实文件名。

    非 ASCII 文件名时 Werkzeug 会同时给两个参数：``filename=`` 是**去掉非 ASCII 的
    回退名**（中文会变成 `JCZG__.docx`），``filename*=UTF-8''...`` 才是真名。
    所以必须优先取 ``filename*``。
    """
    disposition = response.headers.get("Content-Disposition", "")
    fallback = None
    for part in disposition.split(";")[1:]:
        part = part.strip()
        if part.startswith("filename*="):
            _, _, encoded = part[len("filename*="):].strip('"').partition("''")
            return unquote(encoded)
        if part.startswith("filename="):
            fallback = part[len("filename="):].strip('"')
    if fallback:
        return fallback
    raise SystemExit("无法从响应头解析文件名：%s" % disposition)


def main() -> int:
    out_dir = config.DELIVERABLES_DIR / "samples"
    out_dir.mkdir(parents=True, exist_ok=True)

    column_cases, column_order = read_case(COLUMN_SHEET)
    beam_cases, beam_order = read_case(BEAM_SHEET)

    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app({
            "TESTING": True,
            "DB_PATH": str(Path(tmp) / "samples.db"),
            "REPORTS_DIR": str(Path(tmp) / "reports"),
            "UPLOADS_DIR": str(Path(tmp) / "uploads"),
        })
        client = app.test_client()

        for project in SAMPLE_PROJECTS:
            client.post("/projects/", data=project)
            project_id = None
            with app.app_context():
                from webapp import db
                project_id = db.query_one(
                    "SELECT id FROM projects WHERE project_no = ?", (project["project_no"],)
                )["id"]

            submit(client, project_id, "column", column_cases, column_order)
            submit(client, project_id, "beam", beam_cases, beam_order)

            response = client.get("/projects/%d/export" % project_id)
            if response.status_code != 200:
                raise SystemExit("导出失败：%s -> HTTP %s"
                                 % (project["project_no"], response.status_code))

            data = response.data
            name = filename_from_response(response)
            response.close()                     # 释放文件句柄，否则临时目录清理会失败
            (out_dir / name).write_bytes(data)
            print("  生成 %s（%d 字节）" % (name, len(data)))
            rows.append((name, project, len(column_order), len(beam_order)))

    # 清单
    lines = [
        "# 样例报告（5 份）",
        "",
        "由 `tools/generate_sample_reports.py` 生成；检测数据来自 `docs/samples/检测结果案例.xlsx`，",
        "项目信息为构造值。用于章程 Objective 3 的度量：",
        "",
        "> Five sample reports generated from test data match the client's template in structure and formatting.",
        "",
        "## 清单",
        "",
        "| 文件 | 项目编号 | 房屋名称 | 检测日期 | 立柱检测面 | 横梁检测面 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, project, column_faces, beam_faces in rows:
        lines.append("| `%s` | %s | %s | %s | %d | %d |"
                     % (name, project["project_no"], project["house_name"],
                        project["test_date"], column_faces, beam_faces))
    lines += [
        "",
        "## 每份报告的预期结构",
        "",
        "- 项目信息段 5 行（项目编号 / 房屋名称 / 房屋地点 / 委托单位 / 检测日期）",
        "- 「幕墙立柱截面尺寸检测结果」标题 + 表格（5 条记录、10 个检测面；B/H 两面纵向合并四列）",
        "- 「幕墙横梁截面尺寸检测结果」标题 + 表格（5 条记录、5 个检测面；单面不合并）",
        "- 固定备注：`备注：检测构件位置详见检测工作内容附件 18。`",
        "- **不含玻璃模块**（范围外）",
        "",
        "## 结构一致性验证",
        "",
        "见 `deliverables/fidelity-report.md`（由 `tools/compare_report_with_sample.py` 生成）：",
        "从样例回灌其自身数据后重新生成并逐属性比较，覆盖表格/行/单元格全部版式属性与合并网格。",
    ]
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("清单已写入 %s" % (out_dir / "README.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
