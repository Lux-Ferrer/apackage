/* 检测记录表单：检测面行的增删 + 每行 5 个读数的实时最小值。
 *
 * 三条关键约定：
 * 1. 最小值只用于**即时预览**，不参与提交；保存与导出时由服务端
 *    （services/thickness.py）重算 —— 前端算出的值不被信任。
 * 2. 行下标必须落在 0..face_max-1，因为服务端固定探测这个范围，不读"行数"字段。
 * 3. 无 JS 时表格照常提交，只是不显示实时最小值（服务端已渲染初次值）。
 */
(function () {
    'use strict';

    var table = document.getElementById('face-table');
    if (!table) return;

    var tbody = table.tBodies[0];
    var rowTemplate = document.getElementById('face-row-template');
    var addButton = document.getElementById('add-face');
    var hint = document.getElementById('face-hint');
    var maxRows = parseInt(table.dataset.faceMax, 10) || 6;
    var baseHint = hint ? hint.textContent : '';
    var hintTimer = null;

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

    /** 重算一行的最小值，并更新高亮 / 非法标记。 */
    function updateRow(row) {
        var inputs = readingInputs(row);
        var numbers = [];

        inputs.forEach(function (input) {
            var value = parseReading(input.value);
            if (isNaN(value)) {
                input.classList.add('is-invalid');
                return;
            }
            input.classList.remove('is-invalid');
            if (value !== null) numbers.push(value);
        });

        var min = numbers.length ? Math.min.apply(null, numbers) : null;
        var cell = row.querySelector('.min-value');
        if (cell) cell.textContent = (min === null) ? '—' : min.toFixed(2);

        inputs.forEach(function (input) {
            var value = parseReading(input.value);
            input.classList.toggle('is-min', min !== null && value === min);
        });
    }

    function updateAll() {
        rows().forEach(updateRow);
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

        updateRow(row);
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
        refreshAddButton();
    }

    tbody.addEventListener('input', function (event) {
        var row = event.target.closest('tr.face-row');
        if (row) updateRow(row);
    });

    tbody.addEventListener('click', function (event) {
        var button = event.target.closest('.row-remove');
        if (!button) return;
        event.preventDefault();
        removeRow(button.closest('tr.face-row'));
    });

    if (addButton) addButton.addEventListener('click', addRow);

    updateAll();
    refreshAddButton();
})();
