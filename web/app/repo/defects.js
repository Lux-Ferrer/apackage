/* 缺陷报告（报告管理）读写：表单解析、事务化写入、列表/统计/删除、附页数据装配。
 *
 * 与 `webapp/services/defects.py`（含 M4 加的报告管理部分）对应。
 *
 * 三条要点：
 *  1. `risk_level` 的 CHECK 约束在 IndexedDB 里**没有对应物** —— 必须在这里校验，
 *     且导入路径也要走同一个函数（见 `web/app/import-export.js`）；
 *  2. 图片是独立 store，**入库失败要一起回滚**（Python 侧是"删掉刚落盘的文件"，
 *     一个事务天然更安全）；
 *  3. `schema.sql` 里 `defects.project_id … ON DELETE SET NULL` 的语义由
 *     `projects.remove()` 手写（保留报告、只解绑）。
 */

import { CONFIG } from '../config.js';
import { LookupError, STORE, translateConstraintError } from '../db.js';
import { clean } from '../clauses.js';
import { displayText } from '../clauses.js';
import { DEFAULT_PROFILE } from '../product.js';

import { read as readProfile } from './profile.js';

/* --------------------------------------------------------------------------
 * 表单解析
 * ------------------------------------------------------------------------ */

/**
 * 解析缺陷填报表单（**不含图片**，图片单独校验与压缩）。
 * 返回 `{data, errors}`；errors 的键即字段名。
 */
export async function parseForm(db, form) {
    const errors = {};
    const read = (key) => clean(form?.get?.(key) ?? form?.[key]);

    let defectType = read('defect_type');
    if (defectType === CONFIG.CUSTOM_DEFECT_OPTION) {
        defectType = read('custom_defect_type');
        if (!defectType) errors.custom_defect_type = '选择了「其他」时，请填写自定义缺陷类型';
    }

    const projectPart = read('project_part');
    const riskLevel = read('risk_level') || CONFIG.DEFAULT_RISK_LEVEL;
    const rectificationPlan = read('rectification_plan');

    if (!defectType) errors.defect_type = '缺陷类型不能为空';
    if (!CONFIG.RISK_LEVELS.includes(riskLevel)) errors.risk_level = '隐患等级无效';
    if (!projectPart) errors.project_part = '工程部位不能为空';
    if (!rectificationPlan) errors.rectification_plan = '整改方案不能为空';

    const projectIdRaw = read('project_id');
    let bound = null;
    if (projectIdRaw) {
        const project = /^\d+$/.test(projectIdRaw)
            ? await db.read([STORE.projects], (ctx) => ctx.get(STORE.projects, Number(projectIdRaw)))
            : null;
        if (!project) errors.project_id = '绑定的项目不存在';
        else bound = project.id;
    }

    // 报告人是**当前设备**在「我的 → 个人信息配置」里填的名字（没填过 → 出厂默认值）。
    const reporter = await readProfile(db);

    return {
        data: {
            defect_type: defectType,
            project_part: projectPart,
            risk_level: riskLevel,
            rectification_plan: rectificationPlan,
            related_standards: read('related_standards') || null,
            extra_advice: read('extra_advice') || null,
            project_id: bound,
            reporter_name: reporter.reporter_name,
            reporter_department: reporter.reporter_department,
            created_at: timestamp(),
        },
        errors,
    };
}

/* --------------------------------------------------------------------------
 * 写入
 * ------------------------------------------------------------------------ */

/**
 * 保存一份缺陷报告。
 *
 * `image` 是已经压缩好的图片记录（`{id, blob, thumb, width, height, bytes, mime}`）或 null；
 * 图片与报告**同一事务**写入 —— 任一步失败一起回滚，不留孤儿图片。
 *
 * `data.reporter_*` 一般由 `parseForm()` 从「个人信息配置」里带出来；这里只兜底
 * （直接调用本函数的场景：备份导入、测试），兜底值是 `product.js` 的出厂默认值。
 * 报告里存的是**写入当时的快照** —— 以后改了个人信息，历史报告不受影响。
 */
export function create(db, data, image = null) {
    assertRiskLevel(data.risk_level);
    return db.write([STORE.defects, STORE.images], async (ctx) => {
        if (image) await ctx.put(STORE.images, image);
        try {
            return await ctx.insert(STORE.defects, {
                project_id: data.project_id ?? null,
                defect_type: data.defect_type,
                project_part: data.project_part,
                risk_level: data.risk_level,
                rectification_plan: data.rectification_plan,
                related_standards: data.related_standards ?? null,
                extra_advice: data.extra_advice ?? null,
                reporter_name: data.reporter_name ?? DEFAULT_PROFILE.reporter_name,
                reporter_department: data.reporter_department ?? DEFAULT_PROFILE.reporter_department,
                image_path: image ? image.id : null,
                created_at: data.created_at ?? timestamp(),
            });
        } catch (error) {
            throw translateConstraintError(error, '缺陷报告写入失败');
        }
    });
}

/** CHECK (risk_level IN ('高','中','低')) 的等价物 —— IndexedDB 不会替我们做。 */
export function assertRiskLevel(riskLevel) {
    if (!CONFIG.RISK_LEVELS.includes(riskLevel)) {
        throw new Error(`隐患等级无效：${riskLevel}（只能是 ${CONFIG.RISK_LEVELS.join('/')}）`);
    }
}

/* --------------------------------------------------------------------------
 * 读取
 * ------------------------------------------------------------------------ */

export function get(db, defectId) {
    return db.read([STORE.defects], (ctx) => ctx.get(STORE.defects, Number(defectId)));
}

/** 单条报告 + 绑定项目的编号/名称（详情页卡片与列表卡共用同一份视图）。 */
export async function getWithProject(db, defectId) {
    return db.read([STORE.defects, STORE.projects], async (ctx) => {
        const defect = await ctx.get(STORE.defects, Number(defectId));
        if (!defect) return null;
        const project = defect.project_id
            ? await ctx.get(STORE.projects, defect.project_id)
            : null;
        return {
            ...defect,
            project_no: project ? project.project_no : null,
            house_name: project ? project.house_name : null,
        };
    });
}

/**
 * 报告列表（倒序），带绑定项目信息。
 *
 * 排序 `created_at DESC, id DESC`：索引项按 (key, primaryKey) 升序排列，
 * `prev` 反向后**同 key 内即 primaryKey 降序** —— 与 SQL 的写法等价。
 * `risk_level` 给定时按等级筛选（走索引，不扫全表）。
 */
export async function listReports(db, riskLevel = null) {
    assertOptionalRiskLevel(riskLevel);
    return db.read([STORE.defects, STORE.projects], async (ctx) => {
        const rows = riskLevel
            ? await ctx.allByIndex(ctx.index(STORE.defects, 'risk_level'), riskLevel)
            : await cursorAll(ctx.index(STORE.defects, 'created_at'), null, 'prev');
        const sorted = [...rows].sort(compareCreatedDesc);

        const projects = new Map();
        for (const row of sorted) {
            if (row.project_id && !projects.has(row.project_id)) {
                projects.set(row.project_id, await ctx.get(STORE.projects, row.project_id) ?? null);
            }
        }
        return sorted.map((row) => {
            const project = row.project_id ? projects.get(row.project_id) : null;
            return {
                ...row,
                project_no: project ? project.project_no : null,
                house_name: project ? project.house_name : null,
            };
        });
    });
}

/** 反向游标读全表（`prev` 用于倒序）。 */
async function cursorAll(index, query, direction) {
    const rows = [];
    const source = index.openCursor(query, direction);
    await new Promise((resolve, reject) => {
        source.onsuccess = () => {
            const cursor = source.result;
            if (!cursor) {
                resolve();
                return;
            }
            rows.push(cursor.value);
            cursor.continue();
        };
        source.onerror = () => reject(source.error);
    });
    return rows;
}

function compareCreatedDesc(a, b) {
    if (a.created_at !== b.created_at) return a.created_at < b.created_at ? 1 : -1;
    return b.id - a.id;
}

function assertOptionalRiskLevel(riskLevel) {
    if (riskLevel && !CONFIG.RISK_LEVELS.includes(riskLevel)) {
        throw new Error(`未知的筛选值「${riskLevel}」`);
    }
}

/** 项目关联的报告（倒序）。删除项目时 project_id 被置空，故不会出现在这里。 */
export async function listForProject(db, projectId) {
    const rows = await db.read([STORE.defects],
        (ctx) => ctx.allByIndex(ctx.index(STORE.defects, 'project_id'), Number(projectId)));
    return rows.sort(compareCreatedDesc);
}

export async function countForProject(db, projectId) {
    return db.read([STORE.defects], (ctx) => ctx.countByIndex(
        ctx.index(STORE.defects, 'project_id'), Number(projectId)));
}

/**
 * 顶部统计：总数 + 高/中/低，**恒为全量**（不随筛选变化）。
 *
 * 对应 M4 的那条 `COUNT(*) + COALESCE(SUM(CASE WHEN …))`：
 * IndexedDB 用 4 个索引 count，空库返回 0 —— SQL 里 `COALESCE` 那个坑自然消失。
 */
export async function stats(db) {
    return db.read([STORE.defects], async (ctx) => {
        const [total, high, medium, low] = await Promise.all([
            ctx.count(STORE.defects),
            ctx.countByIndex(ctx.index(STORE.defects, 'risk_level'), '高'),
            ctx.countByIndex(ctx.index(STORE.defects, 'risk_level'), '中'),
            ctx.countByIndex(ctx.index(STORE.defects, 'risk_level'), '低'),
        ]);
        return { total, high, medium, low };
    });
}

/* --------------------------------------------------------------------------
 * 删除
 * ------------------------------------------------------------------------ */

/** 删除一份报告（含隐患图片）。关联就在这一行上，删行即解绑。 */
export function remove(db, defectId) {
    const key = Number(defectId);
    return db.write([STORE.defects, STORE.images], async (ctx) => {
        const defect = await ctx.get(STORE.defects, key);
        if (!defect) throw new LookupError(`报告不存在：#${defectId}`);
        await ctx.delete(STORE.defects, key);
        if (defect.image_path) await ctx.delete(STORE.images, defect.image_path);
        return defect;
    });
}

/** 清除全部报告（需求 3.7c「清除全部报告」）。返回 `{reports, images}`。 */
export function deleteAll(db) {
    return db.write([STORE.defects, STORE.images], async (ctx) => {
        const reports = await ctx.getAll(STORE.defects);
        await ctx.clear(STORE.defects);
        let images = 0;
        for (const report of reports) {
            if (report.image_path) {
                await ctx.delete(STORE.images, report.image_path);
                images += 1;
            }
        }
        return { reports: reports.length, images };
    });
}

/* --------------------------------------------------------------------------
 * 附页渲染数据（需求报告 4.4）
 * ------------------------------------------------------------------------ */

/** 报告时间按 `yyyy-MM-dd HH:mm` 显示。 */
export function formatReportTime(value) {
    const text = clean(value);
    return text.length >= 16 ? text.slice(0, 16) : text;
}

/** 附页信息表的取值：按 `CONFIG.ATTACHMENT_ORDER` 组装，空值占位「无」。 */
export function fieldValues(view) {
    const defect = view.defect;
    return {
        defect_type: defect.defect_type,
        project_part: defect.project_part,
        risk_level: defect.risk_level,
        rectification_plan: defect.rectification_plan,
        extra_advice: clean(defect.extra_advice) || CONFIG.EMPTY_TEXT,
        related_standards: clean(defect.related_standards) || CONFIG.EMPTY_TEXT,
        reporter: `${defect.reporter_name}（${defect.reporter_department}）`,
        reported_at: formatReportTime(defect.created_at),
        image_file: imageFileText(view),
    };
}

/** 「图片文件」行的内容：原文件名 + 是否压缩 / 是否缺失（对应 Python 的 image_file_text）。 */
export function imageFileText(view) {
    const name = clean(view.original_name);
    if (!name) return CONFIG.EMPTY_TEXT;
    if (view.missing) return `${name}（文件缺失）`;
    return view.compressed ? `${name}（已压缩）` : name;
}

export function stamp(now = new Date()) {
    const pad = (value) => String(value).padStart(2, '0');
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} `
        + `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}

export function timestamp(now = new Date()) {
    return stamp(now);
}
