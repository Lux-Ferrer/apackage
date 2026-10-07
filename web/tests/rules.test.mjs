/* 厚度读数纯函数 + 生成资产与真相源同步。
 * 断言对应 Python 侧的 `tests/test_thickness.py`。
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import {
    countReadings, faceMin, faceMinText, faceMinTextOfValid, formatMm, normalizeValue,
    readingState, readingsOfRow,
} from '../app/thickness.js';
import { SPEC } from '../app/report/spec.js';

/* --------------------------------------------------------------------------
 * 最小值（对应 test_thickness.py）
 * ------------------------------------------------------------------------ */

test('最小值：保留两位小数', () => {
    assert.equal(faceMin([2.14, 2.12, 2.11, 2.10, 2.10]).toFixed(2), '2.10');
    assert.equal(faceMinText([2.14, 2.12, 2.11, 2.10, 2.10]), '2.10');
    assert.equal(faceMinText([2.15, 2.12, 2.18, 2.19, 2.15]), '2.12');
    assert.equal(faceMinText([2.99, 3.02, 3.01, 3.01, 2.99]), '2.99');
});

test('最小值：接受字符串形式的读数', () => {
    assert.equal(faceMinText(['2.99', '3.02', '3.01', '3.01', '2.99']), '2.99');
    assert.equal(faceMin(['2.5', ' 2.4 ']), 2.4);
});

test('最小值：忽略空值占位符', () => {
    assert.equal(faceMin([2.5, null, '', '-', '/']), 2.5);
    assert.equal(faceMinText([null, 3.0, '']), '3.00');
    assert.equal(faceMin([null, '', '-']), null);
    assert.equal(faceMin([]), null);
    assert.equal(faceMinText([null]), '');
});

test('最小值：支持负值（样例里有 -0.01）', () => {
    assert.equal(faceMinText([2.00, 2.00, 2.00, 2.00, -0.01]), '-0.01');
});

test('无法识别的值抛错（严格版）', () => {
    assert.throws(() => faceMin(['abc']));
    assert.throws(() => normalizeValue(true));
});

test('容错版：跳过非法值，只按有效读数算（表单回填用）', () => {
    assert.equal(faceMinTextOfValid(['abc', '2.50', '', '3.00']), '2.50');
    assert.equal(faceMinTextOfValid(['abc', 'def']), '');
    assert.equal(faceMinTextOfValid(['2.99', '3.02']), '2.99');
    assert.throws(() => faceMin(['abc', '2.50']));
});

test('格式化：两位小数，None → 空串', () => {
    assert.equal(formatMm(2.1), '2.10');
    assert.equal(formatMm(-0.01), '-0.01');
    assert.equal(formatMm(3), '3.00');
    assert.equal(formatMm(null), '');
});

test('readingsOfRow 取出 value_1..value_5', () => {
    const row = { value_1: 2.14, value_2: 2.12, value_3: 2.11, value_4: 2.10, value_5: 2.10 };
    assert.deepEqual(readingsOfRow(row), [2.14, 2.12, 2.11, 2.10, 2.10]);
    assert.equal(faceMinText(readingsOfRow(row)), '2.10');
});

/* --------------------------------------------------------------------------
 * 读数状态：三态着色（完整度）与警告灯（有效性）两个通道的数据
 * ------------------------------------------------------------------------ */

test('读数状态三分类', () => {
    assert.equal(readingState(''), 'empty');
    assert.equal(readingState('  '), 'empty');
    assert.equal(readingState(null), 'empty');
    assert.equal(readingState('-'), 'empty');
    assert.equal(readingState('2.99'), 'valid');
    assert.equal(readingState(2.99), 'valid');
    assert.equal(readingState('abc'), 'invalid');
});

test('有效/非法个数分开统计', () => {
    assert.deepEqual(countReadings(['2.1', '', 'abc', '2.3', null]), [2, 1]);
    assert.deepEqual(countReadings(['abc', 'def', '', '', '']), [0, 2]);
    assert.deepEqual(countReadings(['', '', '', '', '']), [0, 0]);
    assert.deepEqual(countReadings(['1', '2', '3', '4', '5']), [5, 0]);
});

/* --------------------------------------------------------------------------
 * 生成资产必须与真相源一致（防止改了 Python 侧忘了重新生成）
 * ------------------------------------------------------------------------ */

test('web/app/report/spec.js 与 web/assets/report_layout.json 逐键一致', () => {
    const raw = JSON.parse(readFileSync(new URL('../assets/report_layout.json', import.meta.url), 'utf8'));
    assert.deepEqual(SPEC, raw);
});

test('spec 里的关键版式常量符合预期（与 Python 侧同一份数值）', () => {
    assert.equal(SPEC.page.widthTwips, 11907);
    assert.equal(SPEC.page.heightTwips, 16839);
    assert.equal(SPEC.page.marginTwips, 1440);
    assert.equal(SPEC.page.marginBottomTwips, 1843);
    assert.equal(SPEC.page.marginHorizontalTwips, 907);
    assert.equal(SPEC.page.headerFooterTwips, 850);
    assert.equal(SPEC.page.docGridLinePitch, 312);
    assert.equal(SPEC.table.widthTwips, 10833);
    assert.equal(SPEC.columns.widths.length, 11);
    assert.equal(SPEC.columns.widths.reduce((sum, value) => sum + value, 0), SPEC.table.widthTwips);
});
