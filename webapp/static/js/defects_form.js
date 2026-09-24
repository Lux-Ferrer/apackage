/* 缺陷填报表单：隐患图片的大小校验与本地预览。
 *
 * 与 M1 的非法读数拦截同一套思路：**前端只做即时反馈，服务端才是权威**。
 * 超限时就地提示并清空选择，避免用户以为"选上了"。
 */
(function () {
    'use strict';

    var input = document.getElementById('image');
    if (!input) return;

    var preview = document.getElementById('image-preview');
    var previewImage = document.getElementById('image-preview-img');
    var errorBox = document.getElementById('image-error');
    var maxBytes = parseInt(input.dataset.maxBytes, 10) || 0;
    var objectUrl = null;

    function showError(message) {
        if (!errorBox) return;
        errorBox.textContent = message || '';
        errorBox.hidden = !message;
        input.classList.toggle('input-error', Boolean(message));
    }

    function clearPreview() {
        if (objectUrl) {
            window.URL.revokeObjectURL(objectUrl);
            objectUrl = null;
        }
        if (preview) preview.hidden = true;
        if (previewImage) previewImage.removeAttribute('src');
    }

    function describeSize(bytes) {
        return (bytes / (1024 * 1024)).toFixed(1) + 'MB';
    }

    input.addEventListener('change', function () {
        var file = input.files && input.files[0];
        clearPreview();
        if (!file) {
            showError('');
            return;
        }
        if (maxBytes && file.size > maxBytes) {
            showError('图片不能超过 ' + Math.round(maxBytes / (1024 * 1024))
                + 'MB（当前 ' + describeSize(file.size) + '）');
            input.value = '';                       // 清空，避免"看起来选上了"
            return;
        }
        showError('');
        if (preview && previewImage && window.URL && window.URL.createObjectURL) {
            objectUrl = window.URL.createObjectURL(file);
            previewImage.src = objectUrl;
            preview.hidden = false;
        }
    });
})();
