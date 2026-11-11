/* 页面骨架的公共片段：卡片、页头、底部操作条、图片预览。
 *
 * 这些片段一一对应 Jinja 模板里反复出现的那些 class（`.card` / `.page-head` /
 * `.action-bar` / `.report-thumb` …）。集中在这里的理由与 Flask 侧抽 `_card.html`
 * 一样：**同一个视觉块只写一次**，将来调样式不用满仓库找。
 */

import { h, link } from '../ui/dom.js';

/** 一张卡片（页面里最主要的容器）。 */
export function card(children, className = null) {
    return h('div.card', { class: className }, children);
}

/** 页头：左边标题、右边一组操作。`title` 可以是字符串或节点（标题里常要嵌 `span.muted`）。 */
export function pageHead(title, actions = null, { level = 1, subtitle = null } = {}) {
    const heading = h(`h${level}`, null, title);
    const nodes = [h('div.page-head', null, [heading, actions ? h('div.head-actions', null, actions) : null])];
    if (subtitle) nodes.push(h('p.sub', { text: subtitle }));
    return nodes;
}

/** 返回链接（页头右上角那个「← 返回…」）。 */
export function backLink(href, label) {
    return link(href, `← ${label}`);
}

/**
 * 表单页的底部固定操作条。
 *
 * 表单页**不显示底部 Tab**（UI 设计 1.3）：长表单 + 数字键盘下，Tab 会占掉拇指区并误触，
 * 而"保存"必须落在拇指可达处。
 *
 * `statusId` 是保存被拦截时的提示位 —— 放在操作条里，保证提示不会被挤出屏幕。
 * `submitId` 是保存按钮的 id（检测记录表单必须叫 `save-record`：那是 UI 阶段冻结的契约，
 * `ui/record-form.js` 靠它禁用按钮）。
 */
export function actionBar({ cancelHref, cancelLabel = '取消', submitLabel = '保存',
    formId, statusId = null, submitId = null }) {
    return h('div.action-bar', null, [
        statusId ? h('p.form-status', { id: statusId, role: 'status', 'aria-live': 'polite' }) : null,
        h('span.action-spacer'),
        link(cancelHref, cancelLabel),
        h('button', { type: 'submit', form: formId, id: submitId, text: submitLabel }),
    ]);
}

/** 一行「标签 + 控件」的表单行（label 左 / 控件右的横向表格布局，UI 设计第 3 节）。 */
export function formRow({ label, forId = null, required = false, block = false, control, hint = null, error = null }) {
    return h('div.form-row', { class: block ? 'form-row-block' : null }, [
        forId
            ? h('label', { for: forId }, [label, required ? h('span.required', { text: ' *' }) : null])
            : h('label', null, [label, required ? h('span.required', { text: ' *' }) : null]),
        h('div.form-control', null, [
            control,
            hint ? h('p.hint', { text: hint }) : null,
            error ? h('p.field-error', { text: error }) : null,
        ]),
    ]);
}

/** 文本输入框。 */
export function input({ name, id = null, value = '', type = 'text', maxlength = null,
    placeholder = null, className = null, dataset = null, inputmode = null, pattern = null,
    enterkeyhint = null, required = false }) {
    return h('input', {
        type,
        id: id ?? name,
        name,
        class: className,
        value: value ?? '',
        maxlength,
        placeholder,
        autocomplete: 'off',
        inputmode,
        pattern,
        enterkeyhint,
        required: required || null,
        dataset,
    });
}

/** 下拉框。`options` 是 `[{value, label, selected}]`。 */
export function select({ name, id = null, options, className = null, dataset = null }) {
    const element = h('select', {
        id: id ?? name, name, class: className, dataset,
    });
    for (const option of options) {
        element.appendChild(h('option', {
            value: option.value,
            text: option.label,
            selected: option.selected || null,
            disabled: option.disabled || null,
        }));
    }
    return element;
}

/** 文本域。 */
export function textarea({ name, id = null, value = '', rows = 3, placeholder = null, required = false }) {
    const element = h('textarea', {
        id: id ?? name, name, rows, placeholder, required: required || null,
    });
    element.value = value ?? '';
    return element;
}

/**
 * 隐患图片缩略图。
 *
 * 关键差异（相对 Flask 版）：那边 `<img src=".../thumbnail">` 由服务端现压；
 * 这边缩略图**已经存在 IndexedDB 里**（设计文档 3.4 的那次有意偏离），
 * 所以这里只需要 objectURL（`blobUrl`）—— 列表渲染不再解码 20MB 的原图。
 */
export function thumbnail(blobUrl, { href, alt = '隐患图片缩略图', hasImage = true } = {}) {
    return h('a.report-thumb', { href, 'aria-label': alt }, hasImage && blobUrl
        ? h('img', { src: blobUrl, alt, loading: 'lazy', width: 72, height: 72 })
        : h('span.thumb-empty', { text: '无图' }));
}

/** 「加载中」占位（数据层是异步的，首屏需要一句话）。 */
export function loading(text = '加载中…') {
    return h('p.hint', { text });
}
