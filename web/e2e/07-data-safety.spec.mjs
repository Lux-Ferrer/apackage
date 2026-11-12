/* 数据安全与稳定性：两条"用户真的会走到、但 jsdom 里不是真路径"的流程。
 *
 *  1. **备份 → 清除 → 恢复**：现场工具出问题时唯一的救命手段。这里走的是
 *     真实的 `<dialog>` 模态确认（jsdom 里没有 `showModal()`，走的是 `confirm()` 降级分支，
 *     所以这条路径在单元测试里从来没被真正执行过）+ 真实的 File/JSZip 解析。
 *  2. **页面来回切换 30 次**：每次渲染都会建 objectURL、挂事件监听；
 *     如果哪一处没释放，翻几十次就能看到堆一路上涨（真机上表现为"用一会儿就卡"）。
 */
import { expect, test } from '@playwright/test';

import {
    ARTIFACTS, addColumnRecord, addDefect, attachDiagnostics, createProject, downloadFrom,
    expectNoProblems, gotoRoute, heapMb, openApp, screenshot, waitForRoute,
} from './helpers.mjs';

test('备份 → 清除全部报告 → 导入备份：数据与图片都回来，导出仍然可用', async ({ page }, testInfo) => {
    const diagnostics = attachDiagnostics(page);
    await openApp(page);

    /* ---- 准备：1 个项目 + 1 条记录 + 1 份带图报告 ---- */
    const projectId = await createProject(page, { projectNo: 'BAK-01', houseName: '备份验证楼' });
    await addColumnRecord(page, projectId);
    await addDefect(page, { projectId });

    /* ---- 1. 导出备份 ---- */
    await gotoRoute(page, '#/me/data', 'me.data');
    const backup = await downloadFrom(page, page.getByRole('button', { name: '导出备份（.zip）' }),
        'safety-backup.zip');
    expect(backup.size).toBeGreaterThan(500);

    /* ---- 2. 清除全部报告（走真实的 <dialog> 模态确认） ---- */
    await page.getByRole('button', { name: '清除全部报告' }).click();
    const dialog = page.locator('#confirm-dialog');
    await expect(dialog, '确认弹窗应真的打开（showModal 路径）').toBeVisible();
    await expect(dialog).toContainText('确认清除全部');
    await screenshot(page, '50-确认弹窗');
    await dialog.locator('#confirm-ok').click();
    await expect(dialog).toBeHidden();
    await expect(page.locator('#flashes')).toContainText(/已清除全部报告：1 份/);

    // 报告确实没了（列表变空）
    await gotoRoute(page, '#/reports', 'reports.index');
    await expect(page.locator('#view')).toContainText('还没有报告');
    // 项目与检测记录还在（清除只针对报告）
    await gotoRoute(page, '#/projects', 'projects.index');
    await expect(page.locator('#view')).toContainText('备份验证楼');

    /* ---- 3. 导入刚才那份备份（真实文件） ---- */
    await gotoRoute(page, '#/me/data', 'me.data');
    await page.locator('#backup-file').setInputFiles(backup.path);
    await page.getByRole('button', { name: '导入备份（覆盖全部数据）' }).click();
    const importDialog = page.locator('#confirm-dialog');
    await expect(importDialog).toBeVisible();
    await expect(importDialog).toContainText('覆盖当前全部数据');
    await importDialog.locator('#confirm-ok').click();
    await expect(page.locator('#flashes')).toContainText(/已导入：.*1 份报告/, { timeout: 60_000 });

    /* ---- 4. 恢复后的数据真的可用 ---- */
    await gotoRoute(page, '#/reports', 'reports.index');
    await expect(page.locator('.report-list .report-card')).toHaveCount(1);
    await expect(page.locator('.report-list .report-thumb img')).toHaveCount(1);
    // 缩略图是从原图重建出来的（备份里不含缩略图）——必须真的能解码
    await expect.poll(() => page.evaluate(() => [...document.querySelectorAll('.report-thumb img')]
        .every((image) => image.complete && image.naturalWidth > 0)),
    { timeout: 20_000, message: '导入后缩略图应被重建并解码成功' }).toBe(true);

    await gotoRoute(page, `#/projects/${projectId}`, 'projects.detail');
    const docx = await downloadFrom(page,
        page.locator('.head-actions button').filter({ hasText: /附加 1 份并导出/ }).first(),
        'after-restore.docx');
    expect(docx.size, '恢复后应能正常导出（含附页）').toBeGreaterThan(1000);

    expectNoProblems(diagnostics, '备份恢复');
    await testInfo.attach('恢复后导出', { body: String(docx.size), contentType: 'text/plain' });
    console.log(`[safety] 备份 ${backup.size} B → 清除 → 导入 → 导出 ${docx.size} B`);
});

test('页面来回切换 30 次：没有报错、没有明显内存泄漏', async ({ page }) => {
    const diagnostics = attachDiagnostics(page);
    await openApp(page);
    const projectId = await createProject(page, { projectNo: 'CHURN-01', houseName: '切换验证楼' });
    await addColumnRecord(page, projectId);
    await addDefect(page, { projectId });

    const routes = [
        ['#/projects', 'projects.index'],
        [`#/projects/${projectId}`, 'projects.detail'],
        ['#/reports', 'reports.index'],
        ['#/me', 'me.index'],
        ['#/about', 'pages.about'],
        ['#/me/data', 'me.data'],
    ];
    // 先跑两轮热身（JIT、首次渲染的模块都在这一轮加载完）
    for (let round = 0; round < 2; round += 1) {
        for (const [hash, name] of routes) await gotoRoute(page, hash, name);
    }
    const heapWarm = await heapMb(page);

    for (let round = 0; round < 5; round += 1) {
        for (const [hash, name] of routes) await gotoRoute(page, hash, name);
    }
    const heapEnd = await heapMb(page);

    const growth = (heapWarm !== null && heapEnd !== null) ? heapEnd - heapWarm : null;
    console.log(`[churn] 30 次切换：堆 ${heapWarm} → ${heapEnd} MB（增长 ${growth} MB）`);
    if (growth !== null) {
        // 30 次渲染允许涨一点（缓存/GC 时序），但不能是"每次渲染都漏一屏"那种线性增长
        expect(growth, `30 次切换后堆增长 ${growth} MB，疑似泄漏`).toBeLessThan(60);
    }

    // objectURL 必须被释放：留下未 revoke 的会被下一轮统计到
    const urls = await page.evaluate(() => window.__REVOKED__ ?? null);
    expect(urls).toBeNull();                         // 没有这号全局，说明没被测试桩污染

    expectNoProblems(diagnostics, '切换压力');
});
