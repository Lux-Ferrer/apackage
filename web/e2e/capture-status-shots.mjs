#!/usr/bin/env node
/* 为「进度会议」拍三张界面图（数据录入 / 报告列表 / 项目详情）。
 *
 * 与测试用例的区别：这不是断言，而是**取版式样张** —— 所以用真实数据、
 * 真实浏览器、375×812 手机视口，DPR 2（够清晰，文件也不至于太大）。
 *
 * 数据：先走界面建一个项目，再用页面里的 repo 模块灌 4 条检测记录 + 3 份带图报告
 * （灌数据比逐个点界面快，渲染结果完全一致 —— 渲染只看库里的数据）。
 *
 * 用法（自起服务，跑完自动关）：
 *     node web/e2e/capture-status-shots.mjs [--out _work/status] [--port 8125]
 */
import { spawn } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { chromium } from '@playwright/test';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const argOf = (name, fallback) => {
    const index = process.argv.indexOf(`--${name}`);
    return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
};
const OUT = resolve(ROOT, argOf('out', '_work/status'));
const PORT = Number(argOf('port', '8125'));
const BASE = `http://127.0.0.1:${PORT}`;
const FIXTURES = join(ROOT, '_work', 'e2e', 'fixtures');

mkdirSync(OUT, { recursive: true });

/* ---- 1) 起服务（用交付包本身，保证截图与交付物一致） ---- */
const server = spawn(process.execPath, ['web/e2e/serve-release.mjs', '--port', String(PORT)],
    { cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe'] });
const ready = (async () => {
    for (let attempt = 0; attempt < 120; attempt += 1) {
        try {
            const response = await fetch(`${BASE}/index.html`);
            if (response.ok) return;
        } catch { /* 还没起来 */ }
        await new Promise((resolve2) => setTimeout(resolve2, 500));
    }
    throw new Error('静态服务没起来');
})();
await ready;
console.log(`服务就绪：${BASE}`);

const browser = await chromium.launch({ channel: process.env.E2E_CHANNEL ?? 'msedge' });
const context = await browser.newContext({
    viewport: { width: 375, height: 812 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true,
    locale: 'zh-CN', timezoneId: 'Asia/Shanghai',
});
const page = await context.newPage();
const shot = async (name) => {
    // 清掉上一页的提示条（否则截图里会挂着"项目已创建"这类与画面无关的字）
    await page.evaluate(async () => {
        const { clearFlashes } = await import('/app/ui/dialog.js');
        clearFlashes();
    }).catch(() => {});
    await page.waitForTimeout(150);
    const path = join(OUT, `${name}.png`);
    await page.screenshot({ path, fullPage: false });
    console.log(`  📷 ${name}.png`);
    return path;
};
const route = (name) => page.waitForFunction((expected) => document.body.dataset.route === expected,
    name, { timeout: 30000 });

/* ---- 2) 建项目（走界面，顺带让截图里是"真用出来的"数据） ---- */
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => document.body.dataset.route === 'projects.index');
await page.evaluate(() => { location.hash = '#/projects/new'; });
await route('projects.new');
await page.locator('#project-form [name="project_no"]').fill('A06YG-2026-001');
await page.locator('#project-form [name="house_name"]').fill('金骐智谷 1 号厂房');
await page.locator('#project-form [name="house_address"]').fill('深圳市南山区科技园');
await page.locator('#project-form [name="client_org"]').fill('中冶建筑研究总院（深圳）有限公司');
await page.locator('#project-form [name="test_date"]').fill('2026-11-10');
await page.locator('.action-bar button[type="submit"]').click();
await route('projects.detail');
const projectId = Number(page.url().split('/').pop());
console.log(`项目已建：#${projectId}`);

/* ---- 3) 灌 4 条检测记录 + 3 份带图报告（用页面里的 repo，渲染结果与手填一致） ---- */
const portrait = readFileSync(join(FIXTURES, 'portrait.png')).toString('base64');
const large = readFileSync(join(FIXTURES, 'large.png')).toString('base64');
const seeded = await page.evaluate(async (config) => {
    const measurements = await import('/app/repo/measurements.js');
    const defectsRepo = await import('/app/repo/defects.js');
    const imagesRepo = await import('/app/repo/images.js');
    const db = window.__APP__.db;

    const rows = [
        { floor: '六层', position: '1', size: '63x164', readings: ['2.99', '3.02', '3.01', '3.01', '2.98'] },
        { floor: '六层', position: '2', size: '63x164', readings: ['3.01', '3.00', '3.02', '2.99', '3.01'] },
        { floor: '七层', position: '3', size: '64x165', readings: ['3.02', '3.04', '3.01', '3.03', '3.02'] },
        { floor: '七层', position: '4', size: '64x165', readings: ['2.98', '2.99', '3.00', '2.97', '2.99'] },
    ];
    for (const row of rows) {
        const form = {
            floor: row.floor, member_position: row.position, size_result: row.size,
            requirement_index: '0', face_0: 'B',
            value_0_1: row.readings[0], value_0_2: row.readings[1], value_0_3: row.readings[2],
            value_0_4: row.readings[3], value_0_5: row.readings[4],
        };
        const { data, errors } = measurements.parseRecordForm(form, 'column');
        if (Object.keys(errors).length) throw new Error(JSON.stringify(errors));
        await measurements.createRecord(db, config.projectId, 'column', data);
    }

    const defects = [
        { type: '密封胶开裂', part: '东立面三层 1# 立柱', level: '高', plan: '清除原密封胶，重新打胶并压实，固化前不得淋雨。', image: config.portrait, name: '东立面-密封胶开裂.png' },
        { type: '幕墙面板缺陷（玻璃）', part: '南立面五层 2# 板块', level: '中', plan: '更换破损玻璃面板，更换后复查密封胶完整性。', image: config.large, name: '南立面-面板缺陷.png' },
        { type: '半隐框外表面损伤', part: '西立面四层 3# 横梁', level: '低', plan: '打磨划痕并补涂同色氟碳漆。', image: config.large, name: '西立面-表面损伤.png' },
    ];
    for (const defect of defects) {
        const bytes = Uint8Array.from(atob(defect.image), (char) => char.charCodeAt(0));
        const file = new File([bytes], defect.name, { type: 'image/png' });
        const record = await imagesRepo.prepareUpload(db, file, { checkQuota: false });
        const { data } = await defectsRepo.parseForm(db, {
            defect_type: defect.type, project_part: defect.part, risk_level: defect.level,
            rectification_plan: defect.plan, project_id: String(config.projectId),
        });
        await defectsRepo.create(db, data, record);
    }
    return { records: rows.length, defects: defects.length };
}, { projectId, portrait, large });
console.log(`已灌数据：${seeded.records} 条记录 + ${seeded.defects} 份报告`);

/* ---- 4) 图一：数据录入（填满一条记录，含自动算出的最小值） ---- */
await page.evaluate(() => { location.hash = '#/projects/1/records/new/column'; });
await route('records.new');
await page.locator('#record-form [name="floor"]').fill('八层');
await page.locator('#record-form [name="member_position"]').fill('5');
await page.locator('#record-form [name="size_result"]').fill('63x164');
await page.locator('#record-form [name="face_0"]').fill('B');
for (const [index, value] of ['3.01', '3.03', '3.00', '3.02', '2.99'].entries()) {
    await page.locator(`#record-form [name="value_0_${index + 1}"]`).fill(value);
}
// 滚到厚度检测那一块：5 个读数 + 自动算出的最小值才是这张图要说明的东西
await page.locator('.face-row').first().scrollIntoViewIfNeeded();
await page.waitForTimeout(400);
await shot('01-数据录入');

/* ---- 5) 图二：报告列表（3 份带缩略图） ---- */
await page.evaluate(() => { location.hash = '#/reports'; });
await route('reports.index');
await page.waitForTimeout(600);
await shot('02-报告列表');

/* ---- 6) 图三：项目详情（记录 + 关联报告） ---- */
await page.evaluate((id) => { location.hash = `#/projects/${id}`; }, projectId);
await route('projects.detail');
await page.waitForTimeout(600);
await shot('03-项目详情');

/* ---- 7) 顺手导出一份样例 Word（与截图同一个项目，材料之间能对上） ---- */
const download = await Promise.all([
    page.waitForEvent('download', { timeout: 120000 }),
    page.locator('.head-actions button').filter({ hasText: /附加 3 份并导出/ }).first().click(),
]).then(([item]) => item);
const samplePath = join(OUT, 'Sample_Report.docx');
await download.saveAs(samplePath);
console.log(`  📄 ${download.suggestedFilename()} → Sample_Report.docx`);

await browser.close();
server.kill();
console.log(`产物已保存到 ${OUT.replace(`${ROOT}\\`, '')}`);
