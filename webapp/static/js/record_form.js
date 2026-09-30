/* 检测记录表单：检测面的增删 + 每行 5 个读数的实时最小值 + 三态着色 + 警告灯 + 非法读数拦截。
 *
 * UI 改造（详见 docs/management/UI-设计.md 第 2 节）后，检测面从 <table> 的 8 列
 * 改成「摘要行 + 下级编辑」（<details>）。JS 的职责边界因此被明确划成两半：
 *
 *   - **结构**（开合、增删）交给原生 <details> 与克隆 <template>，JS 不接管开合；
 *     自动展开由服务端写 open 属性完成，所以**没有 JS 也能完整录入并提交**。
 *   - **派生状态**（三态圆点、进度 N/5、最小值、警告灯、非法标红）由这里刷新。
 *
 * 五条关键约定：
 * 1. 最小值只用于**即时预览**，不参与提交；保存与导出时由服务端
 *    （services/thickness.py）重算 —— 前端算出的值不被信任。
 * 2. 行下标必须落在 0..face_max-1，因为服务端固定探测这个范围，不读"行数"字段。
 * 3. 无 JS 时表单照常提交，只是没有实时反馈（服务端已渲染好初值：最小值、三态、开合）。
 * 4. 任一读数"非空但不是数字"时：该输入框标红 + 就地提示「请填数字」，
 *    **保存按钮禁用**，并拦截表单提交（防止在文本框里按回车隐式提交）。
 *    最小值计算不受影响，仍按有效值计算 —— 避免出现"看起来能保存"的假象。
 * 5. **完整度与有效性是两个独立通道**：圆点颜色（三态）表示"还剩多少活"，
 *    警告灯表示"能不能保存"。合并成一个视觉信号会让"5 格全填了 abc"
 *    看起来像填完了，用户点保存才发现按钮是灰的。
 */
(function () {
    'use strict';

    var list = document.getElementById('face-list');
    if (!list) return;

    var rowTemplate = document.getElementById('face-row-template');
    var addButton = document.getElementById('add-face');
    var hint = document.getElementById('face-hint');
    var form = document.getElementById('record-form');
    var saveButton = document.getElementById('save-record');
    var formStatus = document.getElementById('form-status');
    var valueCount = parseInt(list.dataset.valueCount, 10) || 5;
    var maxRows = parseInt(list.dataset.faceMax, 10) || 6;
    var baseHint = hint ? hint.textContent : '';
    var hintTimer = null;
    var invalidCount = 0;

    function rows() {
        return Array.prototype.slice.call(list.querySelectorAll('details.face-row'));
    }

    function readingInputs(row) {
        return Array.prototype.slice.call(row.querySelectorAll('input.reading'));
    }

    /** 空串 -> null（未填）；无法解析 -> NaN。 */
    function parseReading(raw) {
        var text = (raw || '').trim();
        if (text === '') return null;
        var value = Number(text);
        return isFinite(value) ? value : NaN;
    }

    /** 就地显示/隐藏该输入框的「请填数字」提示。 */
    function setInputHint(input, visible) {
        var cell = input.parentNode;
        var hintElement = cell ? cell.querySelector('.input-hint') : null;
        if (hintElement) hintElement.classList.toggle('show', visible);
        if (visible) {
            input.setAttribute('title', '请填数字');
        } else {
            input.removeAttribute('title');
        }
    }

    /** 把一行的派生状态刷到摘要行上：三态圆点、进度、最小值、警告灯、名称。 */
    function renderSummary(row, filled, invalid, min) {
        var state = (filled >= valueCount) ? 'done' : (filled ? 'partial' : 'none');

        var dot = row.querySelector('.face-dot');
        if (dot) dot.className = 'face-dot state-' + state;

        var count = row.querySelector('.face-count');
        if (count) count.textContent = filled + '/' + valueCount;

        var minCell = row.querySelector('.min-value');
        if (minCell) minCell.textContent = (min === null) ? '—' : min.toFixed(2);

        // 警告灯：只在有非法格子时出现；折叠态也看得见，这是折叠设计的关键补偿
        var lamp = row.querySelector('.face-lamp');
        if (lamp) {
            lamp.hidden = invalid === 0;
            var lampCount = lamp.querySelector('.lamp-count');
            if (lampCount) lampCount.textContent = String(invalid);
        }

        var name = row.querySelector('.face-name');
        var nameInput = row.querySelector('input.face-input');
        if (name && nameInput) name.textContent = nameInput.value.trim() || '新检测面';
    }

    /** 重算并刷新一行，返回该行的非法读数个数。 */
    function refreshRow(row) {
        var inputs = readingInputs(row);
        var numbers = [];
        var invalid = 0;

        inputs.forEach(function (input) {
            var value = parseReading(input.value);
            var bad = isNaN(value);
            input.classList.toggle('is-invalid', bad);
            setInputHint(input, bad);
            if (bad) {
                invalid += 1;
                return;
            }
            if (value !== null) numbers.push(value);
        });

        // 最小值计算不变：忽略空值，也不让非法值参与
        var min = numbers.length ? Math.min.apply(null, numbers) : null;
        inputs.forEach(function (input) {
            var value = parseReading(input.value);
            input.classList.toggle('is-min', min !== null && value === min);
        });

        renderSummary(row, numbers.length, invalid, min);
        return invalid;
    }

    /** 全表校验：刷新每行状态，并按非法读数个数决定能否保存。 */
    function scan() {
        invalidCount = 0;
        rows().forEach(function (row) {
            invalidCount += refreshRow(row);
        });
        applyValidity();
        return invalidCount;
    }

    function applyValidity() {
        var blocked = invalidCount > 0;

        if (saveButton) {
            saveButton.disabled = blocked;
            if (blocked) {
                saveButton.setAttribute('title', '请先修正标红的厚度读数');
            } else {
                saveButton.removeAttribute('title');
            }
        }

        if (formStatus) {
            formStatus.textContent = blocked
                ? '有 ' + invalidCount + ' 个厚度读数不是有效数字，请填入数字或清空该格后再保存。'
                : '';
            formStatus.classList.toggle('show', blocked);
        }
    }

    /**
     * 展开所有含非法读数的行并聚焦第一个非法输入。
     *
     * **只在用户点了保存（提交被拦截）时调用**，不在输入过程中调用 ——
     * 打字时突然有内容在手指底下展开是很糟的体验。平时靠摘要行的警告灯提示，
     * 用户想修就自己点那一行。
     */
    function revealInvalid() {
        var broken = rows().filter(function (row) {
            return !!row.querySelector('input.reading.is-invalid');
        });
        broken.forEach(function (row) { row.open = true; });
        if (broken.length) {
            var first = broken[0].querySelector('input.reading.is-invalid');
            if (first) first.focus();
        }
        return broken.length;
    }

    /** 下一个可用行下标 = 现有最大下标 + 1。 */
    function nextIndex() {
        var max = -1;
        rows().forEach(function (row) {
            Array.prototype.slice.call(row.querySelectorAll('input.face-input')).forEach(function (input) {
                var match = /^face_(\d+)$/.exec(input.name);
                if (match) max = Math.max(max, parseInt(match[1], 10));
            });
        });
        return max + 1;
    }

    function canAdd() {
        return rows().length < maxRows && nextIndex() < maxRows;
    }

    function refreshAddButton() {
        if (!addButton) return;
        var allowed = canAdd();
        addButton.disabled = !allowed;
        if (hint) {
            hint.textContent = allowed ? baseHint : '已达到上限（最多 ' + maxRows + ' 个检测面）';
        }
    }

    function flashHint(text) {
        if (!hint) return;
        window.clearTimeout(hintTimer);
        hint.textContent = text;
        hintTimer = window.setTimeout(refreshAddButton, 2000);
    }

    function addRow() {
        if (!canAdd() || !rowTemplate) return;

        var html = rowTemplate.innerHTML.split('__INDEX__').join(String(nextIndex()));
        var holder = document.createElement('div');
        holder.innerHTML = html;

        var item = holder.querySelector('li');
        var row = item ? item.querySelector('details.face-row') : null;
        if (!row) return;
        list.appendChild(item);
        row.open = true;                      // 新行直接展开：用户点"添加"就是要填它

        scan();
        refreshAddButton();

        var firstInput = row.querySelector('input.face-input');
        if (firstInput) firstInput.focus();
    }

    function removeRow(row) {
        if (!row) return;
        if (rows().length <= 1) {
            flashHint('至少保留 1 个检测面');
            return;
        }
        var item = row.closest('li') || row;
        item.parentNode.removeChild(item);
        scan();
        refreshAddButton();
    }

    list.addEventListener('input', function (event) {
        if (event.target.closest('details.face-row')) scan();
    });

    list.addEventListener('click', function (event) {
        var button = event.target.closest('.row-remove');
        if (!button) return;
        event.preventDefault();
        removeRow(button.closest('details.face-row'));
    });

    if (addButton) addButton.addEventListener('click', addRow);

    // 关键：禁用的提交按钮挡不住"在文本框里按回车"的隐式提交，这里补一道拦截
    if (form) {
        form.addEventListener('submit', function (event) {
            if (scan() === 0) return;
            event.preventDefault();
            revealInvalid();
        });
    }

    // 「截面尺寸要求」的条文很长，闭合态会被浏览器截断；把选中的全文显示在下方
    var requirementSelect = document.getElementById('requirement_index');
    var requirementFull = document.getElementById('requirement-full');
    function syncRequirement() {
        if (!requirementSelect || !requirementFull) return;
        var option = requirementSelect.options[requirementSelect.selectedIndex];
        var text = option ? option.textContent.trim() : '';
        var isPlaceholder = !requirementSelect.value || text.indexOf('（不填') === 0;
        requirementFull.textContent = isPlaceholder ? '' : text;
        requirementFull.hidden = isPlaceholder;
    }
    if (requirementSelect) {
        requirementSelect.addEventListener('change', syncRequirement);
        syncRequirement();
    }

    scan();
    refreshAddButton();
})();
