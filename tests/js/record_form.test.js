/* 前端功能测试：在 jsdom 里加载真实的 record_form.js，验证
 *
 *   1. 5 个读数的实时最小值计算（忽略空值与非数字、保留两位小数、支持负值）
 *   2. 最小值高亮落在正确的输入框上；非法输入被标红
 *   3. 检测面行的新增（字段下标正确）与删除（至少 1 行、最多 6 行）
 *
 * 运行（项目根目录，需要 Node.js）：
 *
 *     npm install --no-save jsdom      # 仅首次
 *     node tests/js/record_form.test.js
 *
 * 这是可选测试：Python 测试套件（pytest）不依赖它。
 */
const fs = require('fs');
const path = require('path');

let JSDOM;
try {
    ({ JSDOM } = require('jsdom'));
} catch (error) {
    console.error('缺少 jsdom，请先执行：npm install --no-save jsdom');
    process.exit(2);
}

const SCRIPT_PATH = path.join(__dirname, '..', '..', 'webapp', 'static', 'js', 'record_form.js');
const SCRIPT = fs.readFileSync(SCRIPT_PATH, 'utf8');
const VALUE_COUNT = 5;
const FACE_MAX = 6;

const results = [];
function check(name, ok, detail) {
    results.push(ok);
    console.log((ok ? '  PASS  ' : '  FAIL  ') + name + (detail ? '  | ' + detail : ''));
}

function readingCells(index) {
    let cells = '';
    for (let position = 1; position <= VALUE_COUNT; position += 1) {
        cells += `<td><input type="text" class="reading" name="value_${index}_${position}" value=""></td>`;
    }
    return cells;
}

function faceRow(index, face) {
    return `<tr class="face-row">
        <td class="col-face"><input type="text" class="face-input" name="face_${index}" value="${face || ''}"></td>
        ${readingCells(index)}
        <td class="col-min"><span class="min-value">—</span></td>
        <td class="col-op"><button type="button" class="row-remove">✕</button></td>
    </tr>`;
}

/* 模板行用 __INDEX__ 占位，与后端 records/form.html 的 <template> 保持一致 */
function templateRow() {
    let cells = '';
    for (let position = 1; position <= VALUE_COUNT; position += 1) {
        cells += `<td><input type="text" class="reading" name="value___INDEX___${position}" value=""></td>`;
    }
    return `<tr class="face-row">
        <td class="col-face"><input type="text" class="face-input" name="face___INDEX__" value=""></td>
        ${cells}
        <td class="col-min"><span class="min-value">—</span></td>
        <td class="col-op"><button type="button" class="row-remove">✕</button></td>
    </tr>`;
}

const html = `<!doctype html><html><body>
<table id="face-table" data-value-count="${VALUE_COUNT}" data-face-max="${FACE_MAX}">
    <thead><tr><th>检测面</th><th>1</th><th>2</th><th>3</th><th>4</th><th>5</th><th>最小值</th><th></th></tr></thead>
    <tbody>${faceRow(0, 'B')}</tbody>
</table>
<button type="button" id="add-face">+ 添加检测面</button>
<span id="face-hint">最多 ${FACE_MAX} 个检测面</span>
<datalist id="face-suggestions"><option value="B"></option><option value="H"></option></datalist>
<template id="face-row-template">${templateRow()}</template>
</body></html>`;

const dom = new JSDOM(html, { runScripts: 'outside-only' });
const { window } = dom;
window.eval(SCRIPT);

const document = window.document;
const tbody = document.querySelector('#face-table tbody');
const addButton = document.getElementById('add-face');
const hint = document.getElementById('face-hint');

function rows() {
    return Array.from(tbody.querySelectorAll('tr.face-row'));
}
function readingInputs(row) {
    return Array.from(row.querySelectorAll('input.reading'));
}
function minText(row) {
    return row.querySelector('.min-value').textContent;
}
function type(row, values) {
    readingInputs(row).forEach(function (input, index) {
        input.value = values[index];
        input.dispatchEvent(new window.Event('input', { bubbles: true }));
    });
}
function click(element) {
    element.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
}

// 1) 初始化
check('初始最小值显示为 —', minText(rows()[0]) === '—', minText(rows()[0]));

// 2) 实时最小值：案例数据 横梁 六层 6（最小值 2.10）
type(rows()[0], ['2.14', '2.12', '2.11', '2.10', '2.10']);
check('5 个读数实时算出最小值 2.10', minText(rows()[0]) === '2.10', minText(rows()[0]));

// 3) 高亮落在正确的输入框上
const highlighted = readingInputs(rows()[0]).filter(function (input) {
    return input.classList.contains('is-min');
});
check('最小值高亮（2 个并列 2.10）', highlighted.length === 2, '高亮 ' + highlighted.length + ' 个');

// 4) 空值不参与计算
type(rows()[0], ['', '', '3.01', '', '']);
check('空值被忽略，最小值为 3.01', minText(rows()[0]) === '3.01', minText(rows()[0]));

// 5) 非数字被忽略并标红
type(rows()[0], ['abc', '2.5', '', '', '']);
check('非数字输入被标红', readingInputs(rows()[0])[0].classList.contains('is-invalid'));
check('非数字不参与最小值（结果 2.50）', minText(rows()[0]) === '2.50', minText(rows()[0]));

// 6) 全部清空回到 —
type(rows()[0], ['', '', '', '', '']);
check('全部清空后回到 —', minText(rows()[0]) === '—', minText(rows()[0]));

// 7) 负值（样例数据里有 -0.01）
type(rows()[0], ['2.00', '2.00', '2.00', '2.00', '-0.01']);
check('负值参与计算（结果 -0.01）', minText(rows()[0]) === '-0.01', minText(rows()[0]));

// 8) 新增行：字段下标递增且正确
click(addButton);
check('点击后新增一行', rows().length === 2, rows().length + ' 行');
const newRow = rows()[1];
check('新行面标签字段名为 face_1',
    newRow.querySelector('input.face-input').name === 'face_1',
    newRow.querySelector('input.face-input').name);
check('新行读数字段名为 value_1_1..value_1_5',
    readingInputs(newRow).map(function (input) { return input.name; }).join(',') ===
    'value_1_1,value_1_2,value_1_3,value_1_4,value_1_5',
    readingInputs(newRow).map(function (input) { return input.name; }).join(','));
check('新行最小值初始为 —', minText(newRow) === '—');

// 9) 新行同样具备实时计算
type(newRow, ['2.55', '2.52', '2.52', '2.53', '2.53']);
check('新增行实时最小值 2.52', minText(newRow) === '2.52', minText(newRow));

// 10) 加到上限后按钮禁用
while (rows().length < FACE_MAX) { click(addButton); }
check('可以加到 6 行', rows().length === FACE_MAX, rows().length + ' 行');
check('到上限后按钮禁用', addButton.disabled === true);
check('到上限后提示更新', hint.textContent.indexOf('上限') >= 0, hint.textContent);

// 11) 删除中间行后仍可继续添加
click(rows()[5].querySelector('.row-remove'));
click(rows()[4].querySelector('.row-remove'));
check('删除行后行数减少', rows().length === FACE_MAX - 2, rows().length + ' 行');
check('删除后按钮重新可用', addButton.disabled === false);

// 12) 至少保留 1 行
while (rows().length > 1) { click(rows()[rows().length - 1].querySelector('.row-remove')); }
check('可以删到只剩 1 行', rows().length === 1, rows().length + ' 行');
click(rows()[0].querySelector('.row-remove'));
check('最后一行删不掉', rows().length === 1, rows().length + ' 行');
check('给出至少保留 1 行的提示', hint.textContent.indexOf('至少保留') >= 0, hint.textContent);

console.log('');
const passed = results.filter(Boolean).length;
console.log('前端 JS 测试：' + passed + '/' + results.length + ' 通过');
process.exit(passed === results.length ? 0 : 1);
