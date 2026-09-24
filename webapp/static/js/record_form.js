/* 检测记录表单：检测面行的增删 + 每行 5 个读数的实时最小值 + 非法读数拦截。
 *
 * 四条关键约定：
 * 1. 最小值只用于**即时预览**，不参与提交；保存与导出时由服务端
 *    （services/thickness.py）重算 —— 前端算出的值不被信任。
 * 2. 行下标必须落在 0..face_max-1，因为服务端固定探测这个范围，不读"行数"字段。
 * 3. 无 JS 时表格照常提交，只是不显示实时最小值（服务端已渲染初次值）。
 * 4. 任一读数"非空但不是数字"时：该输入框标红 + 就地提示「请填数字」，
 *    **保存按钮禁用**，并拦截表单提交（防止在文本框里按回车隐式提交）。
 *    最小值计算不受影响，仍按有效值计算 —— 避免出现"看起来能保存"的假象。
 */
(function () {
    'use strict';

    var table = document.getElementById('face-table');
    if (!table) return;

    var tbody = table.tBodies[0];
    var rowTemplate = document.getElementById('face-row-template');
    var addButton = document.getElementById('add-face');
    var hint = document.getElementById('face-hint');
    var form = document.getElementById('record-form');
    var saveButton = document.getElementById('save-record');
    var formStatus = document.getElementById('form-status');
    var maxRows = parseInt(table.dataset.faceMax, 10) || 6;
    var baseHint = hint ? hint.textContent : '';
    var hintTimer = null;
    var invalidCount = 0;

    function rows() {
        return Array.prototype.slice.call(tbody.querySelectorAll('tr.face-row'));
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

    /** 重算一行的最小值并更新标记，返回该行的非法读数个数。 */
    function updateRow(row) {
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
        var cell = row.querySelector('.min-value');
        if (cell) cell.textContent = (min === null) ? '—' : min.toFixed(2);

        inputs.forEach(function (input) {
            var value = parseReading(input.value);
            input.classList.toggle('is-min', min !== null && value === min);
        });

        return invalid;
    }

    /** 全表校验：刷新每行的最小值与标记，并按非法读数个数决定能否保存。 */
    function scan() {
        invalidCount = 0;
        rows().forEach(function (row) {
            invalidCount += updateRow(row);
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
        var holder = document.createElement('tbody');
        holder.innerHTML = html;

        var row = holder.querySelector('tr.face-row');
        if (!row) return;
        tbody.appendChild(row);

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
        row.parentNode.removeChild(row);
        scan();
        refreshAddButton();
    }

    tbody.addEventListener('input', function (event) {
        if (event.target.closest('tr.face-row')) scan();
    });

    tbody.addEventListener('click', function (event) {
        var button = event.target.closest('.row-remove');
        if (!button) return;
        event.preventDefault();
        removeRow(button.closest('tr.face-row'));
    });

    if (addButton) addButton.addEventListener('click', addRow);

    // 关键：禁用的提交按钮挡不住"在文本框里按回车"的隐式提交，这里补一道拦截
    if (form) {
        form.addEventListener('submit', function (event) {
            if (scan() === 0) return;
            event.preventDefault();
            var firstInvalid = tbody.querySelector('input.reading.is-invalid');
            if (firstInvalid) firstInvalid.focus();
        });
    }

    scan();
    refreshAddButton();
})();
