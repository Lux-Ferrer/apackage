/* 数据层：库结构、约束、级联、事务纪律。
 *
 * 断言逐条对应 Python 侧的 `tests/test_db.py`（表/约束/级联语义），
 * 外加两条 IndexedDB 特有的检查（手写级联、事务回滚）。
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { IDBFactory } from 'fake-indexeddb';

import { Database, DB_VERSION, SchemaError, STORE } from '../app/db.js';
import { assertRiskLevel, parseForm as parseDefectForm } from '../app/repo/defects.js';
import { freshDb, makeDefect, makeProject, makeRecord, measurements, projects } from './helpers.mjs';

test('建库后有 4 个核心 store + images + meta', async () => {
    const db = await freshDb();
    const names = Array.from(db.idb.objectStoreNames);
    for (const store of ['projects', 'measurement_records', 'thickness_readings', 'defects']) {
        assert.ok(names.includes(store), `缺少 ${store}`);
    }
    assert.ok(names.includes('images'));
    assert.ok(names.includes('meta'));
    db.close();
});

test('不建范围外的 store（登录 / 速记）', async () => {
    const db = await freshDb();
    const names = Array.from(db.idb.objectStoreNames);
    assert.ok(!names.includes('users'));
    assert.ok(!names.includes('notes'));
    db.close();
});

test('meta 写入 schemaVersion', async () => {
    const db = await freshDb();
    assert.equal(await db.meta('schemaVersion'), DB_VERSION);
    db.close();
});

test('project_no 唯一约束', async () => {
    const db = await freshDb();
    await projects.create(db, { project_no: 'JCZG', house_name: '金骐智谷' });
    await assert.rejects(
        () => projects.create(db, { project_no: 'JCZG', house_name: '重复编号' }),
        (error) => error.name === 'IntegrityError' && /已存在/.test(error.message),
    );
    db.close();
});

test('template_type 只接受 column / beam', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    await assert.rejects(
        () => measurements.createRecord(db, projectId, 'glass', {
            floor: '六层', member_position: '1', size_result: null,
            requirement_text: null, faces: [{ face: 'B', values: [2.5] }],
        }),
        /未知模板类型/,
    );
    db.close();
});

test('risk_level 只接受 高 / 中 / 低（IndexedDB 没有 CHECK，靠代码校验）', async () => {
    const db = await freshDb();

    // 解析层拦住
    const { errors } = await parseDefectForm(db, {
        defect_type: '密封胶开裂', project_part: '东立面', risk_level: '紧急',
        rectification_plan: '重新打胶',
    });
    assert.equal(errors.risk_level, '隐患等级无效');

    // 写入层也拦住（导入路径不走 parseForm，也要经过这个校验）
    assert.throws(() => assertRiskLevel('紧急'), /隐患等级无效/);
    assert.doesNotThrow(() => assertRiskLevel('高'));
    db.close();
});

test('检测面接受自由文本（真实数据是 B / H / t，不做枚举）', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    for (const face of ['B', 'H', 't', '自定义面']) {
        await makeRecord(db, projectId, { face_0: face, member_position: face });
    }
    const readings = await db.read([STORE.readings], (ctx) => ctx.getAll(STORE.readings));
    assert.deepEqual(readings.map((row) => row.face).sort(), ['B', 'H', 't', '自定义面'].sort());
    db.close();
});

test('同一记录内检测面唯一，冲突时整条记录回滚', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);

    // 注意：**解析层已经会拦掉重复检测面**（parseRecordForm 报「在本记录中重复」），
    // 所以这里直接调 createRecord 绕过解析 —— 唯一索引是第二道防线（纵深防御），
    // 它保证"即使数据从别的路径进来（导入 / 将来的 API），也不会写坏"。
    const data = {
        floor: '六层',
        member_position: '1',
        size_result: null,
        requirement_text: null,
        faces: [
            { face: 'B', values: [2.99, null, null, null, null] },
            { face: 'B', values: [3.00, null, null, null, null] },
        ],
    };

    await assert.rejects(
        () => measurements.createRecord(db, projectId, 'column', data),
        (error) => /Constraint|约束/i.test(`${error.name} ${error.message}`),
    );

    // 关键：记录也一并回滚（对应 test_create_record_rolls_back_on_duplicate_face）
    const records = await db.read([STORE.records], (ctx) => ctx.getAll(STORE.records));
    const readings = await db.read([STORE.readings], (ctx) => ctx.getAll(STORE.readings));
    assert.equal(records.length, 0, '记录应随读数一起回滚');
    assert.equal(readings.length, 0);
    db.close();
});

test('解析层就挡住重复检测面（不必走到唯一索引）', () => {
    const { errors } = measurements.parseRecordForm({
        floor: '六层', member_position: '1',
        face_0: 'B', value_0_1: '2.99',
        face_1: 'B', value_1_1: '3.00',
    }, 'column');
    assert.equal(errors.face_1, '检测面「B」在本记录中重复');
});

test('读数允许留空（现场可能只测了部分点）', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    await makeRecord(db, projectId, { value_0_2: '', value_0_3: '', value_0_4: '', value_0_5: '' });
    const row = (await db.read([STORE.readings], (ctx) => ctx.getAll(STORE.readings)))[0];
    assert.equal(row.value_1, 2.99);
    assert.equal(row.value_5, null);
    db.close();
});

test('删除项目：检测记录与读数级联删除，缺陷报告保留且解除绑定', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    await makeRecord(db, projectId);
    await makeDefect(db, { project_id: `${projectId}` });

    const result = await projects.remove(db, projectId);

    assert.equal(result.records, 1);
    assert.equal(result.unboundDefects, 1);
    assert.equal((await db.read([STORE.records], (ctx) => ctx.getAll(STORE.records))).length, 0);
    assert.equal((await db.read([STORE.readings], (ctx) => ctx.getAll(STORE.readings))).length, 0);

    const report = (await db.read([STORE.defects], (ctx) => ctx.getAll(STORE.defects)))[0];
    assert.ok(report, '缺陷报告应保留');
    assert.equal(report.project_id, null, '关联应被置空');
    db.close();
});

test('删除不存在的项目 → LookupError', async () => {
    const db = await freshDb();
    await assert.rejects(() => projects.remove(db, 999),
        (error) => error.name === 'LookupError');
    db.close();
});

test('结构不完整时给出明确报错（对应 Python 的旧库检测）', async () => {
    const factory = new IDBFactory();
    const name = 'legacy_like';

    // 手搓一个"有库但没建 store"的旧库：版本相同 → 不会触发 upgradeneeded
    await new Promise((resolve, reject) => {
        const openRequest = factory.open(name, 1);
        openRequest.onupgradeneeded = () => { /* 什么都不建 */ };
        openRequest.onsuccess = () => { openRequest.result.close(); resolve(); };
        openRequest.onerror = () => reject(openRequest.error);
    });

    await assert.rejects(
        () => Database.open({ factory, name, version: 1 }),
        (error) => {
            assert.ok(error instanceof SchemaError);
            assert.match(error.message, /数据库结构不完整/);
            return true;
        },
    );
});

test('事务回滚：写入后抛错 → 全部不落地', async () => {
    const db = await freshDb();
    await assert.rejects(() => db.write([STORE.images], async (ctx) => {
        await ctx.put(STORE.images, { id: 'a.jpg', blob: null });
        throw new Error('故意失败');
    }), /故意失败/);

    const images = await db.read([STORE.images], (ctx) => ctx.getAll(STORE.images));
    assert.deepEqual(images, []);
    db.close();
});

test('跨 store 的事务：一个 store 失败 → 另一个也回滚', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    await assert.rejects(() => db.write([STORE.records, STORE.readings], async (ctx) => {
        await ctx.insert(STORE.records, {
            project_id: projectId, template_type: 'column',
            floor: '六层', member_position: '1', sort_order: 0,
        });
        // 读数缺 face → 唯一索引/结构不满足，事务应整体回滚
        await ctx.insert(STORE.readings, { record_id: 1, face: undefined });
        throw new Error('不可能走到这里');
    }));

    assert.equal((await db.read([STORE.records], (ctx) => ctx.getAll(STORE.records))).length, 0);
    db.close();
});
