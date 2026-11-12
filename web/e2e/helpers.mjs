/* E2E 公共工具：诊断收集、路由等待、界面操作、产物校验、移动端布局断言。
 *
 * 三条约定（都来自被这个问题坑过的经历）：
 *  1. **等"用户看得见的结果"**，不等心跳：`waitForRoute()` 盯的是 main.js 写在
 *     `<body data-route/data-render>` 上的渲染标记，而不是某个选择器出现
 *     （选择器在上一页也可能存在，会读到旧 DOM）；
 *  2. **控制台/页面错误一个都不放过**：`attachDiagnostics()` 收集 console.error、
 *     pageerror、失败请求、4xx/5xx 响应，用例结束时统一断言 —— 白屏和静默失败都藏在这里；
 *  3. **产物用 Python 校验**（python-docx / Pillow）：能打开、附页份数、图片方向，
 *     都比"文件存在且非空"强得多。
 */
import { spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect } from '@playwright/test';

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
export const FIXTURES = join(ROOT, '_work', 'e2e', 'fixtures');
export const SHOTS = join(ROOT, '_work', 'e2e', 'screenshots');
export const ARTIFACTS = join(ROOT, '_work', 'e2e', 'artifacts');
export const PYTHON = process.env.PYTHON ?? 'python';

/* --------------------------------------------------------------------------
 * 诊断：控制台错误 / 页面异常 / 失败请求 / 4xx-5xx
 * ------------------------------------------------------------------------ */

export function attachDiagnostics(page) {
    const state = { consoleErrors: [], pageErrors: [], failedRequests: [], badResponses: [] };

    page.on('console', (message) => {
        if (message.type() === 'error') state.consoleErrors.push(message.text());
    });
    page.on('pageerror', (error) => state.pageErrors.push(error.message));
    page.on('requestfailed', (request) => {
        const reason = request.failure()?.errorText ?? '';
        // 导航打断（页面切换/下载）不是错误，浏览器本来就会 abort
        if (/ERR_ABORTED/.test(reason)) return;
        state.failedRequests.push(`${request.method()} ${request.url()} → ${reason}`);
    });
    page.on('response', (response) => {
        if (response.status() >= 400) {
            state.badResponses.push(`${response.status()} ${response.url()}`);
        }
    });
    return state;
}

/** 断言"这一轮什么错都没出"。任何一条都要能定位，所以按类别打印。 */
export function expectNoProblems(state, label = '本次会话') {
    const sections = [
        ['控制台 console.error', state.consoleErrors],
        ['未捕获异常 (pageerror)', state.pageErrors],
        ['失败的网络请求', state.failedRequests],
        ['4xx/5xx 响应', state.badResponses],
    ];
    const lines = [];
    for (const [title, items] of sections) {
        if (!items.length) continue;
        lines.push(`— ${title}（${items.length}）`);
        for (const item of items.slice(0, 12)) lines.push(`   ${item}`);
        if (items.length > 12) lines.push(`   …另有 ${items.length - 12} 条`);
    }
    expect(lines, `${label}出现了浏览器端问题：\n${lines.join('\n')}`).toEqual([]);
}

/* --------------------------------------------------------------------------
 * 页面准备与导航
 * ------------------------------------------------------------------------ */

/**
 * 打开应用首页并做两件测试专用的准备：
 *  - 提示条（toast）设为不可点击：它会短暂盖住页面顶部，
 *    Playwright 的可点击性检查会因此报 "element intercepts pointer events"（不是产品缺陷）；
 *  - 记录初始渲染标记。
 */
export async function openApp(page) {
    const response = await page.goto('/', { waitUntil: 'domcontentloaded' });
    expect(response?.status(), '首页应返回 200').toBe(200);
    await page.addStyleTag({ content: '#flashes { pointer-events: none !important; }' });
    await waitForRoute(page, 'projects.index');
}

/** 等某个路由渲染完成（看 main.js 写的 body 标记，不看选择器）。 */
export async function waitForRoute(page, name, { timeout = 30_000 } = {}) {
    await expect
        .poll(() => page.evaluate(() => document.body.dataset.route), { timeout, message: `等路由 ${name}` })
        .toBe(name);
}

/** 切到某个 hash 路由并等它渲染完。 */
export async function gotoRoute(page, hash, name = null) {
    await page.evaluate((target) => {
        if (window.location.hash === target) {
            // hash 没变就不会有 hashchange —— 手动补一次，模拟"重新进入当前页"
            window.dispatchEvent(new HashChangeEvent('hashchange'));
        } else {
            window.location.hash = target;
        }
    }, hash);
    if (name) await waitForRoute(page, name);
}

/** 当前路由里的数字 id（例如 `#/projects/7` → 7）。 */
export async function currentId(page) {
    const hash = await page.evaluate(() => window.location.hash);
    const match = /(\d+)$/.exec(hash);
    if (!match) throw new Error(`当前地址里没有 id：${hash}`);
    return Number(match[1]);
}

export async function screenshot(page, name) {
    mkdirSync(SHOTS, { recursive: true });
    const path = join(SHOTS, `${name}.png`);
    await page.screenshot({ path, fullPage: true });
    return path;
}

/* --------------------------------------------------------------------------
 * 业务操作（走的都是用户真会点的按钮/输入框）
 * ------------------------------------------------------------------------ */

export async function createProject(page, { projectNo, houseName, address = '', client = '' }) {
    await gotoRoute(page, '#/projects/new', 'projects.new');
    await page.locator('#project-form [name="project_no"]').fill(projectNo);
    await page.locator('#project-form [name="house_name"]').fill(houseName);
    if (address) await page.locator('#project-form [name="house_address"]').fill(address);
    if (client) await page.locator('#project-form [name="client_org"]').fill(client);
    await page.locator('.action-bar button[type="submit"]').click();
    await waitForRoute(page, 'projects.detail');
    return currentId(page);
}

export async function addColumnRecord(page, projectId, {
    floor = '六层', position = '1', face = 'B', readings = ['2.99', '3.02', '3.01', '3.01', '2.99'],
} = {}) {
    await gotoRoute(page, `#/projects/${projectId}/records/new/column`, 'records.new');
    await page.locator('#record-form [name="floor"]').fill(floor);
    await page.locator('#record-form [name="member_position"]').fill(position);
    await page.locator('#record-form [name="size_result"]').fill('63x164');
    await page.locator('#record-form [name="face_0"]').fill(face);
    for (const [index, value] of readings.entries()) {
        await page.locator(`#record-form [name="value_0_${index + 1}"]`).fill(value);
    }
    await page.locator('#save-record').click();
    await waitForRoute(page, 'projects.detail');
}

export async function addDefect(page, {
    imagePath = join(FIXTURES, 'portrait.png'),
    defectType = '密封胶开裂',
    projectPart = '东立面三层 1# 立柱',
    plan = '清除原密封胶，重新打胶并压实',
    projectId = null,
} = {}) {
    await gotoRoute(page, '#/reports/new', 'reports.new');
    await page.locator('#defect-form #image').setInputFiles(imagePath);
    await expect(page.locator('#image-preview')).toBeVisible();
    await page.locator('#defect-form [name="defect_type"]').selectOption({ label: defectType });
    await page.locator('#defect-form [name="project_part"]').fill(projectPart);
    await page.locator('#defect-form [name="rectification_plan"]').fill(plan);
    if (projectId !== null) {
        await page.locator('#defect-form [name="project_id"]').selectOption(String(projectId));
    }
    await page.locator('.action-bar button[type="submit"]').click();
    await waitForRoute(page, 'reports.detail');
    return currentId(page);
}

/** 点一个会触发下载的按钮，把文件存到 artifacts/ 并返回路径。 */
export async function downloadFrom(page, locator, filename) {
    mkdirSync(ARTIFACTS, { recursive: true });
    const [download] = await Promise.all([
        page.waitForEvent('download', { timeout: 180_000 }),
        locator.click(),
    ]);
    const path = join(ARTIFACTS, filename);
    await download.saveAs(path);
    expect(download.suggestedFilename()).toBeTruthy();
    return { path, suggested: download.suggestedFilename(), size: statSync(path).size };
}

/** 项目详情页的导出按钮（有无关联报告时文案不同）。 */
export function exportButton(page, withAttachments) {
    const text = withAttachments ? /附加 \d+ 份并导出/ : /仅导出检测报告|导出 Word/;
    return page.locator('.head-actions button').filter({ hasText: text }).first();
}

/* --------------------------------------------------------------------------
 * 产物校验（Python：python-docx / Pillow）
 * ------------------------------------------------------------------------ */

function runPython(args) {
    const result = spawnSync(PYTHON, args, { cwd: ROOT, encoding: 'utf8' });
    if (result.error) throw result.error;
    return result;
}

export function verifyDocx(path) {
    const result = runPython([join(ROOT, 'web', 'e2e', 'verify_artifacts.py'), 'docx', path]);
    let payload;
    try {
        payload = JSON.parse(result.stdout.trim());
    } catch {
        throw new Error(`docx 校验输出无法解析：\n${result.stdout}\n${result.stderr}`);
    }
    expect(payload.ok, `docx 打不开：${payload.error ?? ''}`).toBe(true);
    return payload;
}

export function verifyBackup(path) {
    const result = runPython([join(ROOT, 'web', 'e2e', 'verify_artifacts.py'), 'backup', path]);
    let payload;
    try {
        payload = JSON.parse(result.stdout.trim());
    } catch {
        throw new Error(`备份校验输出无法解析：\n${result.stdout}\n${result.stderr}`);
    }
    expect(payload.ok, `备份包不合法：${payload.error ?? ''}`).toBe(true);
    return payload;
}

/** 单张图片的尺寸与四边色带（用于断言缩略图/导出副本的方向）。 */
export function verifyImage(path) {
    const result = runPython([join(ROOT, 'web', 'e2e', 'verify_artifacts.py'), 'image', path]);
    let payload;
    try {
        payload = JSON.parse(result.stdout.trim());
    } catch {
        throw new Error(`图片校验输出无法解析：\n${result.stdout}\n${result.stderr}`);
    }
    expect(payload.ok, `图片读不开：${payload.error ?? ''}`).toBe(true);
    return payload;
}

/* --------------------------------------------------------------------------
 * 移动端布局断言（375×812）
 * ------------------------------------------------------------------------ */

/** 页面级横向溢出：`scrollWidth <= innerWidth + 1`。 */
export async function expectNoHorizontalOverflow(page, label = '当前页') {
    const info = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
    }));
    expect(info.scrollWidth, `${label}出现横向滚动（${info.scrollWidth} > ${info.innerWidth}）`)
        .toBeLessThanOrEqual(info.innerWidth + 1);
}

/** 宽表格必须由 `.table-scroll` 自己横向滚动，而不是把整页撑宽。 */
export async function expectTablesScrollable(page) {
    const broken = await page.evaluate(() => [...document.querySelectorAll('.table-scroll')]
        .filter((element) => element.scrollWidth > element.clientWidth + 1)
        .filter((element) => {
            const overflow = getComputedStyle(element).overflowX;
            return overflow !== 'auto' && overflow !== 'scroll';
        })
        .length);
    expect(broken, '有宽表格没在容器里横向滚动').toBe(0);
}

/** 底部 Tab 的可见性（真机 bug：`[hidden]` 被作者 `display:flex` 压过）。 */
export async function tabbarState(page) {
    return page.evaluate(() => {
        const tabbar = document.querySelector('#tabbar');
        const bar = document.querySelector('.action-bar');
        const style = getComputedStyle(tabbar);
        return {
            hiddenAttr: tabbar.hidden,
            display: style.display,
            rect: tabbar.getBoundingClientRect().toJSON(),
            visible: style.display !== 'none' && tabbar.getBoundingClientRect().height > 0,
            actionBar: bar ? { display: getComputedStyle(bar).display, rect: bar.getBoundingClientRect().toJSON() } : null,
        };
    });
}

/**
 * 表单页：底部只有操作条，且**最后一个控件不被它遮住**。
 *
 * 这是 M5 真机上出过的问题（`[hidden]` 压不过 `display:flex` / 桌面端留白不够），
 * 所以这里既看计算样式，也看几何关系。
 *
 * 注意两种外壳：移动端操作条是 `position: fixed`（会压住内容，必须留出垫底）；
 * ≥960px 的桌面端 app.css 把它改成 `position: static`（回到文档流，结构上不可能遮挡）。
 * 两种情况都要断言，但判据不同 —— 把桌面端当成"贴底失败"是测试自己错了。
 */
export async function expectFormChrome(page, { label = '表单页' } = {}) {
    const state = await tabbarState(page);
    expect(state.hiddenAttr, `${label}：底部 Tab 应被标记 hidden`).toBe(true);
    expect(state.display, `${label}：底部 Tab 实际仍是 ${state.display}（作者样式压过了 [hidden]）`)
        .toBe('none');
    expect(state.actionBar, `${label}：应有固定操作条`).not.toBeNull();
    expect(state.actionBar.display).not.toBe('none');

    const position = await page.evaluate(
        () => getComputedStyle(document.querySelector('.action-bar')).position);
    expect(['fixed', 'static'], `${label}：操作条的定位方式应是 fixed（手机）或 static（桌面）`)
        .toContain(position);

    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await page.waitForTimeout(150);
    const geometry = await page.evaluate(() => {
        const bar = document.querySelector('.action-bar').getBoundingClientRect();
        const controls = [...document.querySelectorAll('#view input, #view select, #view textarea')]
            .filter((element) => element.offsetParent !== null)
            .map((element) => element.getBoundingClientRect())
            .filter((rect) => rect.height > 0)
            .sort((left, right) => right.bottom - left.bottom);
        return {
            barTop: Math.round(bar.top),
            barHeight: Math.round(bar.height),
            viewportHeight: window.innerHeight,
            lowestBottom: controls.length ? Math.round(controls[0].bottom) : null,
        };
    });
    await page.evaluate(() => window.scrollTo(0, 0));

    if (position === 'fixed') {
        // 固定操作条必须贴在视口底部
        expect(Math.abs(geometry.barTop + geometry.barHeight - geometry.viewportHeight),
            `${label}：操作条没有贴底`).toBeLessThanOrEqual(2);
    }
    // 滚到底后，最后一个输入框不能被操作条压住（fixed 时会压，static 时天然不会）
    if (geometry.lowestBottom !== null) {
        expect(geometry.lowestBottom, `${label}：滚到底后最后一个输入框仍被操作条遮住`
            + `（输入框底部 ${geometry.lowestBottom}，操作条顶部 ${geometry.barTop}）`)
            .toBeLessThanOrEqual(geometry.barTop + 1);
    }
}

/** 列表页：底部 Tab 可见、3 项、图标真的画出来了（SVG 命名空间 bug 的验收点）。 */
export async function expectTabbarChrome(page, { label = '列表页' } = {}) {
    const state = await tabbarState(page);
    expect(state.hiddenAttr, `${label}：底部 Tab 不该隐藏`).toBe(false);
    expect(state.visible, `${label}：底部 Tab 没有显示`).toBe(true);

    const icons = await page.evaluate(() => [...document.querySelectorAll('#tabbar .nav-item')]
        .map((item) => {
            const svg = item.querySelector('svg');
            if (!svg) return { label: item.textContent.trim(), ok: false, reason: '没有 svg' };
            const rect = svg.getBoundingClientRect();
            return {
                label: item.textContent.trim(),
                namespace: svg.namespaceURI,
                localName: svg.localName,
                width: rect.width,
                height: rect.height,
                paths: svg.querySelectorAll('path').length,
                stroke: getComputedStyle(svg).strokeWidth,
            };
        }));
    expect(icons.length, `${label}：底部应有 3 个 Tab`).toBe(3);
    for (const icon of icons) {
        expect(icon.namespace, `${icon.label} 的图标不是 SVG 命名空间（创建方式错了）`)
            .toBe('http://www.w3.org/2000/svg');
        expect(icon.localName).toBe('svg');
        expect(icon.width, `${icon.label} 的图标宽度为 0（没画出来）`).toBeGreaterThan(8);
        expect(icon.height, `${icon.label} 的图标高度为 0（没画出来）`).toBeGreaterThan(8);
        expect(icon.paths, `${icon.label} 的图标没有路径`).toBeGreaterThan(0);
    }
}

/** 可点控件的触控尺寸（移动端拇指操作的最低要求）。 */
export async function expectTapTargets(page, { minSize = 32, label = '当前页' } = {}) {
    const small = await page.evaluate((min) => [...document.querySelectorAll(
        'button, a.btn, .nav-item, .action-bar a, .action-bar button, .head-actions a, .head-actions button')]
        .filter((element) => element.offsetParent !== null)
        .map((element) => {
            const rect = element.getBoundingClientRect();
            return {
                text: (element.textContent || '').trim().slice(0, 16),
                width: Math.round(rect.width),
                height: Math.round(rect.height),
            };
        })
        .filter((item) => item.width > 0 && item.height > 0)
        .filter((item) => item.height < min || item.width < min), minSize);
    expect(small, `${label}：这些控件的触控区域小于 ${minSize}px\n${JSON.stringify(small)}`)
        .toEqual([]);
}

/* --------------------------------------------------------------------------
 * 性能与内存（Chromium 的 performance.memory / CDP metrics）
 * ------------------------------------------------------------------------ */

export async function heapMb(page) {
    return page.evaluate(() => (performance.memory
        ? Math.round(performance.memory.usedJSHeapSize / 1048576)
        : null));
}

export async function cdpMetrics(page) {
    const session = await page.context().newCDPSession(page);
    try {
        await session.send('Performance.enable');
        const { metrics } = await session.send('Performance.getMetrics');
        return Object.fromEntries(metrics.map((item) => [item.name, item.value]));
    } finally {
        await session.detach();
    }
}

/** 读图片记录（浏览器里真实落库的东西）。 */
export async function imageRecords(page) {
    return page.evaluate(async () => {
        const { STORE } = await import('/app/db.js');
        const db = window.__APP__.db;
        const rows = await db.read([STORE.images], (ctx) => ctx.getAll(STORE.images));
        return rows.map((row) => ({
            id: row.id,
            width: row.width,
            height: row.height,
            bytes: row.bytes,
            hasThumb: Boolean(row.thumb),
            thumbBytes: row.thumb ? row.thumb.size : 0,
        }));
    });
}

/** 读缩略图字节（base64），供 Node 侧断言"缩略图也是摆正的"。 */
export async function thumbnailBase64(page, index = 0) {
    return page.evaluate(async (position) => {
        const { STORE } = await import('/app/db.js');
        const db = window.__APP__.db;
        const rows = await db.read([STORE.images], (ctx) => ctx.getAll(STORE.images));
        const row = rows[position];
        const buffer = new Uint8Array(await row.thumb.arrayBuffer());
        let binary = '';
        for (const byte of buffer) binary += String.fromCharCode(byte);
        return btoa(binary);
    }, index);
}

/**
 * 批量灌数据（负载测试用）：通过页面里**真实的 repo 与图像管线**写入，
 * 只是不点界面 —— 要灌 15 份报告、40 条记录，逐个点界面会让用例本身成为瓶颈。
 * 注意这里走的是与界面同一条数据链路（parseForm → createRecord / prepareUpload → create），
 * 所以灌进去的东西和用户手填的没有区别。
 */
export async function seedVolume(page, options) {
    return page.evaluate(async (config) => {
        const measurements = await import('/app/repo/measurements.js');
        const defectsRepo = await import('/app/repo/defects.js');
        const imagesRepo = await import('/app/repo/images.js');
        const db = window.__APP__.db;

        const started = performance.now();
        for (let index = 0; index < config.records; index += 1) {
            const { data, errors } = measurements.parseRecordForm({
                floor: `${index + 1}层`,
                member_position: String(index + 1),
                size_result: '63x164',
                requirement_index: '0',
                face_0: 'B',
                value_0_1: '2.99', value_0_2: '3.02', value_0_3: '3.01',
                value_0_4: '3.01', value_0_5: '2.99',
            }, 'column');
            if (Object.keys(errors).length) throw new Error(JSON.stringify(errors));
            await measurements.createRecord(db, config.projectId, 'column', data);
        }

        if (config.defects > 0) {
            for (let index = 0; index < config.defects; index += 1) {
                // 每份报告用**不同颜色**的图：纯色也一样会被压缩，但内容不同 →
                // docx 里的媒体文件就是 20 份而不是被内容去重成 1 份（去重本身是对的，
                // 但那样就验不出"图有没有装错附页"）。尺寸统一给 2400×1800，走缩放路径。
                const canvas = new OffscreenCanvas(config.imageWidth, config.imageHeight);
                const context = canvas.getContext('2d');
                context.fillStyle = `hsl(${(index * 37) % 360} 75% 50%)`;
                context.fillRect(0, 0, config.imageWidth, config.imageHeight);
                context.fillStyle = 'rgba(255,255,255,0.35)';
                for (let stripe = 0; stripe < 8; stripe += 1) {
                    context.fillRect(0, stripe * (config.imageHeight / 8), config.imageWidth, 60);
                }
                const blob = await canvas.convertToBlob({ type: 'image/png' });
                const file = new File([blob], `defect-${index + 1}.png`, { type: 'image/png' });
                const record = await imagesRepo.prepareUpload(db, file, { checkQuota: false });
                const { data } = await defectsRepo.parseForm(db, {
                    defect_type: '密封胶开裂',
                    project_part: `东立面${index + 1}层 1# 立柱`,
                    risk_level: ['高', '中', '低'][index % 3],
                    rectification_plan: '清除原胶后重新打胶',
                    project_id: String(config.projectId),
                });
                await defectsRepo.create(db, data, record);
            }
        }
        return { elapsedMs: Math.round(performance.now() - started) };
    }, {
        records: 0, defects: 0, imageWidth: 2400, imageHeight: 1800, ...options,
    });
}
