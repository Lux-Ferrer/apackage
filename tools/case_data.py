# -*- coding: utf-8 -*-
"""案例数据（docs/samples/检测结果案例.xlsx）的解析与提交，供多个工具复用。

注意：该 xlsx 是从两张 jpg **OCR 转录**而来 —— 数值与"多行数据结构"可靠，
但标点/空格/句号可能有失真。因此：

- **结构与数值**以本文件解析结果为准；
- **条文文字**以需求报告（``docs/requirements/幕墙检测APP需求报告.docx``）为准；
- **表格版式**以真实报告裁剪基准 ``tests/fixtures/检测表_真实裁剪.docx`` 为准
  （数值见 ``webapp/resources/report_layout.json``）；
- **字体/主题**以 ``tests/fixtures/金骐智谷_金骐_检测报告.docx`` 为准（本次不改字体）。
"""

from __future__ import annotations

from pathlib import Path

try:
    import openpyxl
except ImportError:                                        # pragma: no cover
    raise SystemExit(
        "本工具需要 openpyxl，请先安装开发依赖：\n"
        "    python -m pip install -r requirements-dev.txt"
    )

CASE_FILE = Path(__file__).resolve().parent.parent / "docs" / "samples" / "检测结果案例.xlsx"
COLUMN_SHEET = "幕墙立柱截面尺寸检测结果案例"
BEAM_SHEET = "幕墙横梁截面尺寸检测结果案例"

TEMPLATE_SHEETS = {"column": COLUMN_SHEET, "beam": BEAM_SHEET}


def read_case(sheet_name):
    """解析案例 sheet -> ``{(楼层, 构件位置, 面): {...}}``（保持出现顺序）。

    案例里有两类**纵向合并单元格**，openpyxl 只在合并区左上角给值，需要向下填充：

    - 楼层 / 构件位置 / 尺寸结果（立柱 A4:A5 / B4:B5 / C4:C5）——表示"同一构件的多个面"；
    - 截面尺寸要求（立柱 K4:K13、横梁 K4:K8）——表示"整表共用同一条条文"。
    """
    sheet = openpyxl.load_workbook(CASE_FILE, data_only=True)[sheet_name]
    cases, order = {}, []
    last = {"floor": None, "position": None, "size": None, "requirement": None}

    for row in sheet.iter_rows(values_only=True):
        floor, position, size, face = row[0], row[1], row[2], row[3]

        if floor not in (None, "", "/", "楼层"):
            last["floor"] = floor
        if position not in (None, "", "/", "检测构件位置"):
            last["position"] = position
        if size not in (None, "", "/", "尺寸检测结果 m×n (mm×mm)"):
            last["size"] = size
        if row[10] not in (None, ""):
            last["requirement"] = row[10]

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
            "requirement": last["requirement"],
        }
        order.append(key)

    return cases, order


def requirement_index_for(clause, template_type):
    """按条文内容在预置项里找出下标（归一化比较）。

    案例 xlsx 是 OCR 转录，标点/空格可能失真，所以不能直接字符串相等；
    匹配不到时返回空串（报告里显示"无"），让内容对拍如实报出差异。
    """
    from webapp import config
    from webapp.services.measurements import normalize_clause

    if not clause:
        return ""
    target = normalize_clause(clause)
    for index, option in enumerate(config.REQUIREMENT_OPTIONS[template_type]):
        if normalize_clause(option) == target:
            return str(index)
    return ""


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
            "requirement_index": requirement_index_for(cases[keys[0]]["requirement"], template_type),
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


def expected_rows(cases, order):
    """把案例数据摊平成"一行一个检测面"的期望文本行（与 Word 表格的数据行一一对应）。

    多面构件：首个面带 楼层/构件位置/尺寸结果，后续面的这三列为空
    （对应 Word 里的纵向合并 continue 格）。

    「截面尺寸要求」列的合并粒度不同：按**连续相同的条文**合并（不是按构件），
    所以只有"本行条文与上一行不同"时才带文本 —— 同一条文横跨多个构件时，
    第 2 个构件的首行同样是 continue 空格式。
    """
    rows = []
    previous_requirement = None
    for (floor, position), keys in group_by_member(cases, order).items():
        for index, key in enumerate(keys):
            first = index == 0
            case = cases[key]
            requirement = str(case["requirement"] or "")
            clause_here = requirement if requirement != previous_requirement else ""
            previous_requirement = requirement
            rows.append([
                floor if first else "",
                position if first else "",
                case["size"] if first else "",
                key[2],
                *["%.2f" % float(value) for value in case["readings"]],
                case["expected_min"],
                clause_here,
            ])
    return rows
