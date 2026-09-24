/* 应用级交互：带 data-confirm 的表单，提交前弹出应用内确认弹窗。
 *
 * 用法：
 *   <form method="post" data-confirm="确认删除…？" data-confirm-ok="确认删除">
 *
 * 弹窗不可用时（老浏览器）退化为原生 confirm()，功能不受影响。
 */
(function () {
    'use strict';

    var dialog = document.getElementById('confirm-dialog');
    var messageEl = document.getElementById('confirm-message');
    var okButton = document.getElementById('confirm-ok');
    var pendingForm = null;

    function submitNow(form) {
        form.dataset.confirmed = 'true';
        // 直接调 submit() 不会再触发 submit 事件，避免递归
        form.submit();
    }

    function openConfirm(form, message) {
        if (!dialog || typeof dialog.showModal !== 'function') {
            if (window.confirm(message)) submitNow(form);
            return;
        }
        messageEl.textContent = message;
        okButton.textContent = form.dataset.confirmOk || '确认删除';
        dialog.returnValue = '';          // 清掉上次的返回值，防止 Esc 被当成"确认"
        pendingForm = form;
        dialog.showModal();
    }

    if (dialog) {
        dialog.addEventListener('close', function () {
            var form = pendingForm;
            pendingForm = null;
            if (form && dialog.returnValue === 'confirm') submitNow(form);
        });
    }

    document.addEventListener('submit', function (event) {
        var form = event.target;
        if (!form.dataset || !form.dataset.confirm) return;
        if (form.dataset.confirmed === 'true') return;
        event.preventDefault();
        openConfirm(form, form.dataset.confirm);
    });
})();
