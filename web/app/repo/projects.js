/* 项目读写：CRUD、列表统计、删除影响面、级联语义。
 *
 * 与 `webapp/services/projects.py` + `webapp/schema.sql` 对应。
 *
 * **级联是本文件最重要的部分**：IndexedDB 没有外键，`schema.sql` 里那句
 * `ON DELETE CASCADE` / `ON DELETE SET NULL` 必须手写，而且必须**同一事务**——
 * 否则中途失败会留下孤儿读数（用户看不见，但会污染导出）。
 */

import { CONFIG } from '../config.js';
import { IntegrityError, LookupError, STORE, translateConstraintError } from '../db.js';
import { clean } from '../clauses.js';

export const FORM_FIELDS = ['project_no', 'house_name', 'house_address', 'client_org', 'test_date'];

/* --------------------------------------------------------------------------
 * 读取
 * ------------------------------------------------------------------------ */

/** 项目列表 + 立柱/横梁记录数（项目 Tab 的卡片）。倒序：后建的在前。 */
export async function listWithCounts(db) {
    return db.read([STORE.projects, STORE.records], async (ctx) => {
        const projects = await ctx.getAll(STORE.projects);
        const records = await ctx.getAll(STORE.records);
        const counts = new Map();
        for (const record of records) {
            const key = `${record.project_id}`;
            const bucket = counts.get(key) ?? { column: 0, beam: 0 };
            if (record.template_type in bucket) bucket[record.template_type] += 1;
            counts.set(key, bucket);
        }
        return projects
            .sort((a, b) => b.id - a.id)
            .map((project) => {
                const bucket = counts.get(`${project.id}`) ?? { column: 0, beam: 0 };
                return { ...project, column_count: bucket.column, beam_count: bucket.beam };
            });
    });
}

export function get(db, projectId) {
    return db.read([STORE.projects], (ctx) => ctx.get(STORE.projects, Number(projectId)));
}

/** 缺陷填报「绑定项目」下拉用的轻量列表。 */
export function listOptions(db) {
    return db.read([STORE.projects], async (ctx) => {
        const projects = await ctx.getAll(STORE.projects);
        return projects
            .sort((a, b) => b.id - a.id)
            .map(({ id, project_no, house_name }) => ({ id, project_no, house_name }));
    });
}

/** 删除影响面：检测记录分类计数 + 关联缺陷报告数。 */
export async function deleteImpact(db, projectId) {
    return db.read([STORE.records, STORE.defects], async (ctx) => {
        const counts = { column: 0, beam: 0, defects: 0 };
        for (const record of await ctx.allByIndex(ctx.index(STORE.records, 'project_id'), Number(projectId))) {
            if (record.template_type in counts) counts[record.template_type] += 1;
        }
        counts.defects = (await ctx.allByIndex(
            ctx.index(STORE.defects, 'project_id'), Number(projectId))).length;
        counts.records = counts.column + counts.beam;
        return counts;
    });
}

/**
 * 删除确认文案。措辞与 DB 语义严格一致：记录级联删除、缺陷报告解除绑定并保留。
 * （对应 Python 的 `build_delete_message`，含项目详情页要用的那句）
 */
export function buildDeleteMessage(project, impact) {
    const parts = [
        `确认删除项目「${project.house_name}（${project.project_no}）」？`,
        `将同时删除 ${impact.records} 条检测记录（立柱 ${impact.column} 条、横梁 ${impact.beam} 条）`,
    ];
    parts.push(impact.defects
        ? `关联的 ${impact.defects} 份缺陷报告将解除绑定并保留`
        : '该项目没有关联的缺陷报告');
    return `${parts.join('；')}。`;
}

/* --------------------------------------------------------------------------
 * 校验与写入
 * ------------------------------------------------------------------------ */

/** 解析项目表单，返回 `{data, errors}`；errors 的键即字段名。 */
export function parseForm(form) {
    const errors = {};
    const data = {};
    for (const field of FORM_FIELDS) {
        data[field] = clean(form?.get?.(field) ?? form?.[field]) || null;
    }

    if (!data.project_no) errors.project_no = '项目编号不能为空';
    if (!data.house_name) errors.house_name = '房屋名称不能为空';

    for (const [field, [limit, label]] of Object.entries(CONFIG.PROJECT_FIELD_LIMITS)) {
        const value = data[field];
        if (value && value.length > limit) {
            errors[field] = `${label}不能超过 ${limit} 个字符`;
        }
    }

    if (data.test_date && !isValidDate(data.test_date)) {
        errors.test_date = '检测日期格式应为 YYYY-MM-DD';
    }
    return { data, errors };
}

export function isValidDate(text) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(text));
    if (!match) return false;
    const [, y, m, d] = match;
    const date = new Date(`${y}-${m}-${d}T00:00:00Z`);
    return date.getUTCFullYear() === Number(y)
        && date.getUTCMonth() + 1 === Number(m)
        && date.getUTCDate() === Number(d);
}

/**
 * 新建项目，返回新 id。
 * 项目编号重复 → 抛 `IntegrityError`（对应 sqlite3.IntegrityError，由路由捕获成字段错误）。
 */
export async function create(db, data) {
    const now = timestamp();
    try {
        return await db.write([STORE.projects], (ctx) => ctx.insert(STORE.projects, {
            project_no: data.project_no,
            house_name: data.house_name,
            house_address: data.house_address,
            client_org: data.client_org,
            test_date: data.test_date,
            created_at: now,
            updated_at: now,
        }));
    } catch (error) {
        throw translateConstraintError(error, `项目编号「${data.project_no}」已存在`);
    }
}

/** 更新项目；不存在 → LookupError。 */
export async function update(db, projectId, data) {
    return db.write([STORE.projects], async (ctx) => {
        const current = await ctx.get(STORE.projects, Number(projectId));
        if (!current) throw new LookupError(`项目不存在：#${projectId}`);
        try {
            await ctx.put(STORE.projects, {
                ...current,
                project_no: data.project_no,
                house_name: data.house_name,
                house_address: data.house_address,
                client_org: data.client_org,
                test_date: data.test_date,
                updated_at: timestamp(),
            });
        } catch (error) {
            throw translateConstraintError(error, `项目编号「${data.project_no}」已被其他项目使用`);
        }
    });
}

/**
 * 删除项目：检测记录与其读数**级联删除**；关联缺陷报告**解除绑定并保留**。
 *
 * 一个事务里跨 4 个 store —— 这正是"手写级联"要守住的东西。
 */
export async function remove(db, projectId, options = {}) {
    const projectKey = Number(projectId);
    return db.write(
        [STORE.projects, STORE.records, STORE.readings, STORE.defects],
        async (ctx) => {
            const project = await ctx.get(STORE.projects, projectKey);
            if (!project) throw new LookupError(`项目不存在：#${projectId}`);

            // 1) 先按项目删掉每条记录的读数（表里没有 project_id，必须经 records 中转）
            const records = await ctx.allByIndex(
                ctx.index(STORE.records, 'project_id'), projectKey);
            for (const record of records) {
                await ctx.deleteByIndex(ctx.index(STORE.readings, 'record_id'), record.id);
            }

            // 2) 删记录
            await ctx.deleteByIndex(ctx.index(STORE.records, 'project_id'), projectKey);

            // 3) 缺陷报告：置空 project_id（保留报告本体）
            const defects = await ctx.allByIndex(
                ctx.index(STORE.defects, 'project_id'), projectKey);
            for (const defect of defects) {
                await ctx.put(STORE.defects, { ...defect, project_id: null });
            }

            // 4) 删项目
            await ctx.delete(STORE.projects, projectKey);
            return { project, records: records.length, unboundDefects: defects.length };
        },
    );
}

/** 本地时间戳（与 SQLite 的 `datetime('now','localtime')` 同格式）。 */
export function timestamp(now = new Date()) {
    const pad = (value) => String(value).padStart(2, '0');
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} `
        + `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}
