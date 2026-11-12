/* M5 前端的端到端测试：在 jsdom 里加载**真实的 index.html + main.js**，
 * 用 fake-indexeddb 当数据库，走通「录入 → 导出 → 下载」整条链路。
 *
 * 为什么用真实 index.html 而不是手搭一个 DOM 夹具
 * ----------------------------------------------
 * 夹具测的是"我以为的壳"，真实文件测的是"用户拿到的壳"。启动路径（模块加载、hash 路由、
 * 导航渲染、IndexedDB 打开、错误兜底）恰恰是最容易在夹具里被绕过的一段 ——
 * 而它一旦坏了，用户看到的是**白屏**，不是某个局部功能失效。
 *
 * jsdom 的五处能力缺口，都在 `setupDom()` 里显式补上（每处都有理由）：
 *   1. `URL.createObjectURL` 未实现 → 用计数器桩替代（缩略图/大图只关心"有没有 URL"）；
 *   2. `<dialog>.showModal` 未实现 → 走 `confirmDialog()` 的原生 `confirm` 降级分支；
 *   3. `HTMLAnchorElement.click()` 会触发"未实现的导航" → 桩掉并**记录下载**（导出就靠它断言）；
 *   4. `window.scrollTo` 未实现 → 空函数；
 *   5. 没有 canvas / createImageBitmap → 注入假编解码器（与闸门 A 的替身同一个思路）。
 *
 * 关于等待：视图是 async 的，而且渲染是**串行化**的（main.js 里的小互斥量）。
 * 所以测试一律用 `waitFor()` 等"用户可见的结果"，而不是数心跳 —— 数心跳的测试在
 * 机器慢一点的时候就会变成假红（这一版踩过一次）。
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import 'fake-indexeddb/auto';
import { IDBFactory } from 'fake-indexeddb';
import { JSDOM } from 'jsdom';

import { Database } from '../app/db.js';
import { STORE } from '../app/db.js';
import { createApp } from '../app/main.js';
import { CONFIG } from '../app/config.js';
import { PRODUCT } from '../app/product.js';
import { clearFlashes } from '../app/ui/dialog.js';

const ROOT = new URL('../../', import.meta.url);
const INDEX_HTML = readFileSync(new URL('web/index.html', ROOT), 'utf8');
const BASE_DOCX = new Uint8Array(readFileSync(new URL('webapp/resources/report_base.docx', ROOT)));

/**
 * Node 自己的 Blob / File，**必须在覆盖全局之前抓下来**。
 *
 * 为什么：jsdom 的 `window.Blob` / `window.File` 与 Node 的不是同一个类，而 fake-indexeddb 的
 * 结构化克隆认不出前者（克隆结果退化成普通对象），JSZip 也不认它。
 * 这是**测试环境**的限制，不是产品缺陷 —— 真实浏览器里只有一种 Blob。
 * 所以测试里造的文件一律用 Node 的 File。
 */
const NativeBlob = globalThis.Blob;
const NativeFile = globalThis.File;

/* --------------------------------------------------------------------------
 * 环境
 * ------------------------------------------------------------------------ */

/** 假编解码器：解码尺寸给定，编码返回一段可 arrayBuffer 的假 JPEG。 */
function fakeCodec({ width = 1600, height = 1200 } = {}) {
    return {
        decode: async () => ({ source: {}, width, height, orientation: 1 }),
        createCanvas: (canvasWidth, canvasHeight) => ({
            getContext: () => ({
                save() {}, restore() {}, setTransform() {}, fillRect() {}, fillStyle: '', drawImage() {},
            }),
            convertToBlob: async () => new NativeBlob(
                [new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46])],
                { type: 'image/jpeg' }),
        }),
    };
}

async function setupDom({ confirm = true } = {}) {
    const dom = new JSDOM(INDEX_HTML, { url: 'http://localhost:8080/', pretendToBeVisual: true });
    const { window } = dom;

    // ① objectURL：jsdom 没有实现
    const revoked = [];
    let urlCounter = 0;
    window.URL.createObjectURL = () => `blob:mock/${(urlCounter += 1)}`;
    window.URL.revokeObjectURL = (url) => { revoked.push(url); };

    // ② <dialog>：jsdom 未实现 showModal → 走 confirmDialog 的原生 confirm 降级。
    //    ⚠️ 用**可变的共享对象**表达"用户点了什么"，而不是每次替换 window.confirm ——
    //    globalThis.confirm 是本文件下面 defineProperty 出来的**另一个属性**，
    //    替换 window.confirm 不会影响它（踩过一次：确认框永远返回 true）。
    const confirmed = [];
    const answer = { value: confirm };
    window.confirm = (message) => { confirmed.push(message); return answer.value; };
    if (window.HTMLDialogElement) delete window.HTMLDialogElement.prototype.showModal;

    // ③ 下载：jsdom 的 <a>.click() 会报"未实现的导航"
    const downloads = [];
    window.HTMLAnchorElement.prototype.click = function click() {
        if (this.download) downloads.push({ filename: this.download, href: this.href });
    };

    // ④ 滚动：jsdom 未实现（每次渲染都会调一次）
    window.scrollTo = () => {};

    // 把 jsdom 的浏览器全局接到 Node 的 globalThis 上（模块里用的是裸全局名）。
    // ⚠️ 必须用 defineProperty：Node 25 的 `navigator` 等全局是**只读 getter**，
    // 直接赋值会抛 "Cannot set property navigator of #<Object> which has only a getter"。
    for (const key of ['window', 'document', 'HTMLElement', 'Element', 'Node', 'File',
        'CustomEvent', 'Event', 'URL', 'navigator', 'getComputedStyle', 'HTMLAnchorElement',
        'HTMLDialogElement', 'Image', 'MouseEvent', 'KeyboardEvent']) {
        if (window[key] === undefined) continue;
        Object.defineProperty(globalThis, key, { value: window[key], configurable: true, writable: true });
    }
    // Blob 例外：显式用 Node 的（见 NativeBlob 的说明）
    Object.defineProperty(globalThis, 'Blob', { value: NativeBlob, configurable: true, writable: true });
    Object.defineProperty(globalThis, 'confirm', {
        value: window.confirm, configurable: true, writable: true,
    });

    return { dom, window, downloads, confirmed, revoked, answer };
}

async function setupApp(options = {}) {
    const dom = await setupDom(options);
    // 提示条队列是**模块级**的（跨渲染保活是它的设计目标），所以在测试之间必须清掉，
    // 否则上一个用例的提示会漏进下一个用例（模块级状态是这套测试唯一的共享点）。
    clearFlashes();
    const db = await Database.open({ factory: new IDBFactory(), name: `ui_${Math.random()}` });
    const app = createApp({
        db,
        document: dom.window.document,
        window: dom.window,
        storage: null,                                   // 配额信息不可得 → 走"未知"分支
        pipeline: fakeCodec(),
        baseDocxBytes: BASE_DOCX,
    });
    return { ...dom, db, app };
}

/** 走一遍真实启动流程（打开库、渲染首屏、装上 hashchange）。 */
async function bootApp(options = {}) {
    const env = await setupApp(options);
    await env.app.start();
    return env;
}

/* --------------------------------------------------------------------------
 * 等待与交互助手
 * ------------------------------------------------------------------------ */

const $ = (window, selector) => window.document.querySelector(selector);
const $$ = (window, selector) => Array.from(window.document.querySelectorAll(selector));

/** 等一个条件成立（默认 3 秒超时）。测试一律等"结果"，不等心跳。 */
async function waitFor(window, predicate, { timeout = 3000, label = '条件' } = {}) {
    const started = Date.now();
    for (;;) {
        let ok = false;
        try {
            ok = Boolean(predicate());
        } catch {
            ok = false;
        }
        if (ok) return true;
        if (Date.now() - started > timeout) throw new Error(`等待超时：${label}`);
        await new Promise((resolve) => window.setTimeout(resolve, 4));
    }
}

/** 等页面渲染到某个选择器出现。 */
function waitForSelector(window, selector) {
    return waitFor(window, () => $(window, selector), { label: `选择器 ${selector}` });
}

/**
 * 切路由并等**目标页面真的渲染完**。
 *
 * 等待信号用 `main.js` 写下的**渲染计数器** `<body data-render="N">`，不用选择器：
 *   - 只等"某个选择器出现"不可靠 —— 很多 class（`.head-actions` / `table.grid` / `.card`）
 *     在上一页也有，`waitFor` 会立刻返回，测试于是读到**上一页的 DOM**
 *     （表现为"明明删了图片，详情页却还显示图片"这种看起来像产品 bug 的假红）；
 *   - 只等 `data-route` 也不够 —— 同一页重复渲染时它不变（例如"删完图片再进同一个详情页"）。
 */
async function goto(window, hash, routeName = null) {
    const before = renderMark(window);
    if (window.location.hash === hash) {
        // hash 没变就不会有 hashchange —— 手动补一次，模拟"重新进入当前页"
        window.dispatchEvent(new window.Event('hashchange'));
    } else {
        window.location.hash = hash;
    }
    await waitForRender(window, before, hash);
    if (routeName) {
        await waitFor(window, () => window.document.body.dataset.route === routeName,
            { label: `渲染完成 ${routeName}` });
    }
}

/** 当前渲染计数。 */
function renderMark(window) {
    return Number(window.document.body.dataset.render ?? 0);
}

/** 等一次新的渲染完成（计数器严格增长）。 */
async function waitForRender(window, before = renderMark(window), label = '渲染') {
    await waitFor(window, () => renderMark(window) > before, { label: `等待渲染（${label}）` });
}

/** 填一个字段并触发 input/change（让交互层能感知）。 */
function fill(window, element, value) {
    element.value = value;
    element.dispatchEvent(new window.Event('input', { bubbles: true }));
    element.dispatchEvent(new window.Event('change', { bubbles: true }));
    return element;
}

async function click(window, element) {
    element.dispatchEvent(new window.MouseEvent('click', { bubbles: true, cancelable: true }));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
}

/** 提交表单（jsdom 里直接派发 submit 事件最可靠）。 */
async function submit(window, form) {
    form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
}

/**
 * 提交表单并等这次提交引发的那一屏重画完成。
 * 保存后跳页的场景一律用它 —— 只看 hash 会在页面还没重画时就读到旧 DOM。
 */
async function submitAndWait(window, form, label = '提交后重画') {
    const before = renderMark(window);
    await submit(window, form);
    await waitForRender(window, before, label);
}

/** 给 file input 塞一个文件（jsdom 没有 DataTransfer，只能 defineProperty）。 */
function attachFile(window, input, file) {
    Object.defineProperty(input, 'files', { value: [file], configurable: true, writable: false });
    input.dispatchEvent(new window.Event('change', { bubbles: true }));
    return file;
}

/** 一个"可被结构化克隆、也能进 zip"的 JPEG 文件（用 Node 的 File，理由见 NativeBlob）。 */
function jpegFile(_window, name = '隐患照片.jpg') {
    return new NativeFile([new Uint8Array([0xff, 0xd8, 0xff])], name, { type: 'image/jpeg' });
}

/* --------------------------------------------------------------------------
 * 1. 启动与路由
 * ------------------------------------------------------------------------ */

test('启动：/ → 项目 Tab，底部与顶栏各有 3 个导航项，无 hash 时不白屏', async () => {
    const { window, db } = await bootApp();

    assert.equal(window.location.hash, '#/projects');
    assert.equal($(window, '#view .card h1').textContent, '项目');
    assert.equal($$(window, '#tabbar .nav-item').length, 3);
    assert.equal($$(window, '#topnav .nav-item').length, 3);
    // 当前 Tab 高亮 + aria-current（无障碍与视觉同一来源）
    const active = $$(window, '#tabbar .nav-item.active');
    assert.equal(active.length, 1);
    assert.equal(active[0].getAttribute('aria-current'), 'page');
    assert.match(active[0].textContent, /项目/);
    assert.match(window.document.title, /项目/);
});

test('路由：unknown → 回落到项目 Tab（不留在空页面）', async () => {
    const { window, db } = await bootApp();
    window.location.hash = '#/nope/123';
    await waitFor(window, () => window.location.hash === '#/projects');
    await waitForSelector(window, '#view .card h1');
    assert.equal($(window, '#view .card h1').textContent, '项目');
});

test('路由：表单页隐藏底部 Tab，改用固定操作条', async () => {
    const { window, db } = await bootApp();

    await goto(window, '#/projects/new', 'projects.new');
    assert.equal($(window, '#tabbar').hidden, true, '表单页不该显示底部 Tab');
    assert.ok($(window, '.action-bar'), '表单页必须有底部操作条');

    await goto(window, '#/me', 'me.index');
    assert.equal($(window, '#tabbar').hidden, false, '浏览类页面要显示底部 Tab');
    assert.equal($(window, '.action-bar'), null);
});

/* --------------------------------------------------------------------------
 * 2. 录入：项目 → 检测记录 → 缺陷报告（含图片）
 * ------------------------------------------------------------------------ */

test('录入链路：建项目 → 加检测记录 → 加缺陷报告（含图片）→ 三处都能读到', async () => {
    const { window, db, downloads } = await bootApp();

    /* --- 项目 --- */
    await goto(window, '#/projects/new', 'projects.new');
    const projectForm = $(window, '#project-form');
    fill(window, projectForm.querySelector('[name="project_no"]'), 'TEST-01');
    fill(window, projectForm.querySelector('[name="house_name"]'), '真机验证楼');
    fill(window, projectForm.querySelector('[name="house_address"]'), '深圳市南山区');
    await submit(window, projectForm);

    // ⚠️ 判断"跳转成功了"不能只看 hash —— hash 是同步变的，页面可能还没重画。
    // 这里等的是**渲染计数器增长**（见 goto 的说明）。
    const beforeDetail = renderMark(window);
    await waitFor(window, () => /^#\/projects\/\d+$/.test(window.location.hash), { label: '跳回项目详情' });
    await waitForRender(window, beforeDetail, '项目详情');
    const projectId = Number(window.location.hash.split('/').pop());
    assert.match($(window, '#view').textContent, /真机验证楼/);
    assert.match($(window, '#flashes').textContent, /项目已创建/);

    /* --- 检测记录 --- */
    await goto(window, `#/projects/${projectId}/records/new`, 'records.choose');
    assert.match($(window, '#view').textContent, /选择检测记录模板/);

    await goto(window, `#/projects/${projectId}/records/new/column`, 'records.new');
    const recordForm = $(window, '#record-form');
    // 首行默认展开（UI 设计 2.6：新建时唯一那行展开并聚焦）
    assert.equal($(window, '#face-list details.face-row').open, true);

    fill(window, recordForm.querySelector('[name="floor"]'), '六层');
    fill(window, recordForm.querySelector('[name="member_position"]'), '1');
    fill(window, recordForm.querySelector('[name="size_result"]'), '63x164');
    fill(window, recordForm.querySelector('[name="requirement_index"]'), '0');
    fill(window, recordForm.querySelector('[name="face_0"]'), 'B');
    ['2.99', '3.02', '3.01', '3.01', '2.99'].forEach((value, index) => {
        fill(window, recordForm.querySelector(`[name="value_0_${index + 1}"]`), value);
    });
    // 交互层的即时反馈：5 格有效 → 绿点 + 进度 5/5 + 最小值 2.99
    assert.equal($(window, '#face-list .face-dot').className, 'face-dot state-done');
    assert.equal($(window, '#face-list .face-count').textContent, '5/5');
    assert.equal($(window, '#face-list .min-value').textContent, '2.99');

    await submitAndWait(window, recordForm, '保存检测记录');
    await waitFor(window, () => window.location.hash === `#/projects/${projectId}`, { label: '保存后回项目详情' });
    await waitFor(window, () => /六层/.test($(window, '#view').textContent), { label: '项目详情出现新记录' });
    const detailText = $(window, '#view').textContent;
    assert.match(detailText, /六层 · 构件 1/);
    assert.match(detailText, /立柱 1 条/);
    assert.match(detailText, /63×164/, '尺寸结果按规则归一成 ×');
    assert.match(detailText, /2\.99/, '最小值由数据层重算');

    /* --- 缺陷报告（含图片） --- */
    await goto(window, '#/reports/new', 'reports.new');
    const defectForm = $(window, '#defect-form');
    attachFile(window, defectForm.querySelector('#image'), jpegFile(window));
    fill(window, defectForm.querySelector('[name="defect_type"]'), '密封胶开裂');
    fill(window, defectForm.querySelector('[name="project_part"]'), '东立面三层 1# 立柱');
    fill(window, defectForm.querySelector('[name="rectification_plan"]'), '更换密封胶');
    fill(window, defectForm.querySelector('[name="project_id"]'), String(projectId));
    await submitAndWait(window, defectForm, '保存缺陷报告');

    await waitFor(window, () => /^#\/reports\/\d+$/.test(window.location.hash), { label: '报告保存后跳详情' });
    const reportText = $(window, '#view').textContent;
    assert.match(reportText, /密封胶开裂/);
    assert.match(reportText, /隐患照片\.jpg/, '原文件名必须可追溯');

    /* --- 报告列表：缩略图来自 IndexedDB 里的 thumb（不是现压原图） --- */
    await goto(window, '#/reports', 'reports.index');
    await waitForSelector(window, '.report-thumb img');
    assert.match($(window, '#view').textContent, /密封胶开裂/);

    /* --- 项目详情：关联报告计数与「附加 N 份并导出」 --- */
    await goto(window, `#/projects/${projectId}`, 'projects.detail');
    const projectText = $(window, '#view').textContent;
    assert.match(projectText, /关联缺陷报告/);
    assert.match(projectText, /附加 1 份并导出/);

    assert.equal(downloads.length, 0, '这一轮不该触发任何下载');
});

/* --------------------------------------------------------------------------
 * 3. 导出 → 下载
 * ------------------------------------------------------------------------ */

test('导出：点「附加 N 份并导出」→ 生成 docx 并触发下载（文件名按规则）', async () => {
    const { window, db, downloads } = await bootApp();
    const projectId = await seedOneProject(window);

    await goto(window, `#/projects/${projectId}`, 'projects.detail');
    const button = $$(window, '.head-actions button')
        .find((item) => /附加 1 份并导出/.test(item.textContent));
    assert.ok(button, '应有关联报告时的二选一按钮');
    await click(window, button);
    await waitFor(window, () => downloads.length === 1, { label: '导出触发下载' });

    assert.equal(downloads[0].filename, 'TEST-01_真机验证楼_检测报告.docx');
    assert.match(downloads[0].href, /^blob:/);
    assert.match($(window, '#flashes').textContent, /已导出/);

    /* 产物本身：能解出 zip，且含附页（表格 + 图片） */
    const { buildProjectReport } = await import('../app/export.js');
    const result = await buildProjectReport(db, projectId, {
        withAttachments: true, baseDocxBytes: BASE_DOCX, pipeline: fakeCodec(),
    });
    const JSZip = (await import('jszip')).default;
    const zip = await JSZip.loadAsync(result.bytes);
    const xml = await zip.file('word/document.xml').async('string');
    assert.match(xml, /检测报告附页（1\/1）/, '附页应随项目报告一起导出');
    assert.match(xml, /<w:drawing>/, '附页里的隐患图片应被嵌入');
    assert.match(xml, /幕墙立柱截面尺寸检测结果/);
});

test('导出：空项目给出可读错误，不产生下载', async () => {
    const { window, db, downloads } = await bootApp();
    await goto(window, '#/projects/new', 'projects.new');
    const form = $(window, '#project-form');
    fill(window, form.querySelector('[name="project_no"]'), 'EMPTY-01');
    fill(window, form.querySelector('[name="house_name"]'), '空项目');
    await submit(window, form);
    await waitFor(window, () => /^#\/projects\/\d+$/.test(window.location.hash));
    await waitFor(window, () => window.document.body.dataset.route === 'projects.detail',
        { label: '项目详情渲染完成' });

    const button = $$(window, '.head-actions button').find((item) => item.textContent === '导出 Word');
    await click(window, button);
    await waitFor(window, () => /还没有检测记录/.test($(window, '#flashes').textContent),
        { label: '空项目导出提示' });

    assert.equal(downloads.length, 0);
});

/* --------------------------------------------------------------------------
 * 4. 校验与拦截（UI 设计的核心承诺）
 * ------------------------------------------------------------------------ */

test('非法读数：标红 + 警告灯 + 禁用保存 + 阻止提交', async () => {
    const { window, db } = await bootApp();
    const projectId = await seedProject(window);

    await goto(window, `#/projects/${projectId}/records/new/column`, 'records.new');
    const form = $(window, '#record-form');
    fill(window, form.querySelector('[name="floor"]'), '六层');
    fill(window, form.querySelector('[name="member_position"]'), '1');
    fill(window, form.querySelector('[name="face_0"]'), 'B');
    fill(window, form.querySelector('[name="value_0_1"]'), 'abc');

    assert.equal(form.querySelector('[name="value_0_1"]').classList.contains('is-invalid'), true);
    assert.equal($(window, '#face-list .face-lamp').hidden, false, '折叠态也要看得见警告灯');
    assert.equal($(window, '#face-list .lamp-count').textContent, '1');
    assert.ok($(window, '#save-record'), '操作条里的保存按钮必须能被交互层找到（冻结契约）');
    assert.equal($(window, '#save-record').disabled, true, '有非法读数时必须禁用保存');
    assert.match($(window, '#form-status').textContent, /不是有效数字/,
        '操作条里必须写明原因（长表单里提示不能出现在屏幕外）');

    // 提交被拦截：不跳转、不重画、展开非法行
    //
    // 这里用"立即断言 + 渲染计数不变"，而不是 waitFor 等那段文字：跨用例共享 globalThis 是
    // 这套测试唯一的软肋（上一个用例遗留的异步回调可能写进新 document），等一个可变文本
    // 会把测试框架的噪音误判成产品缺陷。产品契约本身在上面几行已经逐条断言过了。
    const beforeBlocked = renderMark(window);
    await submit(window, form);
    assert.equal(renderMark(window), beforeBlocked,
        `被拦截时不该发生跳转/重画（hash=${window.location.hash}`
        + ` route=${window.document.body.dataset.route}`
        + ` status=${JSON.stringify($(window, '#form-status')?.textContent)}）`);
    assert.match(window.location.hash, /records\/new\/column$/);
    assert.equal($(window, '#face-list details.face-row').open, true, '被拦截时应展开非法行');
    assert.equal($(window, '#save-record').disabled, true);
});

test('必填项缺失：就地标红并给出字段级提示（同 Flask 的回填语义）', async () => {
    const { window, db } = await bootApp();
    await goto(window, '#/projects/new', 'projects.new');
    const form = $(window, '#project-form');
    fill(window, form.querySelector('[name="project_no"]'), 'X-1');
    await submit(window, form);                       // 缺 house_name

    await waitFor(window, () => form.querySelector('.field-error'), { label: '字段级错误提示' });
    assert.match(window.location.hash, /projects\/new$/);
    assert.equal(form.querySelector('[name="house_name"]').classList.contains('input-error'), true);
    assert.match(form.querySelector('.field-error').textContent, /房屋名称不能为空/);
});

test('项目编号重复：唯一约束被翻译成字段级错误（IntegrityError → 就地提示）', async () => {
    const { window, db } = await bootApp();
    await seedProject(window);

    await goto(window, '#/projects/new', 'projects.new');
    const form = $(window, '#project-form');
    fill(window, form.querySelector('[name="project_no"]'), 'TEST-01');
    fill(window, form.querySelector('[name="house_name"]'), '另一个楼');
    await submit(window, form);

    await waitFor(window, () => form.querySelector('.field-error'), { label: '唯一约束提示' });
    assert.match(window.location.hash, /projects\/new$/);
    assert.match(form.querySelector('.field-error').textContent, /已存在|唯一|重复/);
});

/* --------------------------------------------------------------------------
 * 5. 删除（应用内确认弹窗）
 * ------------------------------------------------------------------------ */

test('删除报告：先弹确认（文案写明会一并删图片），取消则不删', async () => {
    const { window, db, confirmed, answer } = await bootApp();
    await seedOneProject(window);

    await goto(window, '#/reports', 'reports.index');
    await waitForSelector(window, '.report-actions button.danger-link');

    // 取消：数据不动
    answer.value = false;
    await click(window, $(window, '.report-actions button.danger-link'));
    await waitFor(window, () => confirmed.length > 0, { label: '弹出确认框' });
    assert.match(confirmed.at(-1), /隐患图片会一并删除/);
    assert.match($(window, '#view').textContent, /密封胶开裂/, '取消后报告还在');

    // 确认：删除并刷新列表
    answer.value = true;
    await click(window, $(window, '.report-actions button.danger-link'));
    await waitFor(window, () => /还没有报告/.test($(window, '#view').textContent),
        { label: '删除后列表变空' });
});

/* --------------------------------------------------------------------------
 * 6. 数据管理页（M5 新增）
 * ------------------------------------------------------------------------ */

test('数据管理：显示概览、给出持久化提示、导入导出按钮齐全', async () => {
    const { window, db } = await bootApp();
    await seedOneProject(window);

    await goto(window, '#/me/data', 'me.data');
    const text = $(window, '#view').textContent;
    assert.match(text, /数据存在这台设备的浏览器里/);
    assert.match(text, /导出备份/);
    assert.match(text, /覆盖当前全部数据/);
    assert.match(text, /申请持久化授权/);
    assert.match(text, /重建全部缩略图/);
    // 概览数字与数据对得上
    assert.match(text, /项目\s*1 个/);
    assert.match(text, /缺陷报告\s*1 份/);
});

test('数据管理：导出备份 → 下载 zip；没选文件时导入给出提示', async () => {
    const { window, db, downloads } = await bootApp();
    await seedOneProject(window);

    await goto(window, '#/me/data', 'me.data');

    const exportButton = $$(window, '#view button').find((item) => /导出备份/.test(item.textContent));
    await click(window, exportButton);
    await waitFor(window, () => downloads.length === 1, { label: '备份触发下载' });
    assert.match(downloads[0].filename, /^幕墙检测备份_\d{8}_\d{4}\.zip$/);
    assert.match($(window, '#flashes').textContent, /已导出备份/);

    // 导入：没选文件时应给出提示而不是崩
    const importButton = $$(window, '#view button').find((item) => /导入备份/.test(item.textContent));
    await click(window, importButton);
    await waitFor(window, () => /先选择一个备份文件/.test($(window, '#flashes').textContent),
        { label: '未选文件的提示' });
});

test('数据管理：清除全部报告（确认后图片一并删除）', async () => {
    const { window, db, answer } = await bootApp();
    await seedOneProject(window);

    await goto(window, '#/me/data', 'me.data');
    const clearButton = $$(window, '#view button').find((item) => item.textContent === '清除全部报告');
    assert.ok(clearButton, '数据管理页必须有「清除全部报告」（不可恢复，所以要二次确认）');

    // 先取消：数据不动
    answer.value = false;
    await click(window, clearButton);
    assert.match($(window, '#view').textContent, /清除全部 1 份缺陷报告/);
    let rows = await db.read([STORE.images], (ctx) => ctx.getAll(STORE.images));
    assert.equal(rows.length, 1, '取消后图片还在');

    // 再确认：报告与图片一并删除
    answer.value = true;
    await click(window, clearButton);
    await waitFor(window, () => /已清除全部报告：1 份/.test($(window, '#flashes').textContent),
        { label: '清除回执' });

    rows = await db.read([STORE.images], (ctx) => ctx.getAll(STORE.images));
    assert.equal(rows.length, 0, '隐患图片必须一并删除');
    await waitFor(window, () => /没有可清除的报告/.test($(window, '#view').textContent));
});

/* --------------------------------------------------------------------------
 * 7. 图片缺失降级
 * ------------------------------------------------------------------------ */

test('图片缺失：报告详情显示降级文案，项目导出仍然成功', async () => {
    const { window, db, downloads } = await bootApp();
    const projectId = await seedOneProject(window);

    // 手动把图片记录删掉（模拟"文件不在了"）
    const rows = await db.read([STORE.images], (ctx) => ctx.getAll(STORE.images));
    await db.write([STORE.images], (ctx) => ctx.delete(STORE.images, rows[0].id));

    await goto(window, '#/reports/1', 'reports.detail');
    assert.match($(window, '#view').textContent, /图片文件缺失/);

    await goto(window, `#/projects/${projectId}`, 'projects.detail');
    const button = $$(window, '.head-actions button').find((item) => /附加 1 份并导出/.test(item.textContent));
    await click(window, button);
    await waitFor(window, () => downloads.length === 1, { label: '图片缺失也能导出' });
    assert.match($(window, '#flashes').textContent, /已导出/);
});

/* --------------------------------------------------------------------------
 * 8. 一致性
 * ------------------------------------------------------------------------ */

test('配置：默认风险等级与表单默认值一致（防止两处硬编码走样）', async () => {
    const { window, db } = await bootApp();
    await goto(window, '#/reports/new', 'reports.new');
    const checked = $(window, '[name="risk_level"]:checked');
    assert.equal(checked.value, CONFIG.DEFAULT_RISK_LEVEL);
});

/* --------------------------------------------------------------------------
 * 9. 交付版：页面级自检（版本号从 product.js 取，不写死）
 * ------------------------------------------------------------------------ */

test('关于页：产品名称 / 版本 / 出品方，不再有开发期的模块进度', async () => {
    const { window } = await bootApp();
    await goto(window, '#/about', 'pages.about');
    const text = $(window, '#view').textContent;

    assert.match(text, new RegExp(PRODUCT.name));
    assert.match(text, new RegExp(`v${PRODUCT.version.replace(/\./g, '\\.')}`));
    assert.match(text, /中冶建筑研究总院/);

    // 开发/课程痕迹（这条是交付前专门加的：它们不影响功能，所以只有"盯着看"才会发现）
    for (const [pattern, why] of [
        [/模块进度/, '模块进度表'],
        [/\bM[0-5]\b/, '里程碑编号'],
        [/Capstone|NYU/i, '课程/学校信息'],
        [/Zeyu|结构工程部/i, '开发者名字/部门'],
        [/Flask|python/i, '参考实现的运行说明'],
    ]) {
        assert.doesNotMatch(text, pattern, `关于页里还有${why}`);
    }
});

test('个人信息配置：改名字后「我的」页与新建报告都用新署名', async () => {
    const { window } = await bootApp();

    await goto(window, '#/me', 'me.index');
    assert.match($(window, '#view').textContent, /检测员/, '默认报告人来自 product.js');
    const entry = $$(window, '#view a').find((item) => /个人信息配置/.test(item.textContent));
    assert.ok(entry, '「我的」页必须有个人信息配置入口');
    assert.equal(entry.getAttribute('href'), '#/me/profile');

    await goto(window, '#/me/profile', 'me.profile');
    const form = $(window, '#profile-form');
    assert.ok(form, '个人信息配置页应有表单');
    assert.equal($(window, '#tabbar').hidden, true, '表单页要隐藏底部 Tab');
    fill(window, form.querySelector('[name="reporter_name"]'), '张三');
    fill(window, form.querySelector('[name="reporter_department"]'), '幕墙检测二部');
    await submitAndWait(window, form, '保存个人信息');

    await waitFor(window, () => window.location.hash === '#/me', { label: '保存后回到我的' });
    const meText = $(window, '#view').textContent;
    assert.match(meText, /张三/);
    assert.match(meText, /幕墙检测二部/);
    assert.match($(window, '#flashes').textContent, /个人信息已保存/);

    // 真正的验证点：**新**填写的缺陷报告用的是新署名（旧代码在这里写死开发者）
    await goto(window, '#/reports/new', 'reports.new');
    assert.match($(window, '#view').textContent, /张三（幕墙检测二部）/,
        '缺陷填报页的「报告人」应显示当前个人信息');

    const defectForm = $(window, '#defect-form');
    attachFile(window, defectForm.querySelector('#image'), jpegFile(window));
    fill(window, defectForm.querySelector('[name="defect_type"]'), '密封胶开裂');
    fill(window, defectForm.querySelector('[name="project_part"]'), '东立面三层 1# 立柱');
    fill(window, defectForm.querySelector('[name="rectification_plan"]'), '更换密封胶');
    await submitAndWait(window, defectForm, '保存报告');
    await waitFor(window, () => /^#\/reports\/\d+$/.test(window.location.hash));

    assert.match($(window, '#view').textContent, /张三（幕墙检测二部）/,
        '保存下来的报告里也应是新署名（写入时快照）');
});

/* --------------------------------------------------------------------------
 * 夹具：建一个"有 1 条检测记录 + 1 份带图报告"的项目
 * ------------------------------------------------------------------------ */

async function seedProject(window) {
    await goto(window, '#/projects/new', 'projects.new');
    const form = $(window, '#project-form');
    fill(window, form.querySelector('[name="project_no"]'), 'TEST-01');
    fill(window, form.querySelector('[name="house_name"]'), '真机验证楼');
    await submitAndWait(window, form, '保存项目');
    await waitFor(window, () => /^#\/projects\/\d+$/.test(window.location.hash));
    return Number(window.location.hash.split('/').pop());
}

async function seedOneProject(window) {
    const projectId = await seedProject(window);

    await goto(window, `#/projects/${projectId}/records/new/column`, 'records.new');
    const recordForm = $(window, '#record-form');
    fill(window, recordForm.querySelector('[name="floor"]'), '六层');
    fill(window, recordForm.querySelector('[name="member_position"]'), '1');
    fill(window, recordForm.querySelector('[name="face_0"]'), 'B');
    ['2.99', '3.02', '3.01', '3.01', '2.99'].forEach((value, index) => {
        fill(window, recordForm.querySelector(`[name="value_0_${index + 1}"]`), value);
    });
    await submitAndWait(window, recordForm, '保存记录');
    await waitFor(window, () => window.location.hash === `#/projects/${projectId}`);

    await goto(window, '#/reports/new', 'reports.new');
    const defectForm = $(window, '#defect-form');
    attachFile(window, defectForm.querySelector('#image'), jpegFile(window));
    fill(window, defectForm.querySelector('[name="defect_type"]'), '密封胶开裂');
    fill(window, defectForm.querySelector('[name="project_part"]'), '东立面三层 1# 立柱');
    fill(window, defectForm.querySelector('[name="rectification_plan"]'), '更换密封胶');
    fill(window, defectForm.querySelector('[name="project_id"]'), String(projectId));
    await submitAndWait(window, defectForm, '保存报告');
    await waitFor(window, () => /^#\/reports\/\d+$/.test(window.location.hash));

    return projectId;
}
