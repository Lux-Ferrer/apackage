/* 前端功能测试：在 jsdom 里加载真实的 record_form.js，验证
 *
 *   1. 5 个读数的实时最小值计算（忽略空值与非数字、保留两位小数、支持负值）
 *   2. 最小值高亮落在正确的输入框上
 *   3. 非法读数（非空且非数字）：就地提示「请填数字」+ 保存按钮禁用 + 拦截提交
 *   4. 检测面行的新增（字段下标正确）与删除（至少 1 行、最多 6 行）
 *   5. UI 改造新增：摘要行三态着色 / 进度 N/5 / 折叠态警告灯 / 名称同步 /
 *      点保存被拦截时展开非法行
 *
 * 运行（项目根目录，需要 Node.js）：
 *
 *     npm install --no-save jsdom      # 仅首次
 *     node tests/js/record_form.test.js
 *
 * 这是可选测试：Python 测试套件（pytest）不依赖它。
 *
 * 注意夹具的"契约冻结"：id / name / class 与 input.parentNode 内必须有
 * .input-hint 这两条结构约束都不能变，否则 record_form.js 与断言会一起失效。
 * 详见 docs/management/UI-设计.md 第 5.2 节。
 */
const fs = require('fs');
const path = require('path');

let JSDOM;
let VirtualConsole;
try {
    ({ JSDOM, VirtualConsole } = require('jsdom'));
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

/* 每个读数是 <label class="reading-cell"> 包住 input + .input-hint ——
   record_form.js 用 input.parentNode.querySelector('.input-hint') 找提示 */
function readingCells(index) {
    let cells = '';
    for (let position = 1; position <= VALUE_COUNT; position += 1) {
        cells += `<label class="reading-cell"><span class="reading-label">${position}</span>`
            + `<input type="text" class="reading" name="value_${index}_${position}" value="">`
            + '<span class="input-hint">请填数字</span></label>';
    }
    return cells;
}

function faceRow(index, face, open) {
    return `<li><details class="face-row" data-index="${index}"${open ? ' open' : ''}>
        <summary class="face-summary">
            <span class="face-dot state-none"></span>
            <span class="face-name">${face || '新检测面'}</span>
            <span class="face-count">0/${VALUE_COUNT}</span>
            <span class="face-min">最小 <b class="min-value">—</b></span>
            <span class="face-lamp" hidden>⚠ <span class="lamp-count">0</span> 格不是数字</span>
        </summary>
        <div class="face-editor">
            <label class="face-field">检测面
                <input type="text" class="face-input" name="face_${index}" value="${face || ''}"></label>
            <div class="reading-grid">${readingCells(index)}</div>
            <div class="face-editor-foot">
                <span class="hint">最小值自动计算</span>
                <button type="button" class="row-remove">删除这个检测面</button>
            </div>
        </div>
    </details></li>`;
}

/* 模板行用 __INDEX__ 占位，与后端 records/form.html 的 <template> 保持一致 */
function templateRow() {
    let cells = '';
    for (let position = 1; position <= VALUE_COUNT; position += 1) {
        cells += `<label class="reading-cell"><span class="reading-label">${position}</span>`
            + `<input type="text" class="reading" name="value___INDEX___${position}" value="">`
            + '<span class="input-hint">请填数字</span></label>';
    }
    return `<li><details class="face-row" data-index="__INDEX__" open>
        <summary class="face-summary">
            <span class="face-dot state-none"></span>
            <span class="face-name">新检测面</span>
            <span class="face-count">0/${VALUE_COUNT}</span>
            <span class="face-min">最小 <b class="min-value">—</b></span>
            <span class="face-lamp" hidden>⚠ <span class="lamp-count">0</span> 格不是数字</span>
        </summary>
        <div class="face-editor">
            <label class="face-field">检测面
                <input type="text" class="face-input" name="face___INDEX__" value=""></label>
            <div class="reading-grid">${cells}</div>
            <div class="face-editor-foot">
                <span class="hint">最小值自动计算</span>
                <button type="button" class="row-remove">删除这个检测面</button>
            </div>
        </div>
    </details></li>`;
}

const html = `<!doctype html><html><body>
<form id="record-form" method="post" action="/projects/1/records/">
    <ol id="face-list" data-value-count="${VALUE_COUNT}" data-face-max="${FACE_MAX}">
        ${faceRow(0, 'B', true)}
    </ol>
    <button type="button" id="add-face">+ 添加检测面</button>
    <span id="face-hint">最多 ${FACE_MAX} 个检测面</span>
    <datalist id="face-suggestions"><option value="B"></option><option value="H"></option></datalist>
</form>
<div class="action-bar">
    <p class="form-status" id="form-status" role="status"></p>
    <button type="submit" id="save-record" form="record-form">保存</button>
</div>
<template id="face-row-template">${templateRow()}</template>
</body></html>`;

/* jsdom 未实现表单导航，屏蔽该噪音日志 */
const virtualConsole = new VirtualConsole();
virtualConsole.on('jsdomError', function (error) {
    if (String(error && error.message).indexOf('Not implemented') === 0) return;
    console.error(error && error.message);
});

const dom = new JSDOM(html, { runScripts: 'outside-only', virtualConsole });
const { window } = dom;
window.eval(SCRIPT);

const document = window.document;
const form = document.getElementById('record-form');
const list = document.getElementById('face-list');
const addButton = document.getElementById('add-face');
const hint = document.getElementById('face-hint');
const saveButton = document.getElementById('save-record');
const formStatus = document.getElementById('form-status');

function rows() {
    return Array.from(list.querySelectorAll('details.face-row'));
}
function readingInputs(row) {
    return Array.from(row.querySelectorAll('input.reading'));
}
function minText(row) {
    return row.querySelector('.min-value').textContent;
}
function inputHint(input) {
    return input.parentNode.querySelector('.input-hint');
}
function faceState(row) {
    const dot = row.querySelector('.face-dot');
    return ['state-none', 'state-partial', 'state-done'].filter(function (name) {
        return dot.classList.contains(name);
    })[0];
}
function faceCount(row) {
    return row.querySelector('.face-count').textContent;
}
function lampVisible(row) {
    return !row.querySelector('.face-lamp').hidden;
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
function submitForm() {
    const event = new window.Event('submit', { bubbles: true, cancelable: true });
    form.dispatchEvent(event);
    return event.defaultPrevented;
}

// --------------------------------------------------------------------------
// 1) 实时最小值
// --------------------------------------------------------------------------
check('初始最小值显示为 —', minText(rows()[0]) === '—', minText(rows()[0]));

type(rows()[0], ['2.14', '2.12', '2.11', '2.10', '2.10']);
check('5 个读数实时算出最小值 2.10', minText(rows()[0]) === '2.10', minText(rows()[0]));

const highlighted = readingInputs(rows()[0]).filter(function (input) {
    return input.classList.contains('is-min');
});
check('最小值高亮（2 个并列 2.10）', highlighted.length === 2, '高亮 ' + highlighted.length + ' 个');

type(rows()[0], ['', '', '3.01', '', '']);
check('空值被忽略，最小值为 3.01', minText(rows()[0]) === '3.01', minText(rows()[0]));

type(rows()[0], ['2.00', '2.00', '2.00', '2.00', '-0.01']);
check('负值参与计算（结果 -0.01）', minText(rows()[0]) === '-0.01', minText(rows()[0]));

type(rows()[0], ['', '', '', '', '']);
check('全部清空后回到 —', minText(rows()[0]) === '—', minText(rows()[0]));

// --------------------------------------------------------------------------
// 2) 非法读数：就地提示 + 禁用保存 + 拦截提交
// --------------------------------------------------------------------------
const row0 = rows()[0];
const firstInput = readingInputs(row0)[0];

type(row0, ['wwww', '2.5', '', '', '']);
check('非法输入被标红', firstInput.classList.contains('is-invalid'));
check('非法输入就地显示「请填数字」', inputHint(firstInput).classList.contains('show'));
check('同一行其它格不显示提示',
    !inputHint(readingInputs(row0)[1]).classList.contains('show'));
check('最小值仍按有效值计算（2.50）', minText(row0) === '2.50', minText(row0));

check('保存按钮被禁用', saveButton.disabled === true);
check('整体提示可见且写明数量',
    formStatus.classList.contains('show') && formStatus.textContent.indexOf('1 个') >= 0,
    formStatus.textContent);
check('非法状态下提交被拦截', submitForm() === true);

type(row0, ['2.5', '2.5', '', '', '']);
check('修正后保存按钮恢复可用', saveButton.disabled === false);
check('修正后提示消失', !formStatus.classList.contains('show'));
check('修正后就地提示消失', !inputHint(firstInput).classList.contains('show'));
check('全部合法时提交不被拦截', submitForm() === false);

type(row0, ['2.5', 'abc', 'def', '', '']);
check('多个非法输入时提示数量正确',
    formStatus.textContent.indexOf('2 个') >= 0, formStatus.textContent);

type(row0, ['', '', '', '', '']);
check('清空后仍是合法状态（空值允许）', saveButton.disabled === false);

// --------------------------------------------------------------------------
// 3) 行增删
// --------------------------------------------------------------------------
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
check('新行也带「请填数字」提示元素', !!inputHint(readingInputs(newRow)[0]));

type(newRow, ['2.55', '2.52', '2.52', '2.53', '2.53']);
check('新增行实时最小值 2.52', minText(newRow) === '2.52', minText(newRow));

type(newRow, ['x', '', '', '', '']);
check('新行的非法输入同样禁用保存', saveButton.disabled === true);
type(newRow, ['', '', '', '', '']);
check('清掉新增行的非法值后恢复可用', saveButton.disabled === false);

// 上限
while (rows().length < FACE_MAX) { click(addButton); }
check('可以加到 6 行', rows().length === FACE_MAX, rows().length + ' 行');
check('到上限后按钮禁用', addButton.disabled === true);
check('到上限后提示更新', hint.textContent.indexOf('上限') >= 0, hint.textContent);

// 删除
click(rows()[5].querySelector('.row-remove'));
click(rows()[4].querySelector('.row-remove'));
check('删除行后行数减少', rows().length === FACE_MAX - 2, rows().length + ' 行');
check('删除后按钮重新可用', addButton.disabled === false);

while (rows().length > 1) { click(rows()[rows().length - 1].querySelector('.row-remove')); }
check('可以删到只剩 1 行', rows().length === 1, rows().length + ' 行');
click(rows()[0].querySelector('.row-remove'));
check('最后一行删不掉', rows().length === 1, rows().length + ' 行');
check('给出至少保留 1 行的提示', hint.textContent.indexOf('至少保留') >= 0, hint.textContent);

// --------------------------------------------------------------------------
// 4) UI 改造：摘要行的三态着色 / 进度 / 警告灯 / 名称同步
// --------------------------------------------------------------------------
const soloRow = rows()[0];
type(soloRow, ['', '', '', '', '']);
check('未填时圆点是 state-none', faceState(soloRow) === 'state-none', faceState(soloRow));
check('未填时进度显示 0/5', faceCount(soloRow) === '0/5', faceCount(soloRow));
check('未填时不显示警告灯', lampVisible(soloRow) === false);

type(soloRow, ['2.10', '2.20', '', '', '']);
check('填了 2 格 → state-partial', faceState(soloRow) === 'state-partial', faceState(soloRow));
check('进度显示 2/5', faceCount(soloRow) === '2/5', faceCount(soloRow));

type(soloRow, ['2.10', '2.20', '2.30', '2.40', '2.50']);
check('填满 5 格 → state-done', faceState(soloRow) === 'state-done', faceState(soloRow));
check('进度显示 5/5', faceCount(soloRow) === '5/5', faceCount(soloRow));

// 关键：完整度与有效性是两个独立通道 —— 5 格全填 abc 是"未填 + 警告灯"，不是"完成"
type(soloRow, ['abc', 'def', 'ghi', 'jkl', 'mno']);
check('5 格都是非法值时圆点回到 state-none（不伪装成完成）',
    faceState(soloRow) === 'state-none', faceState(soloRow));
check('5 格都是非法值时警告灯亮起', lampVisible(soloRow) === true);
check('警告灯写明非法格数（折叠态也看得见）',
    soloRow.querySelector('.lamp-count').textContent === '5',
    soloRow.querySelector('.lamp-count').textContent);
check('最小值仍按有效值算（全非法 → —）', minText(soloRow) === '—', minText(soloRow));

type(soloRow, ['2.10', 'abc', '', '', '']);
check('部分非法时进度只算有效格（1/5）', faceCount(soloRow) === '1/5', faceCount(soloRow));
check('部分非法时警告灯计数为 1',
    soloRow.querySelector('.lamp-count').textContent === '1',
    soloRow.querySelector('.lamp-count').textContent);

// 检测面名称同步到摘要行
const nameInput = soloRow.querySelector('input.face-input');
nameInput.value = 'H';
nameInput.dispatchEvent(new window.Event('input', { bubbles: true }));
check('摘要行名称跟随检测面输入', soloRow.querySelector('.face-name').textContent === 'H',
    soloRow.querySelector('.face-name').textContent);
nameInput.value = '  ';
nameInput.dispatchEvent(new window.Event('input', { bubbles: true }));
check('名称清空后回落为「新检测面」',
    soloRow.querySelector('.face-name').textContent === '新检测面',
    soloRow.querySelector('.face-name').textContent);

// --------------------------------------------------------------------------
// 5) 自动展开：输入时不打扰，点保存被拦截时才展开非法行
// --------------------------------------------------------------------------
type(soloRow, ['abc', '', '', '', '']);
check('整理成合法状态前，保存被拦截', submitForm() === true);
check('提交被拦截时展开含非法读数的行', soloRow.open === true);

click(addButton);
const addedRow = rows()[1];
check('新增的行默认展开', addedRow.open === true, String(addedRow.open));
type(addedRow, ['xyz', '', '', '', '']);
check('新行非法时不自动收起（不打断输入）', addedRow.open === true);

// 折叠起来再触发保存：应当被重新展开并聚焦第一个非法输入
// （先把第一行清干净，这样"第一个非法输入"只可能是新增行的）
type(soloRow, ['', '', '', '', '']);
addedRow.open = false;
check('折叠状态下也存在非法值', saveButton.disabled === true);
submitForm();
check('保存被拦截时把折叠的非法行重新展开', addedRow.open === true, String(addedRow.open));
check('焦点落在第一个非法输入上',
    document.activeElement === readingInputs(addedRow)[0],
    document.activeElement ? document.activeElement.name : '(none)');

type(addedRow, ['', '', '', '', '']);
check('全部清空后提交不再被拦截', submitForm() === false);

console.log('');
const passed = results.filter(Boolean).length;
console.log('前端 JS 测试：' + passed + '/' + results.length + ' 通过');
process.exit(passed === results.length ? 0 : 1);
