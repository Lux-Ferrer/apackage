/* 鲁棒性：真实浏览器里才有、jsdom 里根本不会发生的几种"边缘但常见"的情况。
 *
 *  1. **软键盘弹起**（视口变矮）：地址栏/键盘把可视高度压到 ~400px 时，底部操作条会不会
 *     把正在填的输入框整个盖住？（手机上最常见的一次交互，jsdom 里视口是常量）
 *  2. **横屏**（812×375）：底栏 + 操作条 + 宽表格还成立吗？
 *  3. **浏览器后退/前进**：hash 路由在真实历史栈里的表现（jsdom 里没有真正的历史栈）。
 *  4. **文件名里的非法字符**（项目编号带 `/` `:`）：下载会不会直接失败。
 *  5. **空项目导出**：应当给一句能读懂的错误，而不是崩溃或空文件。
 *  6. **半途刷新**：在详情页按 F5，应用要自己从 hash 恢复，而不是白屏。
 */
import { expect, test } from '@playwright/test';

import {
    addColumnRecord, addDefect, attachDiagnostics, createProject, downloadFrom, expectNoProblems,
    exportButton, gotoRoute, openApp, screenshot, tabbarState, waitForRoute,
} from './helpers.mjs';

test('软键盘把视口压到 375×400：操作条仍可用，聚焦的输入框不被盖住', async ({ page }) => {
    const diagnostics = attachDiagnostics(page);
    await openApp(page);
    const projectId = await createProject(page, { projectNo: 'KB-01', houseName: '键盘验证楼' });

    await gotoRoute(page, `#/projects/${projectId}/records/new/column`, 'records.new');
    await page.locator('#record-form [name="floor"]').fill('六层');
    await page.locator('#record-form [name="member_position"]').fill('1');
    await page.locator('#record-form [name="face_0"]').fill('B');
    for (const [index, value] of ['2.99', '3.02', '3.01', '3.01', '2.98'].entries()) {
        await page.locator(`#record-form [name="value_0_${index + 1}"]`).fill(value);
    }
    // 模拟软键盘弹起：可视高度从 812 降到 400
    await page.setViewportSize({ width: 375, height: 400 });
    await page.waitForTimeout(200);

    // 操作条仍贴在视口底部
    const bar = await page.evaluate(() => {
        const element = document.querySelector('.action-bar');
        const rect = element.getBoundingClientRect();
        return { position: getComputedStyle(element).position, bottom: Math.round(rect.bottom), viewport: window.innerHeight };
    });
    expect(bar.position).toBe('fixed');
    expect(Math.abs(bar.bottom - bar.viewport), '操作条应贴在（变矮后的）视口底部').toBeLessThanOrEqual(2);

    // 用户点输入框 → 浏览器把**新聚焦**的元素滚进可视区。
    // ⚠️ 必须先 blur：如果焦点本来就在这个框上，`focus()` 是空操作、不会触发滚动，
    //    那样测出来的是测试自己的假象（第一次写这条用例就踩了）。
    await page.evaluate(() => document.activeElement?.blur());
    await page.locator('#record-form [name="value_0_5"]').focus();
    await page.waitForTimeout(250);
    const focused = await page.evaluate(() => {
        const input = document.activeElement;
        const rect = input.getBoundingClientRect();
        const actionBar = document.querySelector('.action-bar').getBoundingClientRect();
        return {
            name: input.getAttribute('name'),
            top: Math.round(rect.top),
            bottom: Math.round(rect.bottom),
            barTop: Math.round(actionBar.top),
            scrollY: Math.round(window.scrollY),
            visible: rect.top >= 0 && rect.bottom <= window.innerHeight,
        };
    });
    expect(focused.name).toBe('value_0_5');
    expect(focused.scrollY, '浏览器应把聚焦的输入框滚进可视区').toBeGreaterThan(0);
    expect(focused.visible, `聚焦的输入框应在可视区内（top ${focused.top}, bottom ${focused.bottom}）`).toBe(true);
    /* 这一条是**真机式**的判据：浏览器不知道底部还有一条固定操作条，
     * 它只保证"元素进了视口"，而进来之后可能正好被操作条盖住。
     * 解决办法是 CSS 的 `scroll-margin-bottom`（见 styles/m5.css）。 */
    expect(focused.bottom, `聚焦的输入框不能被操作条盖住（输入框底部 ${focused.bottom} > 操作条顶部 ${focused.barTop}）`)
        .toBeLessThanOrEqual(focused.barTop + 1);

    // 键盘状态下仍然能保存
    await page.locator('#save-record').click();
    await waitForRoute(page, 'projects.detail');
    await expect(page.locator('#view')).toContainText('六层');

    expectNoProblems(diagnostics, '软键盘场景');
});

test('横屏 812×375：底栏与操作条不重叠，宽表格在容器里滚动', async ({ page }) => {
    const diagnostics = attachDiagnostics(page);
    await page.setViewportSize({ width: 812, height: 375 });
    await openApp(page);

    const list = await tabbarState(page);
    expect(list.visible, '横屏下底部 Tab 仍应在').toBe(true);
    const listOverflow = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
    }));
    expect(listOverflow.scrollWidth).toBeLessThanOrEqual(listOverflow.innerWidth + 1);

    const projectId = await createProject(page, { projectNo: 'LAND-01', houseName: '横屏验证楼' });
    await addColumnRecord(page, projectId);
    await page.locator('details.record summary').first().click();

    const layout = await page.evaluate(() => {
        const tabbar = document.querySelector('#tabbar').getBoundingClientRect();
        const table = document.querySelector('.table-scroll');
        return {
            tabbarTop: Math.round(tabbar.top),
            viewport: window.innerHeight,
            tableOverflow: table ? getComputedStyle(table).overflowX : null,
            pageScrollWidth: document.documentElement.scrollWidth,
            innerWidth: window.innerWidth,
        };
    });
    // 812 宽度还没到 960 的断点 → 仍用底部 Tab；它必须贴在底部而不是浮在中间
    expect(layout.tabbarTop).toBeGreaterThan(layout.viewport * 0.7);
    expect(layout.tableOverflow, '宽表格应由容器自己横向滚动').toMatch(/auto|scroll/);
    expect(layout.pageScrollWidth, '整页不该因为表格变宽而横向滚动')
        .toBeLessThanOrEqual(layout.innerWidth + 1);

    await screenshot(page, '40-布局-横屏');
    expectNoProblems(diagnostics, '横屏');
});

test('浏览器后退 / 前进：路由能正确恢复，不白屏也不报错', async ({ page }) => {
    const diagnostics = attachDiagnostics(page);
    await openApp(page);
    const projectId = await createProject(page, { projectNo: 'HIST-01', houseName: '历史验证楼' });
    await gotoRoute(page, '#/reports', 'reports.index');
    await gotoRoute(page, `#/projects/${projectId}`, 'projects.detail');

    await page.goBack();
    await waitForRoute(page, 'reports.index');
    await expect(page.locator('#view h1')).toHaveText('报告管理');

    await page.goBack();
    await waitForRoute(page, 'projects.detail');
    await expect(page.locator('#view')).toContainText('历史验证楼');

    await page.goForward();
    await waitForRoute(page, 'reports.index');

    expectNoProblems(diagnostics, '前进后退');
});

test('文件名里的非法字符会被清理，下载仍然成功', async ({ page }) => {
    const diagnostics = attachDiagnostics(page);
    await openApp(page);
    // 项目编号带 `/` `:` `\` —— Windows/iOS 上这些字符会让下载直接失败
    const projectId = await createProject(page, {
        projectNo: 'A/B:C\\D*E',
        houseName: '斜杠/冒号:验证',
    });
    await addColumnRecord(page, projectId);

    const download = await downloadFrom(page, exportButton(page, false), 'weird-name.docx');
    expect(download.suggested, '文件名里的非法字符应被替换成下划线')
        .not.toMatch(/[\\/:*?"<>|]/);
    expect(download.suggested).toMatch(/\.docx$/);
    expect(download.size).toBeGreaterThan(1000);
    console.log(`[robust] 生成的下载文件名：${download.suggested}`);

    expectNoProblems(diagnostics, '非法文件名');
});

test('空项目导出：给出可读错误、不产生下载、不报未捕获异常', async ({ page }) => {
    const diagnostics = attachDiagnostics(page);
    await openApp(page);
    await createProject(page, { projectNo: 'EMPTY-02', houseName: '空项目验证楼' });

    let downloads = 0;
    page.on('download', () => { downloads += 1; });
    await exportButton(page, false).click();
    await expect(page.locator('#flashes')).toContainText(/还没有检测记录/, { timeout: 20_000 });
    await page.waitForTimeout(600);
    expect(downloads, '空项目不该产生下载').toBe(0);

    // 页面仍然可用（不是死循环/白屏）
    await gotoRoute(page, '#/projects', 'projects.index');
    await expect(page.locator('#view h1')).toHaveText('项目');

    expectNoProblems(diagnostics, '空项目导出');
});

test('半途刷新（F5）：从 hash 恢复当前页，数据不丢', async ({ page }) => {
    const diagnostics = attachDiagnostics(page);
    await openApp(page);
    const projectId = await createProject(page, { projectNo: 'RELOAD-01', houseName: '刷新验证楼' });
    await addColumnRecord(page, projectId);
    await addDefect(page, { projectId });
    const hashBefore = await page.evaluate(() => window.location.hash);

    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.addStyleTag({ content: '#flashes { pointer-events: none !important; }' });
    await page.waitForFunction(() => document.body.dataset.route === 'reports.detail');
    expect(await page.evaluate(() => window.location.hash)).toBe(hashBefore);
    await expect(page.locator('#view')).toContainText('密封胶开裂');
    await expect(page.locator('#view')).toContainText('刷新验证楼');

    // 刷新后仍然能导出（底座模板、库都在缓存里）
    await gotoRoute(page, `#/projects/${projectId}`, 'projects.detail');
    const download = await downloadFrom(page, exportButton(page, true), 'reload-report.docx');
    expect(download.size).toBeGreaterThan(1000);

    expectNoProblems(diagnostics, '刷新恢复');
});
