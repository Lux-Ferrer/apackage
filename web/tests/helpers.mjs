/* 测试夹具：每个用例一个**独立的内存 IndexedDB**。
 *
 * `new IDBFactory()` 是 fake-indexeddb 提供的隔离手段 —— 比"用完删库"干净，
 * 也不会因为用例并行而互相干扰。`fake-indexeddb/auto` 负责把 IDBKeyRange 等
 * 全局对象补上（db.js 里用了全局 IDBKeyRange）。
 */
import 'fake-indexeddb/auto';
import { IDBFactory } from 'fake-indexeddb';

import { Database } from '../app/db.js';
import * as projects from '../app/repo/projects.js';
import * as measurements from '../app/repo/measurements.js';
import * as defects from '../app/repo/defects.js';

let counter = 0;

/** 打开一个全新的空库。 */
export async function freshDb() {
    counter += 1;
    return Database.open({
        factory: new IDBFactory(),
        name: `test_${counter}_${Math.floor(Math.random() * 1e6)}`,
    });
}

/** 建一个项目（走 parseForm，顺带覆盖校验路径）。 */
export async function makeProject(db, overrides = {}) {
    const form = {
        project_no: `P-${Math.floor(Math.random() * 1e6)}`,
        house_name: '金骐智谷',
        house_address: '',
        client_org: '',
        test_date: '',
        ...overrides,
    };
    const { data, errors } = projects.parseForm(form);
    if (Object.keys(errors).length) throw new Error(`夹具项目校验失败：${JSON.stringify(errors)}`);
    return projects.create(db, data);
}

/** 构造一次检测记录提交（默认：一个面 B、5 个读数）。 */
export function recordForm(overrides = {}) {
    const form = {
        floor: '六层',
        member_position: '1',
        size_result: '63x164',
        requirement_index: '0',
        face_0: 'B',
        value_0_1: '2.99', value_0_2: '3.02', value_0_3: '3.01',
        value_0_4: '3.01', value_0_5: '2.99',
        ...overrides,
    };
    return form;
}

/** 走完整链路创建一条检测记录，返回 id。 */
export async function makeRecord(db, projectId, overrides = {}, templateType = 'column') {
    const form = recordForm(overrides);
    const { data, errors } = measurements.parseRecordForm(form, templateType);
    if (Object.keys(errors).length) throw new Error(`夹具记录校验失败：${JSON.stringify(errors)}`);
    return measurements.createRecord(db, projectId, templateType, data);
}

/** 构造一份缺陷报告（走 parseForm）。 */
export async function makeDefect(db, overrides = {}, image = null) {
    const form = {
        defect_type: '密封胶开裂',
        project_part: '东立面三层 1# 立柱',
        risk_level: '中',
        rectification_plan: '更换密封胶',
        related_standards: '',
        extra_advice: '',
        project_id: '',
        ...overrides,
    };
    const { data, errors } = await defects.parseForm(db, form);
    if (Object.keys(errors).length) throw new Error(`夹具报告校验失败：${JSON.stringify(errors)}`);
    return defects.create(db, data, image);
}

export { projects, measurements, defects };
