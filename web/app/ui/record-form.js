/* 检测记录表单的交互：检测面增删 + 三态着色 + 警告灯 + 非法读数拦截 + 最小值预览。
 *
 * 移植自 `webapp/static/js/record_form.js`（UI 阶段定下的 5 条约定**一条不改**），
 * 三处因"从服务端渲染换成客户端渲染"而必须调整的地方，逐条说明：
 *
 * 1. **从 IIFE 变成 `attachRecordForm(root)`**：服务端渲染时页面加载即调用一次；
 *    客户端渲染时同一个页面可能被渲染多次（路由来回切），所以必须能被**重复挂载**、
 *    并且只作用于传进来的 `root`（不查全局 `document`）。这也让 jsdom 测试可以
 *    一个用例建一次 DOM，互不干扰。
 * 2. **行模板从 `<template>` + 字符串替换变成 `rowFactory(index)` 建节点**：
 *    字符串替换要维护一份 HTML 里的占位符，容易和 JS 走样；建节点还能顺手保证
 *    用户输入不会被当成 HTML。**冻结的契约是 name/class/结构，不是"怎么生成"**。
 * 3. **校验不再靠"服务端回填"**：客户端直接读表单 → `parseRecordForm()` → 就地标错。
 *    所以 `applyFieldErrors()` 是新增的，语义与 Jinja 的回填一致（标红 + 就地提示 + 展开出错行）。
 *
 * 五条约定（与 Flask 侧完全一致，改任何一条都要先改 `docs/management/UI-设计.md` 2.8）：
 * 1. 最小值只用于**即时预览**，不参与提交 —— 保存与导出时由数据层重算（前端算的值不被信任）；
 * 2. 行下标必须落在 0..face_max-1（数据层固定探测这个范围，不读"行数"字段）；
 * 3. 结构（开合、增删）交给原生 `<details>` 与 `rowFactory`；
 * 4. 任一读数"非空但不是数字"时：标红 + 就地提示 + **禁用保存** + 拦截提交；
 * 5. **完整度与有效性是两个独立通道**：圆点（三态）表示"还剩多少活"，警告灯表示"能不能保存"。
 */

import { h } from './dom.js';

/**
 * 挂载检测记录表单的交互。
 *
 * @param {Element} root 表单所在容器（必须有 `#face-list` / `#add-face` / `#save-record`）
 * @param {object} options
 *   valueCount  每个检测面的读数个数（默认读 `#face-list` 的 `data-value-count`）
 *   faceMax     最多几个检测面（默认读 `data-face-max`）
 *   rowFactory  `(index) => <li>` 造一行（必填；由视图提供，因为它要用到模板相关的文案）
 * @returns {{scan: Function, rows: Function, revealInvalid: Function, addRow: Function}}
 */
export function attachRecordForm(root, options = {}) {
    const list = root.querySelector('#face-list');
    if (!list) return null;

    const addButton = root.querySelector('#add-face');
    const hint = root.querySelector('#face-hint');
    const form = root.querySelector('#record-form');
    const saveButton = root.querySelector('#save-record');
    const formStatus = root.querySelector('#form-status');
    const requirementSelect = root.querySelector('#requirement_index');
    const requirementFull = root.querySelector('#requirement-full');

    // ⚠️ `??` 与 `||` 不能不加括号混用（解析歧义，语法错误）—— 括号是必须的
    const valueCount = options.valueCount ?? (parseInt(list.dataset.valueCount, 10) || 5);
    const maxRows = options.faceMax ?? (parseInt(list.dataset.faceMax, 10) || 6);
    const rowFactory = options.rowFactory;
    const baseHint = hint ? hint.textContent : '';
    let hintTimer = null;
    let invalidCount = 0;

    const rows = () => Array.from(list.querySelectorAll('details.face-row'));
    const readingInputs = (row) => Array.from(row.querySelectorAll('input.reading'));

    /** 空串 -> null（未填）；无法解析 -> NaN。 */
    function parseReading(raw) {
        const textValue = String(raw ?? '').trim();
        if (textValue === '') return null;
        const value = Number(textValue);
        return Number.isFinite(value) ? value : NaN;
    }

    /** 就地显示/隐藏该输入框的「请填数字」提示。 */
    function setInputHint(input, visible) {
        const cell = input.parentNode;
        const hintElement = cell ? cell.querySelector('.input-hint') : null;
        if (hintElement) hintElement.classList.toggle('show', visible);
        if (visible) input.setAttribute('title', '请填数字');
        else input.removeAttribute('title');
    }

    /** 把一行的派生状态刷到摘要行：三态圆点、进度、最小值、警告灯、名称。 */
    function renderSummary(row, filled, invalid, min) {
        const state = (filled >= valueCount) ? 'done' : (filled ? 'partial' : 'none');

        const dot = row.querySelector('.face-dot');
        if (dot) dot.className = `face-dot state-${state}`;

        const count = row.querySelector('.face-count');
        if (count) count.textContent = `${filled}/${valueCount}`;

        const minCell = row.querySelector('.min-value');
        if (minCell) minCell.textContent = (min === null) ? '—' : min.toFixed(2);

        // 警告灯：只在有非法格子时出现；折叠态也看得见 —— 这是折叠设计的关键补偿
        const lamp = row.querySelector('.face-lamp');
        if (lamp) {
            lamp.hidden = invalid === 0;
            const lampCount = lamp.querySelector('.lamp-count');
            if (lampCount) lampCount.textContent = String(invalid);
        }

        const name = row.querySelector('.face-name');
        const nameInput = row.querySelector('input.face-input');
        if (name && nameInput) name.textContent = nameInput.value.trim() || '新检测面';
    }

    /** 重算并刷新一行，返回该行的非法读数个数。 */
    function refreshRow(row) {
        const inputs = readingInputs(row);
        const numbers = [];
        let invalid = 0;

        inputs.forEach((input) => {
            const value = parseReading(input.value);
            const bad = Number.isNaN(value);
            input.classList.toggle('is-invalid', bad);
            setInputHint(input, bad);
            if (bad) {
                invalid += 1;
                return;
            }
            if (value !== null) numbers.push(value);
        });

        // 最小值计算不变：忽略空值，也不让非法值参与
        const min = numbers.length ? Math.min(...numbers) : null;
        inputs.forEach((input) => {
            const value = parseReading(input.value);
            input.classList.toggle('is-min', min !== null && value === min);
        });

        renderSummary(row, numbers.length, invalid, min);
        return invalid;
    }

    function applyValidity() {
        const blocked = invalidCount > 0;

        if (saveButton) {
            saveButton.disabled = blocked;
            if (blocked) saveButton.setAttribute('title', '请先修正标红的厚度读数');
            else saveButton.removeAttribute('title');
        }

        if (formStatus) {
            formStatus.textContent = blocked
                ? `有 ${invalidCount} 个厚度读数不是有效数字，请填入数字或清空该格后再保存。`
                : '';
            formStatus.classList.toggle('show', blocked);
        }
    }

    /** 全表校验：刷新每行，并按非法读数个数决定能否保存。返回非法格子数。 */
    function scan() {
        invalidCount = 0;
        rows().forEach((row) => { invalidCount += refreshRow(row); });
        applyValidity();
        return invalidCount;
    }

    /**
     * 展开所有含非法读数的行并聚焦第一个非法输入。
     * **只在用户点了保存（提交被拦截）时调用**，不在输入过程中调用 ——
     * 打字时突然有内容在手指底下展开是很糟的体验。
     */
    function revealInvalid() {
        const broken = rows().filter((row) => !!row.querySelector('input.reading.is-invalid'));
        broken.forEach((row) => { row.open = true; });
        if (broken.length) {
            const first = broken[0].querySelector('input.reading.is-invalid');
            if (first) first.focus();
        }
        return broken.length;
    }

    function nextIndex() {
        let max = -1;
        rows().forEach((row) => {
            row.querySelectorAll('input.face-input').forEach((input) => {
                const match = /^face_(\d+)$/.exec(input.name);
                if (match) max = Math.max(max, parseInt(match[1], 10));
            });
        });
        return max + 1;
    }

    const canAdd = () => rows().length < maxRows && nextIndex() < maxRows;

    function refreshAddButton() {
        if (!addButton) return;
        const allowed = canAdd();
        addButton.disabled = !allowed;
        if (hint) hint.textContent = allowed ? baseHint : `已达到上限（最多 ${maxRows} 个检测面）`;
    }

    function flashHint(message) {
        if (!hint) return;
        globalThis.clearTimeout(hintTimer);
        hint.textContent = message;
        hintTimer = globalThis.setTimeout(refreshAddButton, 2000);
    }

    function addRow() {
        if (!canAdd() || typeof rowFactory !== 'function') return;
        const item = rowFactory(nextIndex());
        if (!item) return;
        list.appendChild(item);
        const row = item.querySelector ? item.querySelector('details.face-row') : null;
        if (row) row.open = true;               // 新行直接展开：用户点"添加"就是要填它

        scan();
        refreshAddButton();
        const firstInput = row ? row.querySelector('input.face-input') : null;
        if (firstInput) firstInput.focus();
        return item;
    }

    function removeRow(row) {
        if (!row) return;
        if (rows().length <= 1) {
            flashHint('至少保留 1 个检测面');
            return;
        }
        const item = row.closest('li') || row;
        item.parentNode.removeChild(item);
        scan();
        refreshAddButton();
    }

    list.addEventListener('input', (event) => {
        if (event.target.closest('details.face-row')) scan();
    });

    list.addEventListener('click', (event) => {
        const button = event.target.closest('.row-remove');
        if (!button) return;
        event.preventDefault();
        removeRow(button.closest('details.face-row'));
    });

    if (addButton) addButton.addEventListener('click', addRow);

    // 关键：禁用的提交按钮挡不住"在文本框里按回车"的隐式提交，这里补一道拦截
    if (form) {
        form.addEventListener('submit', (event) => {
            if (scan() === 0) return;
            event.preventDefault();
            revealInvalid();
        });
    }

    /**
     * 「截面尺寸要求」的条文很长，闭合态会被浏览器截断；把选中的全文显示在下方。
     * （对应 Flask 侧 `syncRequirement`，那边由模板渲染选项、这里由视图渲染，逻辑一样。）
     */
    function syncRequirement() {
        if (!requirementSelect || !requirementFull) return;
        const option = requirementSelect.options[requirementSelect.selectedIndex];
        const label = option ? option.textContent.trim() : '';
        const isPlaceholder = !requirementSelect.value || label.startsWith('（不填');
        requirementFull.textContent = isPlaceholder ? '' : label;
        requirementFull.hidden = isPlaceholder;
    }
    if (requirementSelect) {
        requirementSelect.addEventListener('change', syncRequirement);
        syncRequirement();
    }

    scan();
    refreshAddButton();

    return { scan, rows, revealInvalid, addRow, refreshAddButton, valueCount, maxRows };
}

/**
 * 把 `parseRecordForm()` 返回的 `errors` 标到表单上（就地标红 + 就地提示 + 展开出错行）。
 *
 * 语义与 Flask 侧"服务端校验失败回填"完全一致 —— 那边靠重新渲染带 `input-error` 的 HTML
 * 与 `open` 属性，这边靠就地改 class。**用户看到的现象必须一样**：
 * 出错的格子标红、旁边写清原因、出错的行自动展开。
 */
export function applyFieldErrors(root, errors) {
    const keys = Object.keys(errors ?? {});
    if (!keys.length) return 0;

    let marked = 0;
    for (const key of keys) {
        const input = root.querySelector(`[name="${key}"]`);
        if (!input) continue;
        input.classList.add('input-error');
        marked += 1;
        // 就地提示：紧跟在控件后面的 .field-error（没有就建一个）
        const holder = input.closest('.form-control') || input.closest('.reading-cell') || input.parentNode;
        if (holder && !holder.querySelector('.field-error')) {
            holder.appendChild(h('p.field-error', { text: errors[key] }));
        } else if (holder) {
            holder.querySelector('.field-error').textContent = errors[key];
        }
    }

    // 表单级错误（如 `faces`）：显示在表单顶部
    if (errors.faces) {
        const form = root.querySelector('#record-form');
        const box = root.querySelector('.form-level-errors') || h('div.form-level-errors');
        box.textContent = '';
        box.appendChild(h('div.error', { text: errors.faces }));
        if (form && !box.parentNode) form.parentNode.insertBefore(box, form);
        marked += 1;
    }

    // 出错的行自动展开 —— 折叠态把错误藏起来是这一整套设计里最危险的一种失败
    const rowsWithError = new Set();
    for (const key of keys) {
        const matched = /^(?:face|value)_(\d+)/.exec(key);
        if (matched) rowsWithError.add(Number(matched[1]));
    }
    for (const index of rowsWithError) {
        const row = root.querySelector(`details.face-row[data-index="${index}"]`);
        if (row) row.open = true;
    }
    return marked;
}

/** 从表单读取 `{key: value}`（供数据层的 `parseRecordForm` 消费）。 */
export function collectForm(form) {
    const data = {};
    for (const element of form.querySelectorAll('input[name], select[name], textarea[name]')) {
        if (element.type === 'radio' && !element.checked) continue;
        // 复选框按"勾选才有值"收集（表单里目前没有复选框，留作约定）
        if (element.type === 'checkbox') {
            if (element.checked) data[element.name] = element.value;
            continue;
        }
        data[element.name] = element.value;
    }
    return data;
}
