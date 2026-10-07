/* 检测记录读写：表单解析、事务化增删改、分组读取。
 *
 * 与 `webapp/services/measurements.py` 对应。最关键的两条：
 *
 * 1. **记录 + 读数必须同一事务**（M1 就定下的语义）：读数写失败 → 记录一并回滚；
 * 2. **`template_type` 不可变**：更新的字段清单里不含它（编辑锁定，三层保证之一）。
 */

import { CONFIG } from '../config.js';
import { LookupError, STORE } from '../db.js';
import { normalizeSizeResult, resolveRequirement, clean } from '../clauses.js';
import { faceMinTextOfValid, normalizeValue, readingsOfRow, formatMm } from '../thickness.js';

/* --------------------------------------------------------------------------
 * 解析与校验
 * ------------------------------------------------------------------------ */

/**
 * 解析检测记录表单，返回 `{data, errors}`。
 *
 * `errors` 的键与表单字段名一一对应（`floor` / `face_0` / `value_0_1` …）；
 * `data.faces` 形如 `[{face: 'B', values: [2.99, …]}]`。
 */
export function parseRecordForm(form, templateType) {
    if (!CONFIG.TEMPLATE_TYPES.includes(templateType)) {
        throw new Error(`未知模板类型：${templateType}`);
    }

    const errors = {};
    const floor = clean(read(form, 'floor'));
    const memberPosition = clean(read(form, 'member_position'));
    if (!floor) errors.floor = '楼层不能为空';
    if (!memberPosition) errors.member_position = '构件位置不能为空';

    const { faces, errors: faceErrors } = parseFaces(form);
    Object.assign(errors, faceErrors);
    if (!faces.length && !Object.keys(faceErrors).length) {
        errors.faces = `至少填写 1 个检测面（面标签 + ${CONFIG.THICKNESS_VALUE_COUNT} 个厚度读数）`;
    }

    const data = {
        floor,
        member_position: memberPosition,
        size_result: normalizeSizeResult(read(form, 'size_result')),
        requirement_text: resolveRequirement(read(form, 'requirement_index'), templateType),
        faces,
    };
    return { data, errors };
}

function read(form, key) {
    if (!form) return undefined;
    if (typeof form.get === 'function') return form.get(key);
    return form[key];
}

/**
 * 按**固定下标**探测检测面行（不信任前端提交的行数）。
 *
 * 超过 `FACE_MAX_COUNT` 的行被忽略 —— 与 Python 一致（服务端只认 0..max-1）。
 */
export function parseFaces(form) {
    const faces = [];
    const errors = {};
    const seen = new Set();

    for (let index = 0; index < CONFIG.FACE_MAX_COUNT; index += 1) {
        const rawFace = clean(read(form, `face_${index}`));
        const rawValues = [];
        for (let position = 1; position <= CONFIG.THICKNESS_VALUE_COUNT; position += 1) {
            rawValues.push(read(form, `value_${index}_${position}`));
        }
        const hasReading = rawValues.some((value) => clean(value));

        if (!rawFace && !hasReading) continue;          // 整行空白：加了一行没填，跳过

        if (!rawFace) {
            errors[`face_${index}`] = '这一行填了厚度读数，请同时填写检测面';
            continue;
        }
        if (seen.has(rawFace)) {
            errors[`face_${index}`] = `检测面「${rawFace}」在本记录中重复`;
            continue;
        }
        seen.add(rawFace);

        const values = [];
        rawValues.forEach((raw, offset) => {
            try {
                values.push(normalizeValue(raw));
            } catch {
                errors[`value_${index}_${offset + 1}`] = '厚度读数必须是数字';
                values.push(null);
            }
        });

        faces.push({ face: rawFace, values });
    }
    return { faces, errors };
}

/* --------------------------------------------------------------------------
 * 写入（事务化）
 * ------------------------------------------------------------------------ */

/**
 * 新增一条检测记录及其检测面读数，返回新记录 id。
 *
 * ``INSERT 记录`` 与 ``INSERT 读数`` 在同一事务内；读数写入失败则记录一并回滚。
 */
export async function createRecord(db, projectId, templateType, data) {
    if (!CONFIG.TEMPLATE_TYPES.includes(templateType)) {
        throw new Error(`未知模板类型：${templateType}`);
    }
    const now = new Date();
    return db.write([STORE.records, STORE.readings], async (ctx) => {
        const existing = await ctx.allByIndex(
            ctx.index(STORE.records, 'project_id'), Number(projectId));
        const nextOrder = existing.reduce(
            (max, record) => Math.max(max, record.sort_order ?? -1), -1) + 1;

        const recordId = await ctx.insert(STORE.records, {
            project_id: Number(projectId),
            template_type: templateType,
            floor: data.floor,
            member_position: data.member_position,
            size_result: data.size_result,
            requirement_text: data.requirement_text,
            sort_order: nextOrder,
            created_at: stamp(now),
            updated_at: stamp(now),
        });

        await insertReadings(ctx, recordId, data.faces);
        return recordId;
    });
}

async function insertReadings(ctx, recordId, faces) {
    for (const face of faces) {
        const row = { record_id: recordId, face: face.face };
        face.values.forEach((value, offset) => {
            row[`value_${offset + 1}`] = value;
        });
        // 复合唯一索引 [record_id, face] 冲突 → ConstraintError，事务整体回滚
        await ctx.insert(STORE.readings, row);
    }
}

/**
 * 更新记录：读数**整体替换**；`template_type` 不在更新字段里（编辑锁定）。
 * 记录不存在 → LookupError。
 */
export async function updateRecord(db, recordId, data) {
    const key = Number(recordId);
    return db.write([STORE.records, STORE.readings], async (ctx) => {
        const current = await ctx.get(STORE.records, key);
        if (!current) throw new LookupError(`检测记录不存在：#${recordId}`);

        // 先删旧读数再写新的：同一事务，失败则旧数据原样保留
        await ctx.deleteByIndex(ctx.index(STORE.readings, 'record_id'), key);
        await insertReadings(ctx, key, data.faces);

        await ctx.put(STORE.records, {
            ...current,
            floor: data.floor,
            member_position: data.member_position,
            size_result: data.size_result,
            requirement_text: data.requirement_text,
            updated_at: stamp(),
            // template_type 刻意不在这里出现
        });
        return key;
    });
}

/** 删除记录及其读数；不存在 → LookupError。 */
export function deleteRecord(db, recordId) {
    const key = Number(recordId);
    return db.write([STORE.records, STORE.readings], async (ctx) => {
        const record = await ctx.get(STORE.records, key);
        if (!record) throw new LookupError(`检测记录不存在：#${recordId}`);
        await ctx.deleteByIndex(ctx.index(STORE.readings, 'record_id'), key);
        await ctx.delete(STORE.records, key);
        return record;
    });
}

/* --------------------------------------------------------------------------
 * 读取
 * ------------------------------------------------------------------------ */

export function getRecord(db, recordId) {
    return db.read([STORE.records], (ctx) => ctx.get(STORE.records, Number(recordId)));
}

/** 某条记录的读数，按 face 排序。 */
export async function getReadings(db, recordId) {
    const rows = await db.read([STORE.readings],
        (ctx) => ctx.allByIndex(ctx.index(STORE.readings, 'record_id'), Number(recordId)));
    return rows.sort((a, b) => (a.face < b.face ? -1 : a.face > b.face ? 1 : 0));
}

/** 一条记录的检测面视图（含最小值文本）—— 与 Python 的 _face_view 对应。 */
export function faceView(row) {
    const values = readingsOfRow(row);
    return {
        face: row.face,
        readings_text: values.map((value) => formatMm(value)),
        min_text: faceMinTextOfValid(values),
    };
}

/**
 * 项目下的记录，按模板分组（立柱在前），每组带 `count` 与每条记录的检测面视图。
 * 对应 Python 的 `grouped_by_template`。排序用复合索引 [project_id, template_type, sort_order]。
 */
export async function groupedByTemplate(db, projectId) {
    const key = Number(projectId);
    const [records, readings] = await db.read(
        [STORE.records, STORE.readings],
        async (ctx) => [
            await ctx.allByIndex(
                ctx.index(STORE.records, 'project_template_order'),
                IDBKeyRange.bound([key], [key, []], false, false)),
            await ctx.getAll(STORE.readings),
        ]);

    return CONFIG.TEMPLATE_TYPES.map((templateType) => {
        const mine = records
            .filter((record) => record.template_type === templateType)
            .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id - b.id);
        const items = mine.map((record) => ({
            record,
            faces: readings
                .filter((row) => row.record_id === record.id)
                .sort((a, b) => (a.face < b.face ? -1 : a.face > b.face ? 1 : 0))
                .map(faceView),
        }));
        return {
            template_type: templateType,
            name: CONFIG.TEMPLATE_NAMES[templateType],
            title: CONFIG.TEMPLATE_TITLES[templateType],
            short_name: CONFIG.TEMPLATE_SHORT_NAMES[templateType],
            requirement_label: CONFIG.REQUIREMENT_LABELS[templateType],
            count: items.length,
            records: items,
        };
    });
}

/** 分类计数（项目列表/详情页用）。 */
export async function countByTemplate(db, projectId) {
    const key = Number(projectId);
    return db.read([STORE.records], async (ctx) => {
        const counts = {};
        for (const templateType of CONFIG.TEMPLATE_TYPES) counts[templateType] = 0;
        for (const record of await ctx.allByIndex(ctx.index(STORE.records, 'project_id'), key)) {
            if (record.template_type in counts) counts[record.template_type] += 1;
        }
        return counts;
    });
}

/** 「立柱 5 条 · 横梁 3 条」文案。 */
export function describeCounts(counts) {
    const parts = CONFIG.TEMPLATE_TYPES.map(
        (templateType) => `${CONFIG.TEMPLATE_SHORT_NAMES[templateType]} ${counts[templateType] ?? 0} 条`);
    return parts.join(' · ');
}

function stamp(now = new Date()) {
    const pad = (value) => String(value).padStart(2, '0');
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} `
        + `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}
