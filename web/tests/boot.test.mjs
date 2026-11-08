/* 启动路径（`boot()`）的回归测试。
 *
 * 为什么单独一个文件
 * ------------------
 * 真机上炸过这么一次：页面一打开就是
 *   Chrome:  Cannot read properties of undefined (reading 'read')
 *   Firefox: db is undefined
 * 根因是 `boot()` 里"先 `createApp({})`、再 `app.db = await open()`"——
 * createApp 的参数在构造那一刻就被闭包固定了，后赋值改变不了它，于是 `ctx.db` 永远是 undefined。
 *
 * 而**当时所有测试都是 `createApp({db})`**：参数从一开始就有值，所以全绿。
 * 换句话说：测的是"我搭的这条路径"，不是"用户走的那条路径"。
 * 这个文件只做一件事 —— 走真实入口 `boot()`，并且真的**用**一下数据库。
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import 'fake-indexeddb/auto';
import { IDBFactory } from 'fake-indexeddb';
import { JSDOM } from 'jsdom';

const { boot } = await import('../app/main.js');
const { Database } = await import('../app/db.js');

const INDEX_HTML = new URL('../index.html', import.meta.url);
const { readFileSync } = await import('node:fs');

/** 装一套 jsdom 全局（boot() 用的是裸全局名）。 */
async function installDom() {
    const dom = new JSDOM(readFileSync(INDEX_HTML, 'utf8'), {
        url: 'http://localhost:8080/',
        pretendToBeVisual: true,
    });
    const { window } = dom;
    window.scrollTo = () => {};
    window.URL.createObjectURL = () => 'blob:mock/1';
    window.URL.revokeObjectURL = () => {};
    window.confirm = () => true;
    if (window.HTMLDialogElement) delete window.HTMLDialogElement.prototype.showModal;

    for (const key of ['window', 'document', 'HTMLElement', 'Element', 'Node', 'File',
        'CustomEvent', 'Event', 'URL', 'navigator', 'getComputedStyle', 'HTMLAnchorElement',
        'HTMLDialogElement', 'Image', 'MouseEvent']) {
        if (window[key] === undefined) continue;
        Object.defineProperty(globalThis, key, { value: window[key], configurable: true, writable: true });
    }
    Object.defineProperty(globalThis, 'Blob', {
        value: globalThis.Blob, configurable: true, writable: true,
    });
    return dom;
}

const waitFor = async (predicate, label, timeout = 4000) => {
    const started = Date.now();
    for (;;) {
        let ok = false;
        try { ok = Boolean(predicate()); } catch { ok = false; }
        if (ok) return;
        if (Date.now() - started > timeout) throw new Error(`等待超时：${label}`);
        await new Promise((resolve) => setTimeout(resolve, 5));
    }
};

test('boot()：真实启动路径能用数据库（回归：ctx.db 曾经是 undefined）', async () => {
    await installDom();

    // 每个用例一个干净的库
    const factory = new IDBFactory();
    const app = await boot({ open: { factory, name: `boot_${Math.random()}` } });

    assert.ok(app, 'boot() 应返回 app 实例');
    assert.ok(app.db, 'app.db 必须是打开后的数据库（不是 undefined）');
    assert.equal(globalThis.__APP__, app, 'boot() 应把实例挂到 window.__APP__ 便于排错');

    // 1) 首屏正常渲染成"项目"页，而不是错误卡片
    const view = document.getElementById('view');
    await waitFor(() => view.querySelector('.card h1'), '首屏渲染');
    assert.equal(view.querySelector('.card h1').textContent, '项目');
    assert.ok(!/这一页出错了/.test(view.textContent), '首屏不该进入错误兜底');
    assert.ok(!/无法打开本地数据库/.test(view.textContent), '首屏不该报开库失败');

    // 2) 关键：**真的用一下** ctx.db —— 这是原来炸掉的那条路径。
    //    视图里第一次 read 就是 projects.listWithCounts()，所以首屏能出来已经说明 db 有效；
    //    这里再直接写一条数据，确认它落到同一个库上、并且能被界面读回来。
    const projects = await import('../app/repo/projects.js');
    const { data } = projects.parseForm({ project_no: 'BOOT-1', house_name: '启动测试楼' });
    const id = await projects.create(app.db, data);
    assert.ok(id, '应能通过 app.db 写库');

    // 3) 重新渲染一次，让界面把它读出来（走完整的 ctx → view → repo 链路）。
    //    用 `app.refresh()` 而不是设 location.hash：hash 已经是 `#/projects` 了，
    //    设成同一个值浏览器**不会**发 hashchange（这个坑在 navigate() 里已经处理过）。
    await app.refresh();
    await waitFor(() => /启动测试楼/.test(document.getElementById('view').textContent),
        '项目列表出现刚写入的项目');

    app.db.close();
});

test('boot()：外壳切换 —— 列表页显示底部 Tab，表单页隐藏它并挂上 has-action-bar', async () => {
    await installDom();
    const factory = new IDBFactory();
    const app = await boot({ open: { factory, name: `boot_${Math.random()}` } });
    assert.ok(app);

    const tabbar = document.getElementById('tabbar');
    const body = document.body;

    // 列表页：底部 Tab 显示、没有操作条
    await waitFor(() => body.dataset.route === 'projects.index', '项目列表渲染');
    assert.equal(tabbar.hidden, false, '列表页应显示底部 Tab');
    assert.equal(body.classList.contains('has-action-bar'), false, '列表页不该挂 has-action-bar');

    // 表单页：Tab 隐藏 + body 挂上 has-action-bar（桌面端靠它补回正文留白）
    window.location.hash = '#/projects/new';
    await waitFor(() => body.dataset.route === 'projects.new', '表单页渲染');
    assert.equal(tabbar.hidden, true, '表单页必须隐藏底部 Tab（否则会盖住操作条）');
    assert.equal(body.classList.contains('has-action-bar'), true,
        '表单页必须在 body 上挂 has-action-bar —— 桌面端 ≥960px 的正文留白靠它');
    assert.ok(document.querySelector('.action-bar'), '表单页必须有底部操作条');

    // 回到列表页要能还原（不能一次性地把 Tab 关掉）
    window.location.hash = '#/projects';
    await waitFor(() => body.dataset.route === 'projects.index', '回列表页');
    assert.equal(tabbar.hidden, false, '回列表页应重新显示底部 Tab');
    assert.equal(body.classList.contains('has-action-bar'), false);

    app.db.close();
});
