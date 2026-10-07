/* 导出引擎：合并语义、表头结构、文档装配。
 *
 * 这一层不重跑对拍闸门（那是 Python 侧 `tools/compare_report_with_sample.py --expected` 的职责），
 * 只锁"引擎自己的结构决策"——尤其是**两类纵向合并粒度不同**这个最容易做错的地方。
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import JSZip from 'jszip';

import { CONFIG } from '../app/config.js';
import { SPEC } from '../app/report/spec.js';
import { buildDetectionTable, dataRowHeight, flattenRows, headerRows, infoLines, renderDocx }
    from '../app/report/engine.js';

const BASE_DOCX = new Uint8Array(
    readFileSync(new URL('../../webapp/resources/report_base.docx', import.meta.url)));

const CLAUSE_A = '立柱铝型材开口部位的厚度不应小于3.0mm';
const CLAUSE_B = '立柱铝型材闭合部位的厚度不应小于2.5mm';

function member(floor, position, clause, faces) {
    return {
        record: { floor, member_position: position, size_result: '63×164', requirement_text: clause },
        faces: faces.map((face, index) => ({
            face, readings_text: ['2.99', '3.02', '3.01', '3.01', '2.99'], min_text: '2.99',
        })),
    };
}

/* --------------------------------------------------------------------------
 * 两类合并的粒度
 * ------------------------------------------------------------------------ */

test('立柱式：每构件 2 面、同一条文 → 楼层按构件合并，要求列跨全部构件合并一次', () => {
    const records = [
        member('六层', '1', CLAUSE_A, ['B', 'H']),
        member('六层', '2', CLAUSE_A, ['B', 'H']),
        member('二十三层', '3', CLAUSE_A, ['B', 'H']),
    ];
    const rows = flattenRows(records);

    assert.equal(rows.length, 6);
    assert.deepEqual(rows.map((row) => row.memberStartRow), [0, 0, 2, 2, 4, 4]);
    assert.deepEqual(rows.map((row) => row.memberFaceCount), [2, 2, 2, 2, 2, 2]);

    // 要求列：整表一条文 → 只在第 0 行起块，跨 6 行
    assert.deepEqual(rows.map((row) => row.requirementStart),
        [true, false, false, false, false, false]);
    assert.equal(rows[0].requirementSpan, 6);
});

test('横梁式：每构件 1 面、同一条文 → 前三列不合并；要求列仍跨 5 行合并', () => {
    const records = ['6', '7', '8', '9', '10'].map(
        (position) => member('六层', position, CLAUSE_B, ['t']));
    const rows = flattenRows(records);

    assert.equal(rows.length, 5);
    assert.deepEqual(rows.map((row) => row.memberFaceCount), [1, 1, 1, 1, 1]);
    assert.deepEqual(rows.map((row) => row.requirementStart),
        [true, false, false, false, false]);
    assert.equal(rows[0].requirementSpan, 5);
});

test('条文变化 → 要求列新起一块（不会错误地并入上一块）', () => {
    const records = [
        member('六层', '1', CLAUSE_A, ['B', 'H']),
        member('六层', '2', CLAUSE_B, ['B', 'H']),
        member('六层', '3', CLAUSE_B, ['B', 'H']),
    ];
    const rows = flattenRows(records);

    assert.deepEqual(rows.map((row) => row.requirementStart),
        [true, false, true, false, false, false]);
    assert.equal(rows[0].requirementSpan, 2);
    assert.equal(rows[2].requirementSpan, 4);
});

test('单行块不写纵向合并（span = null）', () => {
    const records = [member('六层', '1', CLAUSE_A, ['B']), member('六层', '2', CLAUSE_B, ['B'])];
    const rows = flattenRows(records);
    assert.deepEqual(rows.map((row) => row.requirementSpan), [null, null]);
    assert.deepEqual(rows.map((row) => row.requirementStart), [true, true]);
});

test('没有检测面的构件不产生行', () => {
    assert.deepEqual(flattenRows([member('六层', '1', CLAUSE_A, [])]), []);
    assert.deepEqual(flattenRows([]), []);
});

/* --------------------------------------------------------------------------
 * 表头与行高
 *
 * 断言走**生成的 XML**而不是 docx 库的对象内部结构：后者是库的实现细节
 * （`Table` 甚至没有 `.options`），断言它等于在测库；XML 才是交付物与闸门关心的东西。
 * ------------------------------------------------------------------------ */

/** 取出第一张表的每一行的 tc 个数与整段 XML，便于按行断言。 */
function firstTableRows(xml) {
    const table = /<w:tbl>[\s\S]*?<\/w:tbl>/.exec(xml);
    assert.ok(table, '生成的文档里应有表格');
    return (table[0].match(/<w:tr\b[\s\S]*?<\/w:tr>/g) ?? []).map((row) => ({
        xml: row,
        cells: (row.match(/<w:tc>/g) ?? []).length,
    }));
}

async function renderFixture(records, templateType = 'column') {
    const bytes = await renderDocx({ project_no: 'P', house_name: '示例' },
        [{ template_type: templateType, records }], { baseDocxBytes: BASE_DOCX });
    return (await (await JSZip.loadAsync(bytes)).file('word/document.xml').async('string'));
}

test('表头两行：第一行 5 格（厚度块跨 7 列）、第二行 7 个子表头', async () => {
    const xml = await renderFixture([member('六层', '1', CLAUSE_A, ['B', 'H'])]);
    const rows = firstTableRows(xml);

    assert.equal(rows[0].cells, 5, '表头第一行应是 5 个 tc（厚度块跨 7 列 → 减少 6 个）');
    assert.match(rows[0].xml, /<w:gridSpan w:val="7"\/>/);
    // 第一行前 3 格与末格纵向跨 2 行（restart），厚度块不跨行
    assert.equal((rows[0].xml.match(/<w:vMerge w:val="restart"\/>/g) ?? []).length, 4);

    assert.equal(rows[1].cells, 11, '表头第二行补齐 11 个 tc（3 个续格 + 7 个子表头 + 1 个续格）');
    for (const label of SPEC.headers.thicknessSub) {
        assert.ok(rows[1].xml.includes(`>${label}<`), `第二行应含子表头「${label}」`);
    }
});

test('行高按模板不同：立柱 522 / 横梁 567', async () => {
    assert.equal(dataRowHeight('column'), 522);
    assert.equal(dataRowHeight('beam'), 567);
    assert.equal(dataRowHeight('unknown'), SPEC.rows.dataHeightTwips);

    const column = firstTableRows(await renderFixture([member('六层', '1', CLAUSE_A, ['B'])]));
    assert.match(column[2].xml, /<w:trHeight w:val="522"\/>/);
    const beam = firstTableRows(await renderFixture(
        [member('六层', '6', CLAUSE_B, ['t'])], 'beam'));
    assert.match(beam[2].xml, /<w:trHeight w:val="567"\/>/);
});

test('信息段：5 行「标签：值」，空值留空', () => {
    const lines = infoLines({ project_no: 'A06YG', house_name: '示例', house_address: '',
        client_org: '', test_date: '' });
    assert.equal(lines.length, CONFIG.PROJECT_INFO_FIELDS.length);
    assert.equal(lines[0], '项目编号：A06YG');
    assert.equal(lines[2], '房屋地点：');
});

/* --------------------------------------------------------------------------
 * 装配与后处理
 * ------------------------------------------------------------------------ */

test('renderDocx 产出可用的 docx（含底座替换的 styles / theme）', async () => {
    const groups = [{ template_type: 'column', records: [member('六层', '1', CLAUSE_A, ['B', 'H'])] }];
    const bytes = await renderDocx({ project_no: 'P', house_name: '示例' }, groups,
        { baseDocxBytes: BASE_DOCX });

    const zip = await JSZip.loadAsync(bytes);
    for (const part of ['word/document.xml', 'word/styles.xml', 'word/theme/theme1.xml']) {
        assert.ok(zip.file(part), `缺少 ${part}`);
    }

    const xml = await zip.file('word/document.xml').async('string');
    // 补丁生效的标志：docGrid 是规格值、行有 jc、vMerge 不带 val、边框带 space
    assert.match(xml, /w:linePitch="312"/);
    assert.match(xml, /<w:trPr><w:trHeight w:val="567"\/><w:jc w:val="center"\/><\/w:trPr>/);
    assert.ok(!/w:val="continue"/.test(xml), 'vMerge 的 val="continue" 应被归一掉');
    assert.match(xml, /<w:top w:val="single" w:color="000000" w:sz="12" w:space="0"\/>/);
    assert.match(xml, /<w:cols w:space="720"\/>/);

    const styles = await zip.file('word/styles.xml').async('string');
    assert.match(styles, /w:eastAsiaTheme="minorEastAsia"/, 'styles 应来自底座模板');
});

test('表格行数 = 表头 2 + 检测面数，列宽等于规格', async () => {
    const group = {
        template_type: 'column',
        records: [member('六层', '1', CLAUSE_A, ['B', 'H']), member('六层', '2', CLAUSE_A, ['B'])],
    };
    const table = buildDetectionTable(group);
    // 库的 Table 没有 .options：root = [TableProperties, TableGrid, ...TableRow]
    const rowComponents = table.root.filter((node) => node.constructor.name === 'TableRow');
    assert.equal(rowComponents.length, 2 + 3);

    const xml = await renderFixture(group.records);
    const grid = [...xml.matchAll(/<w:gridCol w:w="(\d+)"\/>/g)].map((m) => Number(m[1]));
    assert.deepEqual(grid, [...SPEC.columns.widths]);
});
