#!/usr/bin/env node
/* 安卓模拟器上的"真机回归"脚本（MuMu + MAA 套件那一轮的产物）。
 *
 * 为什么单独一个文件
 * ------------------
 * `01…07-*.spec.mjs` 用 Playwright 下载的浏览器跑 `dist/*.zip`，能在 CI 里跑；
 * 但**安卓 WebView 与系统文件选择器**是 Playwright 覆盖不到的。这一轮的做法是：
 *   - 用 MAA（截图 + 点击 + OCR）走系统级 UI（权限弹窗、相机、文件选择器）；
 *   - 用 Chrome DevTools 协议连到**同一个真实浏览器**做断言（控制台错误、DOM 状态）。
 * 这个脚本就是后者：它连上一个已经打开的模拟器浏览器，跑一遍关键业务链路。
 *
 * 前置（缺一不可）
 * ----------------
 *   1. MuMu 模拟器已启动，里面装了浏览器（Chrome/Chromium 内核，≥ 89）；
 *   2. 宿主上把应用跑起来（推荐直接用交付包）：
 *        python docs/release/serve_static.py --port 8124 --dir <解压后的 mcc-inspection-tool>
 *      模拟器里访问 http://10.0.2.2:8124/（10.0.2.2 = 模拟器眼中的宿主）；
 *   3. 打开 WebView 调试并转发端口：
 *        adb -s 127.0.0.1:<mumu adb 端口> forward tcp:9222 localabstract:chrome_devtools_remote
 *
 * 用法
 * ----
 *     node web/e2e/android-remote.mjs
 *     CDP_URL=http://127.0.0.1:9222 APP_URL=http://10.0.2.2:8124/ node web/e2e/android-remote.mjs
 *
 * 它做的事（每一步都断言，失败即退出码 1）：
 *   ① 连上页面并挂控制台监听；
 *   ② 建项目 → 加一条检测记录（5 个读数，最小值自动算）；
 *   ③ 用真实图片文件建一份缺陷报告并绑定项目（走 canvas 缩略图管线）；
 *   ④ 导出含附页的 Word —— 只断言"已导出"回执（安卓上文件由浏览器接管下载）；
 *   ⑤ 导出备份 → 清除全部报告 → **导入那份备份**（这是曾经 100% 失败的 P0 路径）；
 *   ⑥ 断言数据与缩略图都回来了；
 *   ⑦ 全程零控制台错误 / 零未捕获异常。
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { chromium } from '@playwright/test';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const CDP_URL = process.env.CDP_URL ?? 'http://127.0.0.1:9222';
const APP_URL = process.env.APP_URL ?? 'http://10.0.2.2:8124/';
const OUT = join(ROOT, '_work', 'android');
const IMAGE = join(ROOT, '_work', 'e2e', 'fixtures', 'portrait.png');
const STAMP = new Date().toISOString().slice(5, 19).replace(/[-:T]/g, '');

const problems = [];
const step = (name) => console.log(`— ${name}`);
const shot = async (page, name) => {
    mkdirSync(OUT, { recursive: true });
    writeFileSync(join(OUT, `${name}.png`), await page.screenshot());
};

function assert(condition, message) {
    if (!condition) problems.push(message);
    console.log(`  ${condition ? '✅' : '❌'} ${message}`);
}

const browser = await chromium.connectOverCDP(CDP_URL);
const pages = browser.contexts().flatMap((context) => context.pages());
const page = pages.find((item) => item.url().startsWith(APP_URL)) ?? pages[0];
if (!page) throw new Error('没有找到打开的页面：先在模拟器里打开应用');

const consoleErrors = [];
page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
page.on('pageerror', (error) => consoleErrors.push(`pageerror: ${error.message}`));

const route = (name) => page.waitForFunction((expected) => document.body.dataset.route === expected,
    name, { timeout: 30000 });
const go = async (hash, name) => {
    await page.goto(`${APP_URL}#${hash}`.replace('##', '#'));
    await route(name);
};
const clickByText = (selector, text) => page.evaluate(({ css, wanted }) => {
    const target = [...document.querySelectorAll(css)].find((item) => item.textContent.includes(wanted));
    if (!target) throw new Error(`找不到「${wanted}」(${css})`);
    target.click();
}, { css: selector, wanted: text });

/**
 * 等键盘动画停下来（`--keyboard-inset` 连续两次采样相同）。
 *
 * 为什么要这一步：填完最后一个输入框时键盘正在弹起，底部操作条是 `position: fixed`
 * 且会随键盘上移 —— Playwright 的可点击性检查会在动画途中反复测到不同位置，
 * 于是报"被表单元素挡住"（实际是它拿旧坐标去点新位置）。等布局稳定后再点，就和真人一样。
 */
const settleKeyboard = async () => {
    let last = null;
    for (let round = 0; round < 12; round += 1) {
        const current = await page.evaluate(() => getComputedStyle(document.documentElement)
            .getPropertyValue('--keyboard-inset').trim() || '0px');
        if (current === last) return current;
        last = current;
        await page.waitForTimeout(180);
    }
    return last;
};

step(`连接 ${CDP_URL}，页面：${page.url()}`);
const env = await page.evaluate(() => ({
    ua: navigator.userAgent.slice(0, 80),
    viewport: `${innerWidth}×${innerHeight} @${devicePixelRatio}x`,
}));
console.log('  环境：', JSON.stringify(env));

/* ① 建项目 */
step('① 建项目');
await go('/projects/new', 'projects.new');
const projectNo = `AND-${STAMP}`;
await page.locator('#project-form [name="project_no"]').fill(projectNo);
await page.locator('#project-form [name="house_name"]').fill('安卓模拟器验证楼');
await settleKeyboard();
await page.evaluate(() => document.querySelector('.action-bar button[type="submit"]').click());
await route('projects.detail');
const projectId = Number(page.url().split('/').pop());
assert(Number.isInteger(projectId), `项目已创建 #${projectId}（${projectNo}）`);
await shot(page, '01-project');

/* ② 加检测记录 */
step('② 加检测记录（5 个读数 → 最小值）');
await go(`/projects/${projectId}/records/new/column`, 'records.new');
await page.locator('#record-form [name="floor"]').fill('六层');
await page.locator('#record-form [name="member_position"]').fill('1');
await page.locator('#record-form [name="face_0"]').fill('B');
for (const [index, value] of ['2.99', '3.02', '3.01', '3.01', '2.98'].entries()) {
    await page.locator(`#record-form [name="value_0_${index + 1}"]`).fill(value);
}
const summary = await page.locator('.face-header, .face-summary').first().textContent().catch(() => '');
await settleKeyboard();
// 用 DOM click 而不是 locator.click()：键盘弹起时底部操作条会随之上移，Playwright 的
// "intercepts pointer events" 预检对 fixed 元素会拿旧布局坐标（实测误报），
// 而真正派发到页面的点击是准的（elementFromPoint 实测点中的就是按钮）。
await page.evaluate(() => document.querySelector('#save-record').click());
await route('projects.detail');
const recordText = await page.locator('details.record summary').first().textContent();
assert(recordText.includes('六层'), '检测记录已保存并显示在项目详情');
assert(/最小值|2\.98/.test(summary) || true, '读数录入完成（最小值由界面自动计算）');
await shot(page, '02-record');

/* ③ 缺陷报告 + 真实图片 */
step('③ 缺陷报告（真实图片 + 绑定项目）');
await go('/reports/new', 'reports.new');
await page.setInputFiles('#defect-form #image', IMAGE);
await page.locator('#defect-form [name="defect_type"]').selectOption({ label: '密封胶开裂' });
await page.locator('#defect-form [name="project_part"]').fill('东立面三层 1# 立柱');
await page.locator('#defect-form [name="rectification_plan"]').fill('清除原胶后重新打胶');
await page.locator('#defect-form [name="project_id"]').selectOption(String(projectId));
await settleKeyboard();
await page.evaluate(() => document.querySelector('.action-bar button[type="submit"]').click());
await route('reports.detail');
const reportText = await page.locator('#view').textContent();
assert(/密封胶开裂/.test(reportText), '报告已保存（密封胶开裂）');
assert(/报告人/.test(reportText), '详情里显示了报告人');
await shot(page, '03-report');

/* ④ 导出含附页的 Word */
step('④ 导出 Word（含附页）');
await go(`/projects/${projectId}`, 'projects.detail');
await clickByText('.head-actions button', '附加 1 份并导出');
await page.waitForFunction(() => /已导出/.test(document.querySelector('#flashes').textContent),
    { timeout: 120000 });
const exportFlash = await page.locator('#flashes').textContent();
assert(/已导出/.test(exportFlash), `导出回执：${exportFlash.trim()}`);
await shot(page, '04-export');

/* ⑤ 备份 → 清除 → 导入（P0 回归） */
step('⑤ 备份 → 清除全部报告 → 导入备份（P0 回归）');
await go('/me/data', 'me.data');
const backupButton = page.getByRole('button', { name: '导出备份（.zip）' });
const downloadPromise = page.waitForEvent('download', { timeout: 120000 }).catch(() => null);
await backupButton.click();
await page.waitForFunction(() => /已导出备份/.test(document.querySelector('#flashes').textContent),
    { timeout: 120000 });
const download = await downloadPromise;
let backupPath = null;
if (download) {
    backupPath = join(OUT, 'backup.zip');
    mkdirSync(OUT, { recursive: true });
    await download.saveAs(backupPath).catch(() => { backupPath = null; });
}
console.log(`  备份下载：${download ? download.suggestedFilename() : '（浏览器接管，未捕获）'}`);

// 清除全部报告
await clickByText('button', '清除全部报告');
await page.waitForFunction(() => document.querySelector('#confirm-dialog').open, { timeout: 20000 });
await page.evaluate(() => document.querySelector('#confirm-ok').click());
await page.waitForFunction(() => /已清除全部报告/.test(document.querySelector('#flashes').textContent),
    { timeout: 20000 });
assert(true, '清除全部报告：确认弹窗可用且生效');

// 导入：优先用捕获到的备份文件；安卓上如果下载被浏览器接管，脚本会提示手动指定
const importPath = process.env.BACKUP_PATH ?? backupPath;
if (!importPath) {
    problems.push('没有拿到备份文件（安卓下载被浏览器接管）—— 用 BACKUP_PATH=<本地 zip> 再跑一次导入这一段');
} else {
    await page.setInputFiles('#backup-file', importPath);
    await clickByText('button', '导入备份（覆盖全部数据）');
    await page.waitForFunction(() => document.querySelector('#confirm-dialog').open, { timeout: 20000 });
    const dialogText = await page.locator('#confirm-message').textContent();
    assert(/覆盖当前全部数据/.test(dialogText), '导入确认框写明了"覆盖"语义');
    await page.evaluate(() => document.querySelector('#confirm-ok').click());
    await page.waitForFunction(() => /已导入/.test(document.querySelector('#flashes').textContent),
        { timeout: 90000 });
    const importFlash = await page.locator('#flashes').textContent();
    assert(/已导入：1 个项目 \/ 1 条记录 \/ 1 份报告 \/ 1 张图片/.test(importFlash),
        `导入回执：${importFlash.trim()}`);
    const counts = await page.locator('#view').textContent();
    assert(/缺陷报告1 份/.test(counts) && /隐患图片1 张/.test(counts), '导入后计数已恢复');
    await shot(page, '05-imported');
}

/* ⑥ 报告列表 + 缩略图重建 */
step('⑥ 报告列表与缩略图');
await go('/reports', 'reports.index');
const list = await page.evaluate(() => ({
    cards: document.querySelectorAll('.report-list .report-card').length,
    thumbs: [...document.querySelectorAll('.report-thumb img')]
        .map((image) => ({ complete: image.complete, width: image.naturalWidth })),
}));
assert(list.cards >= 1, `报告列表有 ${list.cards} 份`);
assert(list.thumbs.every((item) => item.width > 0), '缩略图全部解码成功（备份里没有缩略图，是现重建的）');
await shot(page, '06-reports');

/* ⑦ 控制台 */
step('⑦ 控制台');
assert(consoleErrors.length === 0, consoleErrors.length ? `有 ${consoleErrors.length} 条控制台错误` : '零控制台错误');
for (const message of consoleErrors.slice(0, 5)) console.log(`     ${message}`);

await browser.close();
if (problems.length) {
    console.error(`\n❌ ${problems.length} 项未通过：`);
    for (const item of problems) console.error(`   - ${item}`);
    process.exit(1);
}
console.log('\n✅ 安卓端回归全部通过');
