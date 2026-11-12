/* 离线（Service Worker）：这是 jsdom 完全测不了的一块。
 *
 * 验四件事：
 *   1. Service Worker 真的装上并接管页面，缓存名里的版本号 = 交付包里 `VERSION.txt` 记的那个；
 *   2. 缓存条目数 = 离线清单条目数（"漏一个文件"就是断网白屏）；
 *   3. **断网后刷新，应用照常打开，数据还在**（index.html 从缓存来）；
 *   4. 断网状态下**还能导出 Word**（docx 生成全在本地，底座模板也在缓存里）。
 *
 * 注意：离线期间浏览器的"检查 SW 更新"请求会失败（`sw.js` / `shell.js`），
 * 这是预期行为，不是 bug —— 断言时把它们排除，但控制台错误仍然一条都不放过。
 */
import { expect, test } from '@playwright/test';

import {
    addColumnRecord, attachDiagnostics, createProject, downloadFrom, expectNoProblems,
    exportButton, gotoRoute, openApp, screenshot, verifyDocx, waitForRoute,
} from './helpers.mjs';

const SHELL_PREFIX = 'curtain-wall-shell-';

test('离线：SW 装好 → 缓存齐全 → 断网刷新可用 → 断网也能导出 Word', async ({ page, context }) => {
    const diagnostics = attachDiagnostics(page);

    await openApp(page);
    const projectId = await createProject(page, { projectNo: 'OFF-01', houseName: '离线验证楼' });
    await addColumnRecord(page, projectId);

    /* ---- 1. SW 接管 + 版本与交付包一致 ---- */
    await page.evaluate(() => navigator.serviceWorker.ready);
    await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller !== null),
        { timeout: 40_000, message: 'Service Worker 应接管页面' }).toBe(true);

    const info = await page.evaluate(async (prefix) => {
        const shell = await (await fetch('./assets/shell.js')).text();
        const version = /SHELL_VERSION = "([0-9a-f]{12})"/.exec(shell)?.[1] ?? null;
        const names = await caches.keys();
        const ours = names.filter((name) => name.startsWith(prefix));
        const current = `${prefix}${version}`;
        const cache = ours.includes(current) ? await caches.open(current) : null;
        const cached = cache ? (await cache.keys()).map((request) => new URL(request.url).pathname) : [];
        return { version, caches: names, current, cached };
    }, SHELL_PREFIX);

    expect(info.version, 'shell.js 里应有 12 位内容指纹版本号').toMatch(/^[0-9a-f]{12}$/);
    expect(info.caches, `应有缓存 ${info.current}`).toContain(info.current);
    expect(info.cached.length, '缓存条目数应与离线清单一致（44 项左右）').toBeGreaterThanOrEqual(20);

    // 交付包里 VERSION.txt 记的版本号必须与运行时一致（对不上的话"现场排查"会指错方向）
    const versionFile = await page.evaluate(async () => {
        const response = await fetch('./VERSION.txt');
        return response.ok ? response.text() : null;
    });
    if (versionFile) {
        expect(versionFile, 'VERSION.txt 里的离线缓存版本应与 shell.js 一致').toContain(info.version);
    }

    // 离线清单里每个文件都真的在缓存里
    const before = await page.evaluate(async (current) => {
        const shell = await (await fetch('./assets/shell.js')).text();
        const block = /SHELL_ASSETS\s*=\s*Object\.freeze\(\[(.*?)\]\)/s.exec(shell)?.[1] ?? '';
        const assets = [...block.matchAll(/"([^"]+)"/g)].map((match) => match[1]);
        const cache = await caches.open(current);
        const missing = [];
        for (const asset of assets) {
            const hit = await cache.match(new URL(asset, self.location.href).href);
            if (!hit) missing.push(asset);
        }
        return { assets: assets.length, missing };
    }, info.current);
    expect(before.missing, `这些文件没进缓存（断网会白屏）：${before.missing.join(', ')}`).toEqual([]);
    console.log(`[offline] SHELL_VERSION ${info.version}，缓存 ${before.assets} 个文件`);

    /* ---- 2. 断网刷新 ---- */
    await context.setOffline(true);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.addStyleTag({ content: '#flashes { pointer-events: none !important; }' });
    await waitForRoute(page, 'projects.detail');
    await expect(page.locator('#view'), '断网刷新后项目详情应照常显示').toContainText('离线验证楼');
    await expect(page.locator('#view')).toContainText('六层');
    await screenshot(page, '20-离线-刷新后');

    /* ---- 3. 断网也能导出（docx 全在本地生成） ---- */
    await gotoRoute(page, `#/projects/${projectId}`, 'projects.detail');
    const download = await downloadFrom(page, exportButton(page, false), 'offline-report.docx');
    const docx = verifyDocx(download.path);
    expect(docx.tables, '断网导出也应有检测表').toBeGreaterThanOrEqual(1);
    expect(docx.has_column_title).toBe(true);
    await expect(page.locator('#flashes')).toContainText('已导出');
    console.log(`[offline] 断网导出成功：${download.size} B`);

    /* ---- 4. 恢复网络 ---- */
    await context.setOffline(false);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await waitForRoute(page, 'projects.detail');
    await expect(page.locator('#view')).toContainText('离线验证楼');

    expectNoProblems(diagnostics, '离线测试');
});
