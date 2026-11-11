/* 检测记录的**编辑**路径。
 *
 * 为什么单独一个文件
 * ------------------
 * 真机上点项目详情里的「编辑」直接崩：`Cannot read properties of undefined (reading '0')`。
 * 根因是 `records.form` 把 `getReadings()` 的返回值当成已经格式化好的视图：
 *   · `getReadings()` 返回的是 **thickness_readings 的原始行**（字段是 `value_1..value_5`）；
 *   · 表单要的是 `readings_text`（已经格式化过的两位小数字符串）—— 必须过 `faceView()`。
 * 于是 `readings` 是 undefined，`readings[offset]` 立刻抛错。
 *
 * 而**当时所有 UI 测试都只覆盖了"新建"路径**（`#/projects/:id/records/new/:template`），
 * `#/records/:id/edit` 一次都没走过 —— 又是一次"测了我搭的路径，不是用户走的路径"。
 * 这个文件把编辑路径完整走一遍：预填 → 改值 → 保存 → 回详情看到新值。
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import 'fake-indexeddb/auto';
import { IDBFactory } from 'fake-indexeddb';
import { JSDOM } from 'jsdom';

import { Database } from '../app/db.js';
import { createApp } from '../app/main.js';

const ROOT = new URL('../../', import.meta.url);
const INDEX_HTML = readFileSync(new URL('web/index.html', ROOT), 'utf8');
const BASE_DOCX = new Uint8Array(readFileSync(new URL('webapp/resources/report_base.docx', ROOT)));
const NativeBlob = globalThis.Blob;

const $ = (window, selector) => window.document.querySelector(selector);

async function waitFor(window, predicate, label, timeout = 4000) {
    const started = Date.now();
    for (;;) {
        let ok = false;
        try { ok = Boolean(predicate()); } catch { ok = false; }
        if (ok) return;
        if (Date.now() - started > timeout) throw new Error(`等待超时：${label}`);
        await new Promise((resolve) => window.setTimeout(resolve, 5));
    }
}

async function setup() {
    const dom = new JSDOM(INDEX_HTML, { url: 'http://localhost:8080/', pretendToBeVisual: true });
    const { window } = dom;
    window.scrollTo = () => {};
    window.URL.createObjectURL = () => 'blob:mock/1';
    window.URL.revokeObjectURL = () => {};
    window.confirm = () => true;
    if (window.HTMLDialogElement) delete window.HTMLDialogElement.prototype.showModal;
    window.HTMLAnchorElement.prototype.click = () => {};

    for (const key of ['window', 'document', 'HTMLElement', 'Element', 'Node', 'File',
        'CustomEvent', 'Event', 'URL', 'navigator', 'getComputedStyle', 'HTMLAnchorElement',
        'HTMLDialogElement', 'Image', 'MouseEvent']) {
        if (window[key] === undefined) continue;
        Object.defineProperty(globalThis, key, { value: window[key], configurable: true, writable: true });
    }
    Object.defineProperty(globalThis, 'Blob', { value: NativeBlob, configurable: true, writable: true });

    const db = await Database.open({ factory: new IDBFactory(), name: `edit_${Math.random()}` });
    const app = createApp({
        db,
        document: window.document,
        window,
        storage: null,
        pipeline: {
            decode: async () => ({ source: {}, width: 800, height: 600, orientation: 1 }),
            createCanvas: () => ({
                getContext: () => ({
                    save() {}, restore() {}, setTransform() {}, fillRect() {}, fillStyle: '', drawImage() {},
                }),
                convertToBlob: async () => new NativeBlob([new Uint8Array([0xff, 0xd8, 0xff])],
                    { type: 'image/jpeg' }),
            }),
        },
        baseDocxBytes: BASE_DOCX,
    });
    await app.start();
    return { window, db, app };
}

const fill = (window, element, value) => {
    element.value = value;
    element.dispatchEvent(new window.Event('input', { bubbles: true }));
    element.dispatchEvent(new window.Event('change', { bubbles: true }));
};

const submit = async (window, form) => {
    form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
};

async function goto(window, hash, route) {
    const before = Number(window.document.body.dataset.render ?? 0);
    window.location.hash = hash;
    await waitFor(window, () => Number(window.document.body.dataset.render ?? 0) > before,
        `渲染 ${hash}`);
    if (route) await waitFor(window, () => window.document.body.dataset.route === route, `路由 ${route}`);
}

/** 建一个项目 + 一条两面的立柱记录，返回 { projectId, recordId }。 */
async function seed(window) {
    await goto(window, '#/projects/new', 'projects.new');
    const form = $(window, '#project-form');
    fill(window, form.querySelector('[name="project_no"]'), 'EDIT-01');
    fill(window, form.querySelector('[name="house_name"]'), '编辑测试楼');
    await submit(window, form);
    await waitFor(window, () => /^#\/projects\/\d+$/.test(window.location.hash), '跳项目详情');
    const projectId = Number(window.location.hash.split('/').pop());

    await goto(window, `#/projects/${projectId}/records/new/column`, 'records.new');
    const recordForm = $(window, '#record-form');
    fill(window, recordForm.querySelector('[name="floor"]'), '六层');
    fill(window, recordForm.querySelector('[name="member_position"]'), '1');
    fill(window, recordForm.querySelector('[name="size_result"]'), '63x164');
    fill(window, recordForm.querySelector('[name="face_0"]'), 'B');
    ['2.99', '3.02', '3.01', '3.01', '2.99'].forEach((value, index) => {
        fill(window, recordForm.querySelector(`[name="value_0_${index + 1}"]`), value);
    });

    // 再加一个检测面，确保多面记录也能正确回填
    $(window, '#add-face').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    await waitFor(window, () => window.document.querySelectorAll('details.face-row').length === 2,
        '第二个检测面出现');
    fill(window, window.document.querySelector('[name="face_1"]'), 'H');
    ['2.52', '2.51', '2.50', '2.53', '2.52'].forEach((value, index) => {
        fill(window, window.document.querySelector(`[name="value_1_${index + 1}"]`), value);
    });

    await submit(window, recordForm);
    await waitFor(window, () => /六层/.test($(window, '#view').textContent), '项目详情出现记录');
    const recordId = Number(/id="record-(\d+)"/.exec($(window, '#view').innerHTML)?.[1]);
    return { projectId, recordId };
}

/* --------------------------------------------------------------------------
 * 编辑路径
 * ------------------------------------------------------------------------ */

test('编辑检测记录：能打开、预填两面数据、改值后保存并回到详情', async () => {
    const { window, db } = await setup();
    const { projectId, recordId } = await seed(window);
    assert.ok(recordId > 0, '应能拿到记录 id');

    // 1) 打开编辑页 —— 这一步原来直接崩（readings 是 undefined）
    await goto(window, `#/records/${recordId}/edit`, 'records.edit');
    const view = $(window, '#view');
    assert.match(view.textContent, /编辑检测记录/);
    assert.match(view.textContent, /模板类型不可切换/);
    assert.ok(!/这一页出错了/.test(view.textContent), '不该进入错误兜底');

    // 2) 预填：构件信息 + 两个检测面 + 每面 5 个读数
    const form = $(window, '#record-form');
    assert.equal(form.querySelector('[name="floor"]').value, '六层');
    assert.equal(form.querySelector('[name="member_position"]').value, '1');
    assert.equal(form.querySelector('[name="size_result"]').value, '63×164', '尺寸结果应已归一化');

    const faces = window.document.querySelectorAll('details.face-row');
    assert.equal(faces.length, 2, '两个检测面都要回填');
    assert.deepEqual(
        [...window.document.querySelectorAll('input.face-input')].map((input) => input.value),
        ['B', 'H']);
    assert.deepEqual(
        [...window.document.querySelectorAll('[name="value_0_1"],[name="value_0_2"],[name="value_0_3"],[name="value_0_4"],[name="value_0_5"]')]
            .map((input) => input.value),
        ['2.99', '3.02', '3.01', '3.01', '2.99']);
    assert.deepEqual(
        [...window.document.querySelectorAll('[name="value_1_1"],[name="value_1_2"],[name="value_1_3"],[name="value_1_4"],[name="value_1_5"]')]
            .map((input) => input.value),
        ['2.52', '2.51', '2.50', '2.53', '2.52']);

    // 3) 改写第一个面的第一格，保存
    fill(window, form.querySelector('[name="value_0_1"]'), '2.10');
    assert.equal($(window, '#face-list .min-value').textContent, '2.10', '改完立即刷新最小值');

    await submit(window, form);
    await waitFor(window, () => /^#\/projects\/\d+$/.test(window.location.hash), '保存后回详情');
    await waitFor(window, () => /2\.10/.test($(window, '#view').textContent), '详情显示新最小值');

    // 4) 数据层确认：还是 2 个面、记录没被复制成两条
    const measurements = await import('../app/repo/measurements.js');
    const readings = await measurements.getReadings(db, recordId);
    assert.equal(readings.length, 2, '两个检测面，不多不少');
    const first = measurements.faceView(readings.find((row) => row.face === 'B'));
    assert.equal(first.min_text, '2.10', '最小值由数据层重算');
    assert.equal(measurements.faceView(readings.find((row) => row.face === 'H')).min_text, '2.50');

    const groups = await measurements.groupedByTemplate(db, projectId);
    assert.equal(groups[0].count, 1, '编辑不该新建记录');
});

test('编辑不存在的记录：给 404 卡片，而不是崩', async () => {
    const { window } = await setup();
    await goto(window, '#/records/9999/edit', 'records.edit');
    const text = $(window, '#view').textContent;
    assert.match(text, /没有这个页面/);
    assert.match(text, /检测记录不存在/);
    assert.ok(!/Cannot read properties/.test(text), '不该把 JS 异常文案丢给用户');
});
