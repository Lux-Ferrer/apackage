/* 边界负载：真实业务里可能遇到的极端情况。
 *
 * 测的不是"能不能跑"，而是"跑到多大还稳、稳在哪里"：
 *   - 20 份缺陷报告（每份 2400×1800 大图，导出时现压）+ 40 条检测记录；
 *   - 含附页导出 / 纯报告导出各一次，**同一页面连续导出 3 次**（测生成逻辑是否幂等）；
 *   - 主线程长任务（longtask）：有没有卡到用户以为死机的单次阻塞；
 *   - JS 堆增长：连续 5 次导出后有没有内存泄漏的迹象；
 *   - 全程零控制台错误（OOM 前一般会先报错）。
 */
import { expect, test } from '@playwright/test';

import {
    attachDiagnostics, createProject, downloadFrom, expectNoProblems, exportButton,
    gotoRoute, heapMb, openApp, seedVolume, verifyBackup, verifyDocx, waitForRoute,
} from './helpers.mjs';

const RECORDS = 40;
const DEFECTS = 20;

test('边界负载：40 条记录 + 20 份报告（大图），含附页导出 ×4 + 纯报告导出 + 备份', async ({ page }, testInfo) => {
    test.slow();                                   // 三倍超时（慢机器上导出 20 张图会久一点）
    const diagnostics = attachDiagnostics(page);

    await openApp(page);
    const projectId = await createProject(page, { projectNo: 'LOAD-01', houseName: '负载验证楼' });

    /* ---- 灌数据（走真实的 repo + canvas 管线） ---- */
    const heapBefore = await heapMb(page);
    const seedStarted = Date.now();
    const seeded = await seedVolume(page, { projectId, records: RECORDS, defects: DEFECTS });
    const seedMs = Date.now() - seedStarted;
    const heapAfterSeed = await heapMb(page);
    console.log(`[load] 灌数据 ${seedMs}ms（页面内 ${seeded.elapsedMs}ms）：`
        + `${RECORDS} 条记录 + ${DEFECTS} 份带图报告；堆 ${heapBefore} → ${heapAfterSeed} MB`);

    /* ---- 列表页能扛住 20 份（缩略图全部解码成功） ---- */
    await gotoRoute(page, '#/reports', 'reports.index');
    await expect(page.locator('.report-list .report-card')).toHaveCount(DEFECTS);
    // 缩略图是 `loading="lazy"`：先滚一遍把 20 张都触发出加载，再断言"零张破图"。
    // 顺带验证 objectURL 的生命周期 —— 如果渲染时把还在列表里的 URL 释放了，这里就会出现破图。
    await page.evaluate(async () => {
        const step = 400;
        for (let y = 0; y < document.body.scrollHeight; y += step) {
            window.scrollTo(0, y);
            await new Promise((resolve) => setTimeout(resolve, 60));
        }
        window.scrollTo(0, 0);
    });
    await expect.poll(() => page.evaluate(() => [...document.querySelectorAll('.report-thumb img')]
        .filter((image) => !image.complete || image.naturalWidth === 0).length),
    { timeout: 30_000, message: '20 张缩略图应全部解码成功（不能是破图）' }).toBe(0);
    const thumbs = await page.evaluate(() => {
        const images = [...document.querySelectorAll('.report-thumb img')];
        return { total: images.length, width: images[0]?.naturalWidth ?? 0 };
    });
    expect(thumbs.total, '20 份报告都应有缩略图').toBe(DEFECTS);
    expect(thumbs.width, '缩略图应真的解码出来').toBeGreaterThan(0);

    /* ---- 长任务观察器：卡顿要能被量化，而不是"感觉有点慢" ---- */
    await page.evaluate(() => {
        window.__longTasks = [];
        if (typeof PerformanceObserver === 'function') {
            const observer = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) window.__longTasks.push(Math.round(entry.duration));
            });
            observer.observe({ entryTypes: ['longtask'] });
        }
    });

    /* ---- 含 20 份附页导出 ---- */
    await gotoRoute(page, `#/projects/${projectId}`, 'projects.detail');
    await expect(page.locator('#view')).toContainText(`（${DEFECTS} 份）`);
    const exportStarted = Date.now();
    const first = await downloadFrom(page, exportButton(page, true), 'load-with-attachments.docx');
    const exportMs = Date.now() - exportStarted;
    const docx = verifyDocx(first.path);
    expect(docx.attachment_pages, `应含 ${DEFECTS} 份附页`).toBe(DEFECTS);
    expect(docx.media.length, `应嵌入 ${DEFECTS} 张图`).toBe(DEFECTS);
    expect(docx.compress_marks, '2400px 的大图每张都该标「已压缩」').toBe(DEFECTS);
    expect(docx.missing_image_marks, '不应有图片缺失').toBe(0);
    expect(docx.media.every((item) => item.width <= 1600 && item.height <= 1600),
        '导出副本最长边应被压到 1600px 以内').toBe(true);
    console.log(`[load] 含附页导出：${exportMs}ms，docx ${first.size} B，`
        + `媒体最大 ${Math.max(...docx.media.map((item) => item.bytes))} B`);

    /* ---- 连续导出 3 次（同一页面，不刷新）：验证生成逻辑幂等、不累积状态 ---- */
    const repeatTimes = [];
    for (let round = 0; round < 3; round += 1) {
        const started = Date.now();
        const repeat = await downloadFrom(page, exportButton(page, true), `load-repeat-${round}.docx`);
        repeatTimes.push(Date.now() - started);
        const repeated = verifyDocx(repeat.path);
        expect(repeated.attachment_pages, `第 ${round + 1} 次连续导出的附页数应稳定`).toBe(DEFECTS);
        expect(repeated.media.length).toBe(DEFECTS);
        expect(repeated.size_kb, `第 ${round + 1} 次产物大小应与首次接近（±20%）`)
            .toBeGreaterThan(docx.size_kb * 0.8);
        expect(repeated.size_kb).toBeLessThan(docx.size_kb * 1.2);
    }
    console.log(`[load] 连续导出耗时：${repeatTimes.join(' / ')} ms`);

    /* ---- 纯检测报告（40 条记录，无附页） ---- */
    const plainStarted = Date.now();
    const plain = await downloadFrom(page, exportButton(page, false), 'load-plain.docx');
    const plainMs = Date.now() - plainStarted;
    const plainDocx = verifyDocx(plain.path);
    expect(plainDocx.attachment_pages, '纯报告不该有附页').toBe(0);
    expect(plainDocx.media.length, '纯报告不该嵌图').toBe(0);
    expect(plainDocx.table_rows[0], `检测表应有 表头 2 行 + ${RECORDS} 条记录`)
        .toBe(2 + RECORDS);
    console.log(`[load] 纯报告导出：${plainMs}ms，表 ${plainDocx.tables} 张 / 行 ${plainDocx.table_rows}`);

    /* ---- 备份 20 张原图 ---- */
    await gotoRoute(page, '#/me/data', 'me.data');
    const backupStarted = Date.now();
    const backup = await downloadFrom(page, page.getByRole('button', { name: '导出备份（.zip）' }),
        'load-backup.zip');
    const backupMs = Date.now() - backupStarted;
    const backupInfo = verifyBackup(backup.path);
    expect(backupInfo.counts.defects).toBe(DEFECTS);
    expect(backupInfo.image_files, '备份应包含 20 张原图').toBe(DEFECTS);
    expect(backupInfo.images.every((item) => item.format === 'PNG'), '备份存原图（PNG）')
        .toBe(true);
    console.log(`[load] 备份导出：${backupMs}ms，${backup.size} B`);

    /* ---- 卡顿与内存 ---- */
    const longTasks = await page.evaluate(() => (window.__longTasks ?? []).slice(-200));
    const over200 = longTasks.filter((duration) => duration > 200);
    const worst = longTasks.length ? Math.max(...longTasks) : 0;
    const heapEnd = await heapMb(page);
    console.log(`[load] 长任务 ${longTasks.length} 个（>200ms ${over200.length} 个，最长 ${worst}ms）；`
        + `堆 ${heapBefore} → ${heapEnd} MB`);

    // 单次阻塞超过 4s 就属于"用户会以为死机"，这条线宁可宽松也不要假红
    expect(worst, `出现 ${worst}ms 的主线程长任务（超过 4s 视为不可接受）`).toBeLessThan(4000);
    if (heapEnd !== null && heapBefore !== null) {
        expect(heapEnd - heapBefore, `JS 堆增长 ${heapEnd - heapBefore} MB（>500MB 视为泄漏迹象）`)
            .toBeLessThan(500);
    }
    // 20 份附页在慢机器上也不该超过 2 分钟
    expect(exportMs).toBeLessThan(120_000);

    /* ---- 全程零错误 ---- */
    expectNoProblems(diagnostics, '负载测试');

    await testInfo.attach('负载指标', {
        contentType: 'application/json',
        body: JSON.stringify({
            seedMs, exportMs, repeatTimes, plainMs, backupMs,
            tableRows: plainDocx.table_rows, docxSizeKb: docx.size_kb,
            longTasks: { count: longTasks.length, over200: over200.length, worst },
            heapMb: { before: heapBefore, afterSeed: heapAfterSeed, end: heapEnd },
        }, null, 2),
    });
});
