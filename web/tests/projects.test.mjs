/* 项目读写：校验、CRUD、列表统计、删除影响面。
 * 断言对应 Python 侧的 `tests/test_projects.py` 里的**数据层**部分（路由层不在此范围）。
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { STORE } from '../app/db.js';
import { freshDb, makeDefect, makeProject, makeRecord, projects } from './helpers.mjs';

/* --------------------------------------------------------------------------
 * 表单解析
 * ------------------------------------------------------------------------ */

test('必填字段缺失时逐字段报错', () => {
    const { errors } = projects.parseForm({ project_no: '', house_name: '  ' });
    assert.equal(errors.project_no, '项目编号不能为空');
    assert.equal(errors.house_name, '房屋名称不能为空');
});

test('选填字段可以留空（存 null）', () => {
    const { data, errors } = projects.parseForm({
        project_no: 'P1', house_name: '某楼',
        house_address: '', client_org: '   ', test_date: '',
    });
    assert.deepEqual(errors, {});
    assert.equal(data.house_address, null);
    assert.equal(data.client_org, null);
    assert.equal(data.test_date, null);
});

test('日期格式非法被拒', () => {
    assert.equal(projects.parseForm({ project_no: 'P1', house_name: 'A', test_date: '2026/09/20' })
        .errors.test_date, '检测日期格式应为 YYYY-MM-DD');
    assert.equal(projects.parseForm({ project_no: 'P1', house_name: 'A', test_date: '2026-02-30' })
        .errors.test_date, '检测日期格式应为 YYYY-MM-DD');
    assert.deepEqual(projects.parseForm({ project_no: 'P1', house_name: 'A', test_date: '2026-09-20' })
        .errors, {});
});

test('超长项目编号被拒（带字段名与上限）', () => {
    const { errors } = projects.parseForm({ project_no: 'X'.repeat(51), house_name: 'A' });
    assert.equal(errors.project_no, '项目编号不能超过 50 个字符');
});

/* --------------------------------------------------------------------------
 * CRUD
 * ------------------------------------------------------------------------ */

test('创建后可读回，且列表倒序（后建的在前）', async () => {
    const db = await freshDb();
    const first = await makeProject(db, { project_no: 'P-1', house_name: '一号楼' });
    const second = await makeProject(db, { project_no: 'P-2', house_name: '二号楼' });

    const project = await projects.get(db, first);
    assert.equal(project.house_name, '一号楼');

    const list = await projects.listWithCounts(db);
    assert.deepEqual(list.map((row) => row.id), [second, first]);
    assert.ok(list[0].created_at && list[0].updated_at);
    db.close();
});

test('列表带立柱/横梁记录数', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    await makeRecord(db, projectId, {}, 'column');
    await makeRecord(db, projectId, { member_position: '2' }, 'column');
    await makeRecord(db, projectId, { face_0: 't', member_position: '6' }, 'beam');

    const [row] = await projects.listWithCounts(db);
    assert.equal(row.column_count, 2);
    assert.equal(row.beam_count, 1);
    db.close();
});

test('重复项目编号 → IntegrityError，且原记录不变', async () => {
    const db = await freshDb();
    await makeProject(db, { project_no: 'JCZG' });
    await assert.rejects(
        () => projects.create(db, { project_no: 'JCZG', house_name: '重复' }),
        (error) => error.name === 'IntegrityError',
    );
    assert.equal((await projects.listWithCounts(db)).length, 1);
    db.close();
});

test('更新持久化改动，并保持编号唯一', async () => {
    const db = await freshDb();
    const first = await makeProject(db, { project_no: 'P-1', house_name: '旧名' });
    const second = await makeProject(db, { project_no: 'P-2', house_name: '二号楼' });

    const { data } = projects.parseForm({
        project_no: 'P-1', house_name: '新名', house_address: '深圳市南山区',
        client_org: '中冶', test_date: '2026-09-20',
    });
    await projects.update(db, first, data);

    const updated = await projects.get(db, first);
    assert.equal(updated.house_name, '新名');
    assert.equal(updated.house_address, '深圳市南山区');
    assert.equal(updated.test_date, '2026-09-20');

    await assert.rejects(
        () => projects.update(db, first, { ...data, project_no: 'P-2' }),
        (error) => error.name === 'IntegrityError' && /已被其他项目使用/.test(error.message),
    );
    assert.equal((await projects.get(db, second)).project_no, 'P-2');
    db.close();
});

test('更新不存在的项目 → LookupError', async () => {
    const db = await freshDb();
    await assert.rejects(() => projects.update(db, 999, { project_no: 'P', house_name: 'A' }),
        (error) => error.name === 'LookupError');
    db.close();
});

/* --------------------------------------------------------------------------
 * 删除影响面与确认文案
 * ------------------------------------------------------------------------ */

test('删除影响面：分类计数 + 关联报告数', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    await makeRecord(db, projectId, {}, 'column');
    await makeRecord(db, projectId, { member_position: '2' }, 'column');
    await makeRecord(db, projectId, { face_0: 't', member_position: '6' }, 'beam');
    await makeDefect(db, { project_id: `${projectId}` });
    await makeDefect(db, { project_id: `${projectId}` });

    const impact = await projects.deleteImpact(db, projectId);
    assert.deepEqual(impact, { column: 2, beam: 1, defects: 2, records: 3 });
    db.close();
});

test('删除确认文案写明记录影响面与"解除绑定并保留"', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db, { project_no: 'P-1', house_name: '某楼' });
    await makeRecord(db, projectId, {}, 'column');
    await makeDefect(db, { project_id: `${projectId}` });

    const project = await projects.get(db, projectId);
    const impact = await projects.deleteImpact(db, projectId);
    const message = projects.buildDeleteMessage(project, impact);

    assert.match(message, /确认删除项目「某楼（P-1）」/);
    assert.match(message, /将同时删除 1 条检测记录（立柱 1 条、横梁 0 条）/);
    assert.match(message, /关联的 1 份缺陷报告将解除绑定并保留/);
    db.close();
});

test('没有关联报告时文案说明这一点', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db, { project_no: 'P-1', house_name: '某楼' });
    const project = await projects.get(db, projectId);
    const message = projects.buildDeleteMessage(project, await projects.deleteImpact(db, projectId));
    assert.match(message, /该项目没有关联的缺陷报告/);
    db.close();
});

test('删除项目后：记录没了、报告还在且解绑、图片不受影响', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    await makeRecord(db, projectId);
    await db.write([STORE.images], (ctx) => ctx.put(STORE.images, { id: 'a.jpg' }));
    const defectId = await makeDefect(db, { project_id: `${projectId}` });

    await projects.remove(db, projectId);

    const reports = await db.read([STORE.defects], (ctx) => ctx.getAll(STORE.defects));
    assert.equal(reports.length, 1);
    assert.equal(reports[0].id, defectId);
    assert.equal(reports[0].project_id, null);
    assert.equal((await db.read([STORE.images], (ctx) => ctx.getAll(STORE.images))).length, 1);
    db.close();
});

/* --------------------------------------------------------------------------
 * 下拉选项
 * ------------------------------------------------------------------------ */

test('绑定项目下拉只给 id / 编号 / 名称，且倒序', async () => {
    const db = await freshDb();
    const first = await makeProject(db, { project_no: 'P-1', house_name: '一号楼' });
    const second = await makeProject(db, { project_no: 'P-2', house_name: '二号楼' });

    const options = await projects.listOptions(db);
    assert.deepEqual(options, [
        { id: second, project_no: 'P-2', house_name: '二号楼' },
        { id: first, project_no: 'P-1', house_name: '一号楼' },
    ]);
    db.close();
});
