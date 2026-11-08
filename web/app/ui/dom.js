/* DOM 小工具：用函数建节点，而不是拼 HTML 字符串。
 *
 * 为什么坚持"建节点"而不是 innerHTML 拼串
 * ----------------------------------------
 * 这一版的数据全部来自用户输入（项目名、构件位置、整改方案……）。拼字符串就必须**处处记得转义**，
 * 漏一处就是一个 XSS；而且"忘了转义"这种事在 review 里很难看出来。
 * `h()` 走 textContent / setAttribute，转义问题从构造上就不存在。
 *
 * 唯一例外是检测面的行模板（`<template id="face-row-template">`）：它里面要复制
 * 一整棵带 `__INDEX__` 占位符的子树。那里用的是**开发者写的静态标记**（不含用户数据），
 * 用户值一律在渲染后通过 `value` 属性塞进去，所以同样安全。
 */

/* --------------------------------------------------------------------------
 * SVG：**必须**用 createElementNS（见 h() 的说明）
 * ------------------------------------------------------------------------ */

export const SVG_NS = 'http://www.w3.org/2000/svg';

/** 需要通过 SVG 命名空间创建的标签（本项目只用到这几个）。 */
export const SVG_TAGS = new Set(['svg', 'g', 'path', 'circle', 'ellipse', 'line',
    'polyline', 'polygon', 'rect', 'use', 'defs', 'title', 'text', 'tspan']);

/** 建一个 SVG 元素（语义化入口，避免调用方记错命名空间）。 */
export function svg(spec, options = null, children = null) {
    const tag = String(spec).split('.')[0];
    if (!SVG_TAGS.has(tag)) throw new Error(`不是 SVG 标签：${tag}`);
    return h(spec, options, children);
}

/* --------------------------------------------------------------------------
 * 元素构造
 * ------------------------------------------------------------------------ */

/**
 * 建一个元素。
 *
 * `h('div.card', {id: 'x'}, [子节点…])` —— 支持 `tag.class1.class2` 简写；
 * 属性名用 HTML 属性名（`class` / `for` / `aria-label`），也接受 `text` / `dataset` / `on` 三个便捷键。
 *
 * ⚠️ **SVG 必须用 `createElementNS`**：`document.createElement('svg')` 造出来的是
 * **HTML 命名空间**里的一个未知标签，浏览器不会把它当矢量图渲染 —— 元素在 DOM 里、
 * 有尺寸、`querySelector` 也找得到，**但屏幕上什么都没有**。
 * 这正是"底部 Tab 图标看不见"的根因（真机上才发现，jsdom 里查 DOM 结构完全正常）。
 */
export function h(spec, options = null, children = null) {
    const [tag = 'div', ...classes] = String(spec).split('.');
    const inSvg = SVG_TAGS.has(tag);
    const element = inSvg
        ? document.createElementNS(SVG_NS, tag)
        : document.createElement(tag || 'div');

    /** 设 class：SVG 元素的 `className` 是只读的 SVGAnimatedString，只能走属性。 */
    const setClass = (value) => {
        if (inSvg) element.setAttribute('class', value);
        else element.className = value;
    };
    if (classes.length) setClass(classes.join(' '));

    if (options) {
        for (const [key, value] of Object.entries(options)) {
            if (value === null || value === undefined || value === false) continue;
            if (key === 'text') element.textContent = String(value);
            else if (key === 'class') {
                const merged = inSvg
                    ? [element.getAttribute('class'), value].filter(Boolean).join(' ')
                    : [element.className, value].filter(Boolean).join(' ');
                setClass(merged);
            } else if (key === 'dataset') Object.assign(element.dataset, value);
            else if (key === 'on') {
                for (const [event, handler] of Object.entries(value)) {
                    element.addEventListener(event, handler);
                }
            } else if (value === true) element.setAttribute(key, '');
            else element.setAttribute(key, String(value));
        }
    }

    append(element, children);
    return element;
}

/** 追加子节点：字符串当文本、数组递归、null/false 跳过。 */
export function append(parent, children) {
    if (children === null || children === undefined || children === false) return parent;
    if (Array.isArray(children)) {
        for (const child of children) append(parent, child);
        return parent;
    }
    parent.appendChild(children instanceof Node ? children : document.createTextNode(String(children)));
    return parent;
}

/** 文本节点（`h()` 的 text 选项之外偶尔直接用）。 */
export function text(value) {
    return document.createTextNode(value === null || value === undefined ? '' : String(value));
}

/** 清空一个容器。 */
export function clear(element) {
    while (element.firstChild) element.removeChild(element.firstChild);
    return element;
}

/** `document.getElementById` 的简写（本项目里是唯一的"查全局元素"入口）。 */
export function byId(id) {
    return document.getElementById(id);
}

/** 把 `{a: 1}` 变成 `<dl class="info-grid">` 那种键值对块（项目详情/详情页共用）。 */
export function definitions(pairs) {
    return h('dl.info-grid', null, pairs.map(([label, value]) => h('div', null, [
        h('dt', { text: label }),
        h('dd', { text: value === null || value === undefined || value === '' ? '—' : value }),
    ])));
}

/** 一张两列（th/td）信息表 —— 报告详情与「应用信息」都用它。 */
export function infoTable(rows) {
    return h('table.grid', null, h('tbody', null, rows
        .filter((row) => row)
        .map(([label, value]) => h('tr', null, [
            h('th', { text: label }),
            value instanceof Node ? h('td', null, value) : h('td', { text: value }),
        ]))));
}

/** 徽标（隐患等级 / 模块状态共用）。 */
export function badge(label, className) {
    return h('span.badge', { class: className, text: label });
}

/** 链接。`href` 一律是 hash 路由（`#/...`）。 */
export function link(href, label, className = 'link') {
    return h('a', { class: className, href, text: label });
}

/** 「还没有数据」的空态块。 */
export function emptyState(message, action = null) {
    return [h('p.hint', { text: message }), action].filter(Boolean);
}
