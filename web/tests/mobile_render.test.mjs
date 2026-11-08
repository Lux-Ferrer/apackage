/* 真机 bug 的回归测试：底部操作条被 Tab 挡住 / Tab 图标不可见。
 *
 * 这两个都是**只有真机才会暴露**的问题，jsdom 里查 DOM 结构完全正常：
 *
 * 1. `tabbar.hidden = true` 在真机上**没有任何效果** —— 作者样式 `.tabbar { display: flex }`
 *    压过 UA 的 `[hidden] { display: none }`。于是表单页底部还是三个 Tab，
 *    而本该固定在那里的「保存 / 取消」操作条被盖住（两者都 `position: fixed; bottom: 0`，
 *    Tab 在 DOM 里更靠后 → 盖在上面）。
 *    **而 jsdom 的级联顺序与浏览器相反**：它让 UA 的 `[hidden]` 赢，所以
 *    `getComputedStyle(tabbar).display` 在 jsdom 里返回 `none`，"看起来没问题"。
 *    → 所以这里**测规则存在性**（作者样式里必须有 `[hidden]` 的 `!important` 覆盖）。
 *
 * 2. 图标不可见：`document.createElement('svg')` 造出来的是 **HTML 命名空间**里的未知标签，
 *    浏览器不渲染它。jsdom 里 `querySelector('svg')` 照样找得到、`outerHTML` 也正常。
 *    → 这里**测命名空间**，这是唯一能区分"看着在、其实不画"的信号。
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { JSDOM } from 'jsdom';

const SVG_NS = 'http://www.w3.org/2000/svg';
const HTML_NS = 'http://www.w3.org/1999/xhtml';

/** 装一套最小 DOM 给 dom.js 用。 */
function installDom() {
    const dom = new JSDOM('<!doctype html><html><body><div id="host"></div></body></html>');
    for (const key of ['window', 'document', 'Node', 'Element', 'HTMLElement']) {
        Object.defineProperty(globalThis, key, {
            value: dom.window[key], configurable: true, writable: true,
        });
    }
    return dom;
}

/* --------------------------------------------------------------------------
 * 图标：必须是 SVG 命名空间
 * ------------------------------------------------------------------------ */

test('h("svg") 与它的子节点都在 SVG 命名空间里（否则浏览器不渲染）', async () => {
    installDom();
    const { h, svg, SVG_NS: exported } = await import('../app/ui/dom.js');
    assert.equal(exported, SVG_NS);

    const icon = h('svg', {
        viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.8',
    }, h('path', { d: 'M3 21h18M5 21V7l7-4 7 4v14' }));

    assert.equal(icon.namespaceURI, SVG_NS, 'svg 必须在 SVG 命名空间（createElement 会在 HTML 命名空间）');
    assert.equal(icon.firstChild.namespaceURI, SVG_NS, 'path 子节点也必须在 SVG 命名空间');
    assert.equal(icon.getAttribute('viewBox'), '0 0 24 24', 'viewBox 大小写必须保住');
    assert.equal(icon.getAttribute('stroke-width'), '1.8');
    // 语义化入口
    assert.equal(svg('path', { d: 'M0 0' }).namespaceURI, SVG_NS);
    assert.throws(() => svg('div'), /不是 SVG 标签/);
});

test('普通元素仍然是 HTML 命名空间（别把 div 也塞进 SVG）', async () => {
    installDom();
    const { h } = await import('../app/ui/dom.js');
    assert.equal(h('div.card').namespaceURI, HTML_NS);
    assert.equal(h('div.card').className, 'card');
    assert.equal(h('span', { text: '文字' }).textContent, '文字');
});

test('底部导航真的产出了 SVG 图标（而不是空 span）', async () => {
    installDom();
    const { renderNav } = await import('../app/main.js');
    const container = document.getElementById('host');
    renderNav(container, 'projects', { withIcons: true });

    const icons = container.querySelectorAll('.nav-icon svg');
    assert.equal(icons.length, 3, '三个 Tab 应各有一个图标');
    for (const icon of icons) {
        assert.equal(icon.namespaceURI, SVG_NS, '图标不在 SVG 命名空间 → 真机上不会画出来');
        assert.equal(icon.querySelector('path')?.namespaceURI, SVG_NS, 'path 也必须在 SVG 命名空间');
    }
});

/* --------------------------------------------------------------------------
 * hidden 必须真的能藏住
 * ------------------------------------------------------------------------ */

test('作者样式里有 [hidden] 的强制隐藏规则（jsdom 查不出这个 bug，只能查规则）', () => {
    // ⚠️ 先剥掉 CSS 注释再匹配：m5.css 的**说明文字**里就写着 `[hidden] { display: none !important; }`，
    // 不剥注释的话这条测试会一直绿 —— 连规则被删掉都发现不了（做阳性对照时正好撞上）。
    const stripCssComments = (text) => text.replace(/\/\*[\s\S]*?\*\//g, '');
    const css = stripCssComments(readFileSync(new URL('../styles/m5.css', import.meta.url), 'utf8'));

    // 允许写法差异（多空格、换行），但要同时具备三件事：选择器、display: none、!important
    const rule = /\[hidden\]\s*\{[^}]*display\s*:\s*none\s*!important[^}]*\}/.test(css);
    assert.ok(rule,
        'm5.css 里必须有 `[hidden] { display: none !important; }` —— '
        + '否则 .tabbar { display: flex } 会压过 UA 的 [hidden]，表单页底部会被 Tab 盖住操作条');

    // 顺带守住"为什么必须在作者样式里"这一条：确认 app.css 里确实有会压过它的 display 规则
    const appCss = stripCssComments(readFileSync(new URL('../styles/app.css', import.meta.url), 'utf8'));
    assert.match(appCss, /\.tabbar\s*\{[\s\S]*?display:\s*flex/, 'app.css 的 .tabbar 是靠 display:flex 显示的');
});

test('jsdom 与浏览器的差异记录：别用 jsdom 的 computedStyle 去验这件事', () => {
    // 这条测试存在的意义是**把踩过的坑写进代码**：
    // jsdom 让 UA 的 [hidden] 赢，浏览器让作者的 .tabbar{display:flex} 赢。
    // 所以任何"在 jsdom 里断言 display === none 就代表真机没问题"的测试都是假的。
    const dom = new JSDOM('<style>.tabbar{display:flex}</style><nav class="tabbar" hidden></nav>');
    const nav = dom.window.document.querySelector('.tabbar');
    assert.equal(dom.window.getComputedStyle(nav).display, 'none',
        'jsdom 在这里返回 none（与真机相反）—— 所以这个信号不能用来判断真机行为');
});
