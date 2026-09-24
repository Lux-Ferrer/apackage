# -*- coding: utf-8 -*-
"""检测记录（立柱 / 横梁）读写服务。

三层职责：

1. **表单解析与校验** —— :func:`parse_record_form` 是纯函数（不碰请求上下文），便于单测；
2. **事务化写入** —— 记录与其检测面读数始终在**同一个事务**内提交或回滚，
   任一步失败（含 ``UNIQUE(record_id, face)`` 冲突）都不留半条数据；
3. **分组读取** —— 一次查记录、一次查读数，在 Python 里分组，避免 N+1。

最小值不落库：读取时由 :mod:`webapp.services.thickness` 现算。
"""

from __future__ import annotations

import re

from .. import config, db
from . import thickness

# 尺寸结果里可能出现的乘号写法，统一成全角 ×
_SIZE_SEPARATORS = ("x", "X", "*", "＊")
_SIZE_MULTIPLY = "×"
# 「两个数字 + 空白」这种没有运算符的写法（现场/表格里常见）→ 空白应当视作乘号，
# 而不是被当作普通空格删掉（否则 "63 164" 会被粘成 "63164"）。
_TWO_NUMBERS = re.compile(r"^(\d+(?:\.\d+)?)[\s\u3000]+(\d+(?:\.\d+)?)$")


def _clean(value):
    """转成去空白的字符串；None 得到空串。"""
    return "" if value is None else str(value).strip()


# --------------------------------------------------------------------------
# 解析与校验
# --------------------------------------------------------------------------
def normalize_size_result(raw):
    """规范化尺寸结果。

    - 把 ``x`` / ``X`` / ``*`` / ``＊`` 统一成 ``×``（如 ``63x164`` -> ``63×164``）；
    - **两个数字之间只有空白**时，把空白视作乘号（``63 164`` -> ``63×164``）；
    - 其余空白去掉，因此 ``12 + 75`` 保留为 ``12+75``（需求报告里的写法）。
    """
    text = _clean(raw)
    if not text:
        return None

    for separator in _SIZE_SEPARATORS:
        text = text.replace(separator, _SIZE_MULTIPLY)

    pairs = _TWO_NUMBERS.match(text)
    if pairs:
        return "%s%s%s" % (pairs.group(1), _SIZE_MULTIPLY, pairs.group(2))

    return text.replace(" ", "").replace("\u3000", "") or None


def resolve_requirement(index_raw, template_type):
    """把下拉序号解析成条文文案（存快照）；空或越界返回 None（导出时显示"无"）。"""
    options = config.REQUIREMENT_OPTIONS.get(template_type, ())
    text = _clean(index_raw)
    if not text:
        return None
    try:
        index = int(text)
    except ValueError:
        return None
    if 0 <= index < len(options):
        return options[index]
    return None


def requirement_index_of(requirement_text, template_type):
    """反向匹配：编辑时用已存文案找回下拉选中项；匹配不到返回 None。"""
    options = config.REQUIREMENT_OPTIONS.get(template_type, ())
    if requirement_text in options:
        return options.index(requirement_text)
    return None


# 条文文案的标点归一化表（全角 → 半角）
_CLAUSE_PUNCTUATION = {"，": ",", "。": ".", "；": ";", "：": ":", "（": "(", "）": ")"}


def normalize_clause(text):
    """条文文案归一化：去空白、全角标点转半角、去首尾标点。

    用途是**比较与追溯**（配置文案 vs 需求报告 / 对拍时的原始差异判定），
    不参与存储——库里存的始终是用户选中的原文快照。
    """
    if text is None:
        return ""
    cleaned = re.sub(r"\s+", "", str(text))
    for full, half in _CLAUSE_PUNCTUATION.items():
        cleaned = cleaned.replace(full, half)
    return cleaned.strip(".;,、")


def parse_record_form(form, template_type):
    """解析检测记录表单，返回 ``(data, errors)``。

    ``errors`` 的键与表单字段名一一对应（``floor`` / ``face_0`` / ``value_0_1`` …），
    便于模板就地报错。``data`` 结构::

        {"floor": ..., "member_position": ..., "size_result": ...,
         "requirement_text": ..., "faces": [{"face": "B", "values": [2.99, ...]}, ...]}
    """
    if template_type not in config.TEMPLATE_TYPES:
        raise ValueError("未知模板类型：%r" % (template_type,))

    errors = {}
    floor = _clean(form.get("floor"))
    member_position = _clean(form.get("member_position"))
    if not floor:
        errors["floor"] = "楼层不能为空"
    if not member_position:
        errors["member_position"] = "构件位置不能为空"

    faces, face_errors = _parse_faces(form)
    errors.update(face_errors)
    if not faces and not face_errors:
        errors["faces"] = "至少填写 1 个检测面（面标签 + 5 个厚度读数）"

    data = {
        "floor": floor,
        "member_position": member_position,
        "size_result": normalize_size_result(form.get("size_result")),
        "requirement_text": resolve_requirement(form.get("requirement_index"), template_type),
        "faces": faces,
    }
    return data, errors


def _parse_faces(form):
    """按固定下标探测检测面行（不信任前端提交的行数），返回 ``(faces, errors)``。"""
    faces = []
    errors = {}
    seen = set()

    for index in range(config.FACE_MAX_COUNT):
        raw_face = _clean(form.get("face_%d" % index))
        raw_values = [
            form.get("value_%d_%d" % (index, position))
            for position in range(1, config.THICKNESS_VALUE_COUNT + 1)
        ]
        has_reading = any(_clean(value) for value in raw_values)

        if not raw_face and not has_reading:
            continue                                    # 整行空白：加了一行没填，直接跳过

        if not raw_face:
            errors["face_%d" % index] = "这一行填了厚度读数，请同时填写检测面"
            continue
        if raw_face in seen:
            errors["face_%d" % index] = "检测面「%s」在本记录中重复" % raw_face
            continue
        seen.add(raw_face)

        values = []
        for position, raw in enumerate(raw_values, start=1):
            try:
                values.append(thickness.normalize_value(raw))
            except ValueError:
                errors["value_%d_%d" % (index, position)] = "厚度读数必须是数字"
                values.append(None)

        faces.append({"face": raw_face, "values": values})

    return faces, errors


# --------------------------------------------------------------------------
# 写入（事务化）
# --------------------------------------------------------------------------
def create_record(project_id, template_type, data):
    """新增一条检测记录及其检测面读数，返回新记录 id。

    ``INSERT 记录`` 与 ``INSERT 读数`` 在同一事务内；读数写入失败则记录一并回滚。
    """
    if template_type not in config.TEMPLATE_TYPES:
        raise ValueError("未知模板类型：%r" % (template_type,))

    with db.transaction() as conn:
        next_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order"
            " FROM measurement_records WHERE project_id = ?",
            (project_id,),
        ).fetchone()["next_order"]

        cursor = conn.execute(
            """
            INSERT INTO measurement_records
                (project_id, template_type, floor, member_position,
                 size_result, requirement_text, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, template_type, data["floor"], data["member_position"],
             data["size_result"], data["requirement_text"], next_order),
        )
        record_id = cursor.lastrowid
        _insert_readings(conn, record_id, data["faces"])

    return record_id


def update_record(record_id, data):
    """更新记录：构件字段 + 整体替换检测面读数（同一事务）。

    **``template_type`` 刻意不在 UPDATE 字段清单内** —— 这是"编辑时模板类型不可切换"
    在数据层的保证：即使伪造 POST 也无法改动。
    """
    with db.transaction() as conn:
        cursor = conn.execute(
            """
            UPDATE measurement_records
               SET floor = ?, member_position = ?, size_result = ?,
                   requirement_text = ?,
                   updated_at = datetime('now','localtime')
             WHERE id = ?
            """,
            (data["floor"], data["member_position"], data["size_result"],
             data["requirement_text"], record_id),
        )
        if cursor.rowcount == 0:
            raise LookupError("检测记录不存在：#%s" % record_id)

        conn.execute("DELETE FROM thickness_readings WHERE record_id = ?", (record_id,))
        _insert_readings(conn, record_id, data["faces"])


def delete_record(record_id):
    """删除记录；检测面读数由外键 ``ON DELETE CASCADE`` 一并删除（同一事务）。"""
    with db.transaction() as conn:
        cursor = conn.execute("DELETE FROM measurement_records WHERE id = ?", (record_id,))
        if cursor.rowcount == 0:
            raise LookupError("检测记录不存在：#%s" % record_id)


def _insert_readings(conn, record_id, faces):
    """写入检测面读数；面重复会触发 UNIQUE 约束，由外层事务整体回滚。"""
    for face in faces:
        values = list(face["values"])
        values = (values + [None] * config.THICKNESS_VALUE_COUNT)[:config.THICKNESS_VALUE_COUNT]
        conn.execute(
            """
            INSERT INTO thickness_readings
                (record_id, face, value_1, value_2, value_3, value_4, value_5)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (record_id, face["face"], *values),
        )


# --------------------------------------------------------------------------
# 读取
# --------------------------------------------------------------------------
def get_record(record_id):
    return db.query_one("SELECT * FROM measurement_records WHERE id = ?", (record_id,))


def get_readings(record_id):
    return db.query_all(
        "SELECT * FROM thickness_readings WHERE record_id = ? ORDER BY id", (record_id,)
    )


def list_records_with_faces(project_id):
    """取项目下全部记录（含检测面明细）：两条查询 + Python 分组，避免 N+1。"""
    records = db.query_all(
        "SELECT * FROM measurement_records WHERE project_id = ? ORDER BY sort_order, id",
        (project_id,),
    )
    if not records:
        return []

    placeholders = ",".join("?" * len(records))
    readings = db.query_all(
        "SELECT * FROM thickness_readings WHERE record_id IN (%s) ORDER BY record_id, id"
        % placeholders,
        [row["id"] for row in records],
    )

    by_record = {}
    for row in readings:
        by_record.setdefault(row["record_id"], []).append(_face_view(row))

    return [{"record": row, "faces": by_record.get(row["id"], [])} for row in records]


def grouped_by_template(project_id):
    """按模板分组（顺序取自 config.TEMPLATE_TYPES，立柱在前），供项目详情页渲染。"""
    items = list_records_with_faces(project_id)
    groups = []
    for template_type in config.TEMPLATE_TYPES:
        records = [item for item in items if item["record"]["template_type"] == template_type]
        groups.append({
            "template_type": template_type,
            "name": config.TEMPLATE_NAMES[template_type],
            "short_name": config.TEMPLATE_SHORT_NAMES[template_type],
            "title": config.TEMPLATE_TITLES[template_type],
            "requirement_label": config.REQUIREMENT_LABELS[template_type],
            "records": records,
            "count": len(records),
        })
    return groups


def count_by_template(project_id):
    """项目下立柱/横梁记录数，如 ``{'column': 3, 'beam': 2}``。"""
    counts = {template_type: 0 for template_type in config.TEMPLATE_TYPES}
    for row in db.query_all(
        "SELECT template_type, COUNT(*) AS total FROM measurement_records"
        " WHERE project_id = ? GROUP BY template_type",
        (project_id,),
    ):
        if row["template_type"] in counts:
            counts[row["template_type"]] = row["total"]
    return counts


def describe_counts(counts):
    """把计数转成紧凑文案：``立柱 3 条 · 横梁 2 条``。"""
    return " · ".join(
        "%s %d 条" % (config.TEMPLATE_SHORT_NAMES[t], counts.get(t, 0))
        for t in config.TEMPLATE_TYPES
    )


def face_labels(item):
    """记录的检测面标签串，如 ``B/H``。"""
    return "/".join(face["face"] for face in item["faces"])


def _face_view(row):
    """把一行 thickness_readings 转成模板友好的视图（含现算的最小值文本）。

    注意：键名用 ``readings`` 而不是 ``values`` —— 在 Jinja 里 ``foo.values`` 会先命中
    dict 自带的 ``values()`` 方法，导致取值静默变成空。
    """
    readings = thickness.readings_of_row(row)
    return {
        "face": row["face"],
        "readings": readings,
        "readings_text": [thickness.format_mm(value) for value in readings],
        "min_text": thickness.format_mm(thickness.face_min(readings)),
        "row": row,
    }
