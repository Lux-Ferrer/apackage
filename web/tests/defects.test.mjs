/* 缺陷报告（报告管理）：解析、写入、列表/统计/删除、附页数据。
 * 断言对应 Python 侧的 `tests/test_defects.py` 数据层部分 + M4 报告管理的数据语义。
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { CONFIG } from '../app/config.js';
import { STORE } from '../app/db.js';
import { fieldValues, imageFileText, formatReportTime } from '../app/repo/defects.js';
import { originalNameFromPath, sanitizeOriginalName, makeImageKey, validateFile } from '../app/repo/images.js';
import { freshDb, makeDefect, makeProject, projects, defects } from './helpers.mjs';

const IMAGE = Object.freeze({
    id: 'abc123_缺陷照片.jpg', blob: 'blob', thumb: 'thumb',
    width: 600, height: 400, bytes: 1234, mime: 'image/jpeg',
});

/* --------------------------------------------------------------------------
 * 表单解析（对应 test_parse_*）
 * ------------------------------------------------------------------------ */

test('合法表单：选填转 null，默认等级「中」，报告人取默认配置', async () => {
    const db = await freshDb();
    const { data, errors } = await defects.parseForm(db, {
        defect_type: '密封胶开裂', project_part: '东立面三层 1# 立柱',
        risk_level: '高', rectification_plan: '更换密封胶',
        related_standards: '  ', extra_advice: '', project_id: '',
    });
    assert.deepEqual(errors, {});
    assert.equal(data.related_standards, null);
    assert.equal(data.extra_advice, null);
    assert.equal(data.project_id, null);
    assert.equal(data.risk_level, '高');
    assert.equal(data.reporter_name, CONFIG.DEFAULT_REPORTER.name);
    assert.equal(data.reporter_department, CONFIG.DEFAULT_REPORTER.department);
    assert.match(data.created_at, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);
    db.close();
});

test('未选等级时按默认「中」处理', async () => {
    const db = await freshDb();
    const { data } = await defects.parseForm(db, {
        defect_type: '密封胶开裂', project_part: '东立面', risk_level: '', rectification_plan: '打胶',
    });
    assert.equal(data.risk_level, CONFIG.DEFAULT_RISK_LEVEL);
    db.close();
});

test('选「其他」时必须填自定义类型', async () => {
    const db = await freshDb();
    const blank = await defects.parseForm(db, {
        defect_type: CONFIG.CUSTOM_DEFECT_OPTION, custom_defect_type: '   ',
        project_part: '东立面', rectification_plan: '打胶',
    });
    assert.equal(blank.errors.custom_defect_type, '选择了「其他」时，请填写自定义缺陷类型');

    const filled = await defects.parseForm(db, {
        defect_type: CONFIG.CUSTOM_DEFECT_OPTION, custom_defect_type: '幕墙开启扇脱落',
        project_part: '东立面', rectification_plan: '打胶',
    });
    assert.equal(filled.data.defect_type, '幕墙开启扇脱落');
    db.close();
});

test('必填字段逐项报错', async () => {
    const db = await freshDb();
    const { errors } = await defects.parseForm(db, {
        defect_type: '', project_part: '', risk_level: '紧急', rectification_plan: '',
    });
    assert.equal(errors.defect_type, '缺陷类型不能为空');
    assert.equal(errors.project_part, '工程部位不能为空');
    assert.equal(errors.risk_level, '隐患等级无效');
    assert.equal(errors.rectification_plan, '整改方案不能为空');
    db.close();
});

test('绑定项目：存在的通过、不存在的报错', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    const bound = await defects.parseForm(db, {
        defect_type: '密封胶开裂', project_part: '东立面', rectification_plan: '打胶',
        project_id: `${projectId}`,
    });
    assert.equal(bound.data.project_id, projectId);

    const unknown = await defects.parseForm(db, {
        defect_type: '密封胶开裂', project_part: '东立面', rectification_plan: '打胶',
        project_id: '999',
    });
    assert.equal(unknown.errors.project_id, '绑定的项目不存在');
    db.close();
});

/* --------------------------------------------------------------------------
 * 写入与读取
 * ------------------------------------------------------------------------ */

test('创建：报告与图片同一事务落地', async () => {
    const db = await freshDb();
    const defectId = await makeDefect(db, {}, IMAGE);

    const defect = await defects.get(db, defectId);
    assert.equal(defect.image_path, IMAGE.id);
    assert.deepEqual(defect.risk_level, '中');

    const stored = await db.read([STORE.images], (ctx) => ctx.get(STORE.images, IMAGE.id));
    assert.deepEqual(stored.thumb, 'thumb');
    db.close();
});

test('创建：绑定项目后可按项目查到', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    await makeDefect(db, { project_id: `${projectId}` });
    assert.equal(await defects.countForProject(db, projectId), 1);
    assert.equal((await defects.listForProject(db, projectId)).length, 1);
    db.close();
});

test('创建：图片写入成功但报告失败 → 图片也回滚（一个事务）', async () => {
    const db = await freshDb();
    await assert.rejects(() => db.write([STORE.defects, STORE.images], async (ctx) => {
        await ctx.put(STORE.images, { id: 'orphan.jpg' });
        await ctx.insert(STORE.defects, { defect_type: 'x', project_part: 'y', risk_level: '紧急' });
        throw new Error('不可能到达');
    }));
    // risk_level 没有 CHECK，所以这里靠显式抛错收尾；重点是图片不会留下
    assert.deepEqual(await db.read([STORE.images], (ctx) => ctx.getAll(STORE.images)), []);
    db.close();
});

test('获取报告 + 绑定项目信息（详情页与列表卡共用）', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db, { project_no: 'JCZG-2026-001', house_name: '金骐智谷' });
    const defectId = await makeDefect(db, { project_id: `${projectId}` });

    const withProject = await defects.getWithProject(db, defectId);
    assert.equal(withProject.project_no, 'JCZG-2026-001');
    assert.equal(withProject.house_name, '金骐智谷');

    const unbound = await defects.getWithProject(db, await makeDefect(db));
    assert.equal(unbound.project_no, null);
    db.close();
});

/* --------------------------------------------------------------------------
 * 列表与统计（M4 报告管理的数据语义）
 * ------------------------------------------------------------------------ */

async function insertDefectAt(db, createdAt, riskLevel = '中') {
    return db.write([STORE.defects], (ctx) => ctx.insert(STORE.defects, {
        project_id: null, defect_type: '密封胶开裂', project_part: '东立面',
        risk_level: riskLevel, rectification_plan: '打胶',
        related_standards: null, extra_advice: null,
        reporter_name: CONFIG.DEFAULT_REPORTER.name,
        reporter_department: CONFIG.DEFAULT_REPORTER.department,
        image_path: null, created_at: createdAt,
    }));
}

test('列表按 created_at 倒序；同秒内按 id 倒序', async () => {
    const db = await freshDb();
    const early = await insertDefectAt(db, '2026-09-20 09:00:00');
    const sameA = await insertDefectAt(db, '2026-09-22 10:00:00');
    const sameB = await insertDefectAt(db, '2026-09-22 10:00:00');
    const late = await insertDefectAt(db, '2026-09-25 18:30:00');

    const list = await defects.listReports(db);
    assert.deepEqual(list.map((row) => row.id), [late, sameB, sameA, early]);
    db.close();
});

test('列表带绑定项目信息；未绑定的不报错', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db, { project_no: 'P-1', house_name: '某楼' });
    await makeDefect(db, { project_id: `${projectId}` });
    await makeDefect(db);

    const list = await defects.listReports(db);
    assert.equal(list.length, 2);
    assert.ok(list.some((row) => row.project_no === 'P-1' && row.house_name === '某楼'));
    assert.ok(list.some((row) => row.project_no === null));
    db.close();
});

test('按等级筛选；未绑定项目也能筛', async () => {
    const db = await freshDb();
    await makeDefect(db, { risk_level: '高' });
    await makeDefect(db, { risk_level: '中' });
    await makeDefect(db, { risk_level: '低' });

    assert.equal((await defects.listReports(db, '高')).length, 1);
    assert.equal((await defects.listReports(db, '高'))[0].risk_level, '高');
    assert.equal((await defects.listReports(db)).length, 3);
    await assert.rejects(() => defects.listReports(db, '紧急'), /未知的筛选值/);
    db.close();
});

test('统计恒为全量；空库返回 0（SQL 的 COALESCE 坑在这里不存在）', async () => {
    const db = await freshDb();
    assert.deepEqual(await defects.stats(db), { total: 0, high: 0, medium: 0, low: 0 });

    await makeDefect(db, { risk_level: '高' });
    await makeDefect(db, { risk_level: '高' });
    await makeDefect(db, { risk_level: '低' });
    assert.deepEqual(await defects.stats(db), { total: 3, high: 2, medium: 0, low: 1 });
    db.close();
});

/* --------------------------------------------------------------------------
 * 删除
 * ------------------------------------------------------------------------ */

test('删除报告：行与图片一起删除；不存在 → LookupError', async () => {
    const db = await freshDb();
    const defectId = await makeDefect(db, {}, IMAGE);

    const removed = await defects.remove(db, defectId);
    assert.equal(removed.id, defectId);
    assert.equal(await defects.get(db, defectId), undefined);
    assert.equal(await db.read([STORE.images], (ctx) => ctx.get(STORE.images, IMAGE.id)), undefined);

    await assert.rejects(() => defects.remove(db, defectId),
        (error) => error.name === 'LookupError');
    db.close();
});

test('删除项目后报告仍在，但已解绑（与 Python 的 ON DELETE SET NULL 一致）', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    const defectId = await makeDefect(db, { project_id: `${projectId}` });

    await projects.remove(db, projectId);

    const defect = await defects.get(db, defectId);
    assert.ok(defect);
    assert.equal(defect.project_id, null);
    db.close();
});

test('清除全部报告：只清报告与图片，项目与记录不受影响', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    await makeDefect(db, {}, { ...IMAGE, id: 'one.jpg' });
    await makeDefect(db, {}, { ...IMAGE, id: 'two.jpg' });

    const removed = await defects.deleteAll(db);
    assert.deepEqual(removed, { reports: 2, images: 2 });
    assert.deepEqual(await defects.stats(db), { total: 0, high: 0, medium: 0, low: 0 });
    assert.deepEqual(await db.read([STORE.images], (ctx) => ctx.getAll(STORE.images)), []);
    assert.equal((await projects.listWithCounts(db)).length, 1);
    db.close();
});

test('清除全部报告：空库返回 0，不报错', async () => {
    const db = await freshDb();
    assert.deepEqual(await defects.deleteAll(db), { reports: 0, images: 0 });
    db.close();
});

/* --------------------------------------------------------------------------
 * 附页数据（对应 test_format_report_time / test_field_values_*）
 * ------------------------------------------------------------------------ */

test('报告时间按 yyyy-MM-dd HH:mm 显示', () => {
    assert.equal(formatReportTime('2026-09-22 10:00:00'), '2026-09-22 10:00');
    assert.equal(formatReportTime(''), '');
    assert.equal(formatReportTime(null), '');
});

test('附页取值：选填空 → 「无」，报告人合成「姓名（部门）」', () => {
    const values = fieldValues({
        defect: {
            defect_type: '密封胶开裂', project_part: '东立面三层', risk_level: '高',
            rectification_plan: '更换密封胶', extra_advice: '', related_standards: null,
            reporter_name: 'Zeyu Jin', reporter_department: '结构工程部',
            created_at: '2026-09-22 10:00:00',
        },
        original_name: '缺陷照片.jpg',
    });
    assert.equal(values.extra_advice, '无');
    assert.equal(values.related_standards, '无');
    assert.equal(values.reporter, 'Zeyu Jin（结构工程部）');
    assert.equal(values.reported_at, '2026-09-22 10:00');
    assert.equal(values.image_file, '缺陷照片.jpg');
});

test('「图片文件」行：缺图 → 「无」；压缩过 → 标注；文件缺失 → 标注', () => {
    assert.equal(imageFileText({ original_name: '' }), '无');
    assert.equal(imageFileText({ original_name: 'a.jpg' }), 'a.jpg');
    assert.equal(imageFileText({ original_name: 'a.jpg', compressed: true }), 'a.jpg（已压缩）');
    assert.equal(imageFileText({ original_name: 'a.jpg', missing: true }), 'a.jpg（文件缺失）');
});

/* --------------------------------------------------------------------------
 * 图片命名与校验（对应 images.py 的 sanitize / original_name / validate）
 * ------------------------------------------------------------------------ */

test('文件名清洗：去掉路径与危险字符，保留中文', () => {
    assert.equal(sanitizeOriginalName('C:\\photos\\缺陷照片.jpg'), '缺陷照片.jpg');
    assert.equal(sanitizeOriginalName('a/b:c*d.jpg'), 'b_c_d.jpg');
    assert.equal(sanitizeOriginalName(''), 'image');
    assert.equal(sanitizeOriginalName('   '), 'image');
});

test('从 key 反推原始文件名', () => {
    const key = makeImageKey('缺陷照片.PNG', 'abcdef0123456789abcdef0123456789');
    assert.match(key, /^abcdef0123456789abcdef0123456789_缺陷照片\.png$/);
    assert.equal(originalNameFromPath(key), '缺陷照片.png');
    assert.equal(originalNameFromPath(''), '');
});

test('上传校验：格式、空文件、超限', () => {
    assert.match(validateFile(null), /请上传/);
    assert.match(validateFile({ name: 'a.txt', size: 10 }), /格式只支持/);
    assert.match(validateFile({ name: 'a.jpg', size: 0 }), /是空的/);
    assert.match(validateFile({ name: 'a.jpg', size: CONFIG.MAX_IMAGE_BYTES + 1 }), /不能超过/);
    assert.equal(validateFile({ name: 'a.jpg', size: 1024 }), null);
    assert.equal(validateFile({ name: 'a.PNG', size: 1024 }), null);
});
