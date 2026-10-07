/* 检测记录读写：解析、事务化增删改、分组读取。
 * 断言对应 Python 侧的 `tests/test_measurements.py` 数据层部分。
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { STORE } from '../app/db.js';
import { normalizeClause, normalizeSizeResult, requirementIndexOf, resolveRequirement } from '../app/clauses.js';
import { freshDb, makeProject, makeRecord, measurements, recordForm } from './helpers.mjs';

/* --------------------------------------------------------------------------
 * 文本规则（对应 test_normalize_size_result* / test_normalize_clause / test_resolve_*）
 * ------------------------------------------------------------------------ */

test('尺寸结果：x / X / * 统一成 ×', () => {
    assert.equal(normalizeSizeResult('63x164'), '63×164');
    assert.equal(normalizeSizeResult('63X164'), '63×164');
    assert.equal(normalizeSizeResult('63*164'), '63×164');
    assert.equal(normalizeSizeResult('63＊164'), '63×164');
});

test('尺寸结果：两个数字之间的空白视作乘号（不粘连）', () => {
    assert.equal(normalizeSizeResult('63 164'), '63×164');
    assert.equal(normalizeSizeResult('63　164'), '63×164');
    assert.equal(normalizeSizeResult('2.5 3.0'), '2.5×3.0');
    // 需求报告里的写法要原样保留（只去空白）
    assert.equal(normalizeSizeResult('12 + 75'), '12+75');
    assert.equal(normalizeSizeResult('  '), null);
});

test('条文按序号解析，越界或空 → null', () => {
    assert.match(resolveRequirement('0', 'column'), /^立柱铝型材开口部位/);
    assert.equal(resolveRequirement('', 'column'), null);
    assert.equal(resolveRequirement('9', 'column'), null);
    assert.equal(resolveRequirement('abc', 'column'), null);
});

test('条文序号与文案可以往返', () => {
    for (const templateType of ['column', 'beam']) {
        const text = resolveRequirement('0', templateType);
        assert.equal(requirementIndexOf(text, templateType), 0);
        assert.equal(requirementIndexOf('不存在的条文', templateType), null);
    }
});

test('条文归一化：去空白、全角转半角、去首尾标点', () => {
    assert.equal(normalizeClause('立柱 不应小于 3.0mm，闭口'),
        '立柱不应小于3.0mm,闭口');
    assert.equal(normalizeClause('条文。'), '条文');
    assert.equal(normalizeClause(null), '');
});

/* --------------------------------------------------------------------------
 * 表单解析（对应 test_parse_*）
 * ------------------------------------------------------------------------ */

test('合法表单解析出 faces 与条文快照', () => {
    const { data, errors } = measurements.parseRecordForm(recordForm(), 'column');
    assert.deepEqual(errors, {});
    assert.equal(data.floor, '六层');
    assert.equal(data.member_position, '1');
    assert.equal(data.size_result, '63×164');
    assert.match(data.requirement_text, /^立柱铝型材/);
    assert.deepEqual(data.faces, [{
        face: 'B',
        values: [2.99, 3.02, 3.01, 3.01, 2.99],
    }]);
});

test('楼层与构件位置必填', () => {
    const { errors } = measurements.parseRecordForm(recordForm({ floor: ' ', member_position: '' }), 'column');
    assert.equal(errors.floor, '楼层不能为空');
    assert.equal(errors.member_position, '构件位置不能为空');
});

test('至少要有一个检测面', () => {
    const { errors } = measurements.parseRecordForm(
        recordForm({ face_0: '', value_0_1: '', value_0_2: '', value_0_3: '', value_0_4: '', value_0_5: '' }),
        'column');
    assert.match(errors.faces, /至少填写 1 个检测面/);
});

test('整行空白被跳过（加了一行没填不算错）', () => {
    const { data, errors } = measurements.parseRecordForm(
        recordForm({ face_1: '', value_1_1: '', value_1_2: '', value_1_3: '', value_1_4: '', value_1_5: '' }),
        'column');
    assert.deepEqual(errors, {});
    assert.equal(data.faces.length, 1);
});

test('填了读数却没填检测面 → 报该行错误', () => {
    const { errors } = measurements.parseRecordForm(recordForm({ face_0: '', value_0_1: '2.99' }), 'column');
    assert.equal(errors.face_0, '这一行填了厚度读数，请同时填写检测面');
});

test('检测面重复 → 报该行错误', () => {
    const { errors } = measurements.parseRecordForm(
        recordForm({ face_1: 'B', value_1_1: '3.00' }), 'column');
    assert.equal(errors.face_1, '检测面「B」在本记录中重复');
});

test('非数字读数 → 逐格报错，其余读数照常解析', () => {
    const { data, errors } = measurements.parseRecordForm(
        recordForm({ value_0_3: 'abc' }), 'column');
    assert.equal(errors.value_0_3, '厚度读数必须是数字');
    assert.deepEqual(data.faces[0].values, [2.99, 3.02, null, 3.01, 2.99]);
});

test('超过 face_max 的行被忽略（服务端只认固定下标范围）', () => {
    const { data, errors } = measurements.parseRecordForm(
        recordForm({ face_1: 'H', value_1_1: '2.55', face_9: 'X', value_9_1: '1.00' }),
        'column');
    assert.deepEqual(errors, {});
    assert.deepEqual(data.faces.map((face) => face.face), ['B', 'H']);
});

test('未知模板类型 → 抛错', () => {
    assert.throws(() => measurements.parseRecordForm(recordForm(), 'glass'), /未知模板类型/);
});

/* --------------------------------------------------------------------------
 * 写入（对应 test_create_record_* / test_update_record_* / test_delete_record_*）
 * ------------------------------------------------------------------------ */

test('创建记录：记录 + 读数都落地，最小值可现算', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    const recordId = await makeRecord(db, projectId);

    const record = await measurements.getRecord(db, recordId);
    assert.equal(record.project_id, projectId);
    assert.equal(record.template_type, 'column');
    assert.equal(record.size_result, '63×164');
    assert.equal(record.sort_order, 0);

    const faces = (await measurements.groupedByTemplate(db, projectId))
        .find((group) => group.template_type === 'column').records[0].faces;
    assert.deepEqual(faces[0].readings_text, ['2.99', '3.02', '3.01', '3.01', '2.99']);
    assert.equal(faces[0].min_text, '2.99');
    db.close();
});

test('sort_order 逐条递增（同一项目内）', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    const first = await makeRecord(db, projectId, { member_position: '1' });
    const second = await makeRecord(db, projectId, { member_position: '2' });
    const third = await makeRecord(db, projectId, { member_position: '3' });

    assert.equal((await measurements.getRecord(db, first)).sort_order, 0);
    assert.equal((await measurements.getRecord(db, second)).sort_order, 1);
    assert.equal((await measurements.getRecord(db, third)).sort_order, 2);
    db.close();
});

test('另一个项目的 sort_order 从 0 重新开始', async () => {
    const db = await freshDb();
    const firstProject = await makeProject(db, { project_no: 'P-1' });
    const secondProject = await makeProject(db, { project_no: 'P-2' });
    await makeRecord(db, firstProject);
    const second = await makeRecord(db, secondProject);
    assert.equal((await measurements.getRecord(db, second)).sort_order, 0);
    db.close();
});

test('更新记录：读数整体替换', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    const recordId = await makeRecord(db, projectId);

    const { data } = measurements.parseRecordForm(recordForm({
        face_0: 'B', value_0_1: '2.10', value_0_2: '2.10', value_0_3: '2.10',
        value_0_4: '2.10', value_0_5: '2.10',
        face_1: 'H', value_1_1: '2.55', value_1_2: '2.52', value_1_3: '2.53',
        value_1_4: '2.53', value_1_5: '2.52',
    }), 'column');
    await measurements.updateRecord(db, recordId, data);

    const rows = await measurements.getReadings(db, recordId);
    assert.deepEqual(rows.map((row) => row.face), ['B', 'H']);
    assert.equal(rows[0].value_1, 2.10);
    assert.equal(rows[1].value_2, 2.52);
    db.close();
});

test('更新记录：template_type 永不改变（编辑锁定）', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    const recordId = await makeRecord(db, projectId, {}, 'column');

    const { data } = measurements.parseRecordForm(recordForm(), 'beam');
    await measurements.updateRecord(db, recordId, data);

    assert.equal((await measurements.getRecord(db, recordId)).template_type, 'column');
    db.close();
});

test('更新记录：读数写入失败则整体回滚，原读数保留', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    const recordId = await makeRecord(db, projectId);

    // 两个面同名 → 唯一索引冲突
    await assert.rejects(() => measurements.updateRecord(db, recordId, {
        floor: '七层', member_position: '9', size_result: '1×2', requirement_text: null,
        faces: [{ face: 'B', values: [1, 2, 3, 4, 5] }, { face: 'B', values: [1, 2, 3, 4, 5] }],
    }));

    const record = await measurements.getRecord(db, recordId);
    assert.equal(record.floor, '六层', '失败的更新不应改动记录');
    const rows = await measurements.getReadings(db, recordId);
    assert.equal(rows.length, 1);
    assert.equal(rows[0].value_1, 2.99, '原读数应保留');
    db.close();
});

test('更新不存在的记录 → LookupError', async () => {
    const db = await freshDb();
    await assert.rejects(() => measurements.updateRecord(db, 999, {
        floor: '六层', member_position: '1', faces: [{ face: 'B', values: [1] }],
    }), (error) => error.name === 'LookupError');
    db.close();
});

test('删除记录：读数级联删除；不存在 → LookupError', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    const recordId = await makeRecord(db, projectId);

    await measurements.deleteRecord(db, recordId);
    assert.equal(await measurements.getRecord(db, recordId), undefined);
    assert.equal((await db.read([STORE.readings], (ctx) => ctx.getAll(STORE.readings))).length, 0);

    await assert.rejects(() => measurements.deleteRecord(db, recordId),
        (error) => error.name === 'LookupError');
    db.close();
});

/* --------------------------------------------------------------------------
 * 分组读取（对应 test_grouped_by_template_*）
 * ------------------------------------------------------------------------ */

test('分组：立柱在前，带 count 与最小值', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    await makeRecord(db, projectId, { face_0: 't', member_position: '6' }, 'beam');
    await makeRecord(db, projectId, {}, 'column');

    const groups = await measurements.groupedByTemplate(db, projectId);
    assert.deepEqual(groups.map((group) => group.template_type), ['column', 'beam']);
    assert.equal(groups[0].count, 1);
    assert.equal(groups[1].count, 1);
    assert.equal(groups[0].records[0].faces[0].min_text, '2.99');
    assert.equal(groups[0].short_name, '立柱');
    assert.equal(groups[1].short_name, '横梁');
    db.close();
});

test('空项目：两个分组都在，count 为 0', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    const groups = await measurements.groupedByTemplate(db, projectId);
    assert.deepEqual(groups.map((group) => group.count), [0, 0]);
    assert.deepEqual(groups.map((group) => group.records), [[], []]);
    db.close();
});

test('分类计数与文案', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db);
    await makeRecord(db, projectId, {}, 'column');
    await makeRecord(db, projectId, { face_0: 't' }, 'beam');

    const counts = await measurements.countByTemplate(db, projectId);
    assert.deepEqual(counts, { column: 1, beam: 1 });
    assert.equal(measurements.describeCounts(counts), '立柱 1 条 · 横梁 1 条');
    db.close();
});
