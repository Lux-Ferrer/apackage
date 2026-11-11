/* 个人信息（报告人姓名 / 部门）—— 存在 IndexedDB 的 `meta` 表里。
 *
 * 为什么放 `meta` 而不是新建一张表
 * --------------------------------
 * `meta` 是 key → value 的通用键值表（建库时就存在，见 `db.js` 的 `STORE.meta`），
 * 本来只放 `schemaVersion`。个人信息是**单例配置**，不是业务实体：
 * 放进去不需要升 schema 版本，也就没有"老用户升级时库结构不匹配"的风险 ——
 * 现场工具最不能承受的就是升级后打不开。
 *
 * 三条纪律
 * --------
 *  1. **取不到就用出厂默认值**（`product.js` 的 `DEFAULT_PROFILE`）。
 *     所以"没配过"和"配成默认值"在行为上等价，不需要额外的初始化步骤；
 *  2. 保存时**校验长度并去空白**：报告人这一栏会原样写进 Word 附页，
 *     前面带一串空格在打印稿上很难看；
 *  3. 这是**当前设备**的设置，不进备份 zip（备份是业务数据快照）。
 *     换手机/换浏览器后需要在「我的 → 个人信息配置」里重填一次。
 */

import { DEFAULT_PROFILE, PROFILE_LIMITS } from '../product.js';
import { STORE } from '../db.js';
import { clean } from '../clauses.js';

/** `meta` 里的键名（同一个表里还有 `schemaVersion`，别撞名）。 */
export const PROFILE_KEY = 'profile';

/** 出厂默认值（拷贝一份，避免调用方改到冻结对象）。 */
export function defaults() {
    return { ...DEFAULT_PROFILE };
}

/**
 * 把任意来源的值归一成一份**永远可用**的个人信息。
 *
 * 备份恢复、老库、手工写坏的 meta 都走这一条：宁可回到默认值，也不让界面出现空白报告人。
 */
export function normalize(value) {
    const name = clean(value?.reporter_name).slice(0, PROFILE_LIMITS.reporter_name);
    const department = clean(value?.reporter_department).slice(0, PROFILE_LIMITS.reporter_department);
    return {
        reporter_name: name || DEFAULT_PROFILE.reporter_name,
        reporter_department: department || DEFAULT_PROFILE.reporter_department,
    };
}

/** 读当前设备的个人信息（没配过 → 出厂默认值）。 */
export async function read(db) {
    const row = await db.read([STORE.meta], (ctx) => ctx.get(STORE.meta, PROFILE_KEY));
    return normalize(row?.value);
}

/**
 * 解析表单 → `{data, errors}`（与 `repo/projects.js::parseForm` 同一套约定）。
 *
 * 两个字段都必填：它们是报告上的署名，空着导出就成了「（ ）」。
 */
export function parseForm(form) {
    const errors = {};
    const read = (key) => clean(form?.get?.(key) ?? form?.[key]);

    const name = read('reporter_name');
    const department = read('reporter_department');
    if (!name) errors.reporter_name = '报告人姓名不能为空';
    else if (name.length > PROFILE_LIMITS.reporter_name) {
        errors.reporter_name = `报告人姓名不能超过 ${PROFILE_LIMITS.reporter_name} 个字`;
    }
    if (!department) errors.reporter_department = '部门不能为空';
    else if (department.length > PROFILE_LIMITS.reporter_department) {
        errors.reporter_department = `部门不能超过 ${PROFILE_LIMITS.reporter_department} 个字`;
    }

    return { data: { reporter_name: name, reporter_department: department }, errors };
}

/** 保存个人信息（`meta` 里一行，含更新时间 —— 排错时能看出是这台设备什么时候填的）。 */
export async function save(db, data, { now = new Date() } = {}) {
    const value = {
        reporter_name: clean(data.reporter_name),
        reporter_department: clean(data.reporter_department),
        updated_at: stamp(now),
    };
    await db.write([STORE.meta], (ctx) => ctx.put(STORE.meta, { key: PROFILE_KEY, value }));
    return normalize(value);
}

function stamp(now) {
    const pad = (value) => String(value).padStart(2, '0');
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} `
        + `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}
