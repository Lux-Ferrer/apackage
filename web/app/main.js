/* 应用引导：打开数据库 → 生成导航 → 监听 hash → 渲染视图。
 *
 * 这里是整个 M5 前端的"接线盒"。三件事：
 *   1. **数据来源**：`Database.open()` 打开 IndexedDB（M5-1 的数据层，与 Flask 的 SQLite 同语义）；
 *   2. **视图分发**：把 `router.resolve()` 的结果映射到 `views/*.js` 的渲染函数；
 *   3. **渲染之外的杂事**：导航高亮、表单页隐藏底部 Tab、objectURL 释放、错误兜底。
 *
 * 一条纪律：**视图只返回节点，不碰全局 DOM**。写 document 的操作全部集中在本文件与 ui/* 里，
 * 这样视图可以脱离浏览器渲染（Node 里用 jsdom 就能测整条链路）。
 */

import { Database } from './db.js';
import { flash, renderFlashes } from './ui/dialog.js';
import { byId, clear, h } from './ui/dom.js';
import { releaseObjectURLs } from './ui/objecturl.js';
import { NAV_ITEMS, activeTab, chromeFor, normalizePath, pathFor, resolve, titleFor } from './router.js';

import * as projectsView from './views/projects.js';
import * as recordsView from './views/records.js';
import * as reportsView from './views/reports.js';
import * as meView from './views/me.js';

/** 路由名 → 渲染函数。视图函数签名统一是 `(ctx) => {nodes, chrome?}`。 */
const VIEWS = {
    'projects.index': (ctx) => projectsView.index(ctx),
    'projects.new': (ctx) => projectsView.form(ctx, { editing: false }),
    'projects.detail': (ctx) => projectsView.detail(ctx),
    'projects.edit': (ctx) => projectsView.form(ctx, { editing: true }),
    'records.choose': (ctx) => recordsView.choose(ctx),
    'records.new': (ctx) => recordsView.form(ctx, { editing: false }),
    'records.edit': (ctx) => recordsView.form(ctx, { editing: true }),
    'reports.index': (ctx) => reportsView.index(ctx),
    'reports.new': (ctx) => reportsView.form(ctx),
    'reports.detail': (ctx) => reportsView.detail(ctx),
    'me.index': (ctx) => meView.index(ctx),
    'me.data': (ctx) => meView.data(ctx),
    'pages.about': (ctx) => meView.about(ctx),
};

/* --------------------------------------------------------------------------
 * 导航（一个定义，两处渲染 —— 与 Flask 的 _nav.html 同一套做法）
 * ------------------------------------------------------------------------ */

const ICONS = {
    projects: 'M3 21h18M5 21V7l7-4 7 4v14M9 21v-5h6v5',
    reports: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h4',
    me: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0',
};

function navIcon(key) {
    const path = h('path', { d: ICONS[key] ?? ICONS.projects });
    return h('svg', {
        viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.8',
        'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true',
    }, path);
}

/** 渲染导航（底部 Tab 与顶栏各渲染一次，定义只有一份）。 */
export function renderNav(container, active, { withIcons = true } = {}) {
    clear(container);
    for (const item of NAV_ITEMS) {
        const isActive = item.key === active;
        container.appendChild(h('a.nav-item', {
            class: isActive ? 'active' : null,
            href: item.href,
            'aria-current': isActive ? 'page' : null,
        }, [
            withIcons ? h('span.nav-icon', { 'aria-hidden': 'true' }, navIcon(item.key)) : null,
            h('span.nav-label', { text: item.label }),
        ]));
    }
}

/* --------------------------------------------------------------------------
 * 应用
 * ------------------------------------------------------------------------ */

export function createApp({
    db, document: doc = globalThis.document, window: win = globalThis.window,
    storage = globalThis.navigator?.storage ?? null, pipeline = undefined,
    // 底座模板字节：导出时要它来补 styles/theme（第 ⑥ 个补丁）。测试里可以注入。
    baseDocxBytes: injectedBase = null,
} = {}) {
    const viewRoot = doc.getElementById('view');
    const tabbar = doc.getElementById('tabbar');
    const topnav = doc.getElementById('topnav');
    let baseDocxPromise = null;

    /** 底座模板：懒加载 + 只取一次（13KB，但首屏不需要它）。 */
    async function baseDocxBytes() {
        if (injectedBase) return injectedBase;
        if (!baseDocxPromise) {
            baseDocxPromise = fetch('./assets/report_base.docx')
                .then((response) => {
                    if (!response.ok) throw new Error(`底座模板加载失败（HTTP ${response.status}）`);
                    return response.arrayBuffer();
                })
                .then((buffer) => new Uint8Array(buffer))
                .catch((error) => {
                    baseDocxPromise = null;      // 允许下次重试
                    throw error;
                });
        }
        return baseDocxPromise;
    }

    const app = {
        db,
        storage,
        pipeline,
        baseDocxBytes,
        get current() { return app._current; },
        navigate: (hash, options = {}) => {
            const target = String(hash).startsWith('#') ? String(hash) : `#${hash}`;
            // ⚠️ 必须在**赋值之前**判断"是不是已经在目标页"：
            // 赋值之后再比就一定相等，于是每次导航都会多渲染一次（白白多画一屏，
            // 而且留下一条与 hashchange 竞争的在途渲染 —— 踩过）。
            const alreadyThere = win.location.hash === target;
            if (options.replace) win.location.replace(target);
            else win.location.hash = target;
            // hash 没变 → 浏览器不会发 hashchange，那就得手动渲染一次，
            // 否则"保存后回到当前页"这类操作会静默什么都不发生。
            if (alreadyThere) return render();
            return undefined;
        },
        refresh: () => render(),
    };

    async function doRender() {
        const route = resolve(win.location.hash);
        app._current = route;

        if (!route.name) {
            // 空 hash / 未知路径 → 落到项目 Tab（与 Flask 的 `GET / → /projects/` 一致）。
            // 用 replace 而不是 push：不要在历史里留下这条"其实没渲染"的记录。
            app.navigate(pathFor('projects.index'), { replace: true });
            return;
        }

        releaseObjectURLs();                 // 上一屏建的图片 URL 全部释放（见 ui/objecturl.js）
        // 注意：这里**不能**清空提示 —— flash() 后面常常紧跟 navigate()/refresh()，
        // 清了用户就看不到回执。提示由 ui/dialog.js 的小队列管生命周期。

        const ctx = {
            db, storage, pipeline, baseDocxBytes,
            params: route.params ?? {},
            query: route.query ?? {},
            navigate: app.navigate,
            refresh: app.refresh,
            document: doc,
        };

        let result;
        try {
            const view = VIEWS[route.name];
            result = await view(ctx);
        } catch (error) {
            // 任何渲染期异常都要变成"看得懂的一句话"，而不是白屏
            result = {
                nodes: [h('div.card', null, [
                    h('h1', { text: '这一页出错了' }),
                    h('p.sub', { text: error?.message ?? String(error) }),
                    h('p', null, h('a', { class: 'link', href: pathFor('projects.index'), text: '← 回到项目列表' })),
                ])],
            };
            if (globalThis.console) console.error('[M5] 渲染失败', error);
        }

        // —— 渲染 ——
        const active = route.name ? activeTab(route.name) : 'projects';
        const chrome = result.chrome ?? (route.name ? chromeFor(route.name) : 'tabbar');

        renderNav(tabbar, active, { withIcons: true });
        tabbar.hidden = chrome !== 'tabbar';         // 表单页隐藏底部 Tab，改用固定操作条
        renderNav(topnav, active, { withIcons: false });

        clear(viewRoot);
        for (const node of (result.nodes ?? []).flat(Infinity)) {
            if (node) viewRoot.appendChild(node);
        }
        renderFlashes();
        if (result.status === 404) doc.documentElement.dataset.status = '404';
        else delete doc.documentElement.dataset.status;

        const heading = viewRoot.querySelector('h1');
        doc.title = titleFor(route.name, result.title ?? (heading ? heading.textContent.trim() : null));

        // 渲染标记：`<body data-route="projects.detail" data-render="7">`。
        // 既是排错时的第一手信息，也让自动化测试能**可靠地等"这一页渲染完了"** ——
        // 只等某个选择器出现是不可靠的（上一页可能也有同名元素，于是测试读到旧 DOM）；
        // 只等 route 名也不够（同一页重复渲染时它不变）。计数器是唯一没有歧义的信号。
        renderSerial += 1;
        doc.body.dataset.route = route.name;
        doc.body.dataset.render = String(renderSerial);

        win.scrollTo?.(0, 0);
        return result;
    }

    /**
     * 串行化的渲染入口。
     *
     * 为什么必须串行：一次交互可能同时触发两条渲染路径 —— 例如保存后 `navigate()`（hashchange）
     * 与 `refresh()`。视图是 **async** 的，两条渲染会交错，先发起的那条可能后写入，
     * 于是屏幕上停着"上一页"（实测症状：保存完跳到项目详情，随后又被旧的渲染覆盖回表单页）。
     * 这里用一个"正在渲染 + 合并后续请求"的小互斥量解决：并发调用只会多渲染一次，
     * 且永远只有一条在写 DOM。
     */
    let rendering = null;
    let queued = false;
    let renderSerial = 0;

    function render() {
        if (rendering) { queued = true; return rendering; }
        rendering = doRender().finally(() => {
            rendering = null;
            if (queued) {
                queued = false;
                render();
            }
        });
        return rendering;
    }

    /** 已经渲染了多少次（单调递增）。自动化测试靠它判断"这一页真的画完了"。 */
    app.renderCount = () => renderSerial;

    async function start() {
        win.addEventListener('hashchange', () => { render(); });
        if (!win.location.hash || win.location.hash === '#') {
            win.location.replace(`#${normalizePath('/projects')}`);
        }
        await render();
        return app;
    }

    app.render = render;
    app.start = start;
    return app;
}

/* --------------------------------------------------------------------------
 * 浏览器入口
 * ------------------------------------------------------------------------ */
export async function boot() {
    const app = createApp({});
    try {
        app.db = await Database.open();
    } catch (error) {
        byId('view').appendChild(h('div.card', null, [
            h('h1', { text: '无法打开本地数据库' }),
            h('p.sub', { text: error.message }),
            h('p.hint', {
                text: '常见原因：浏览器隐私模式禁用了 IndexedDB；或者用 file:// 打开了本页'
                    + '（请改用静态服务器，例如 python -m http.server 8080 --directory web）。',
            }),
        ]));
        if (globalThis.console) console.error('[M5] 打开数据库失败', error);
        return null;
    }
    await app.start();
    globalThis.__APP__ = app;                 // 便于真机排错时在控制台里查状态
    return app;
}

if (globalThis.__APP_BOOT__) {
    boot().catch((error) => {
        flash(`启动失败：${error.message}`, 'error');
        if (globalThis.console) console.error('[M5] 启动失败', error);
    });
}
