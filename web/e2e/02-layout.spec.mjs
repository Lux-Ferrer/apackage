/* 移动端布局与控件：把 jsdom 看不出来的东西在真浏览器里量一遍。
 *
 * 这一组对应 M5 里三个"测试全绿、真机全废"的问题：
 *   1. 表单页底部 Tab 压过 `[hidden]`（作者样式 vs UA 样式）；
 *   2. 底栏 SVG 图标没走命名空间 → 空白；
 *   3. 桌面端（≥960px）固定操作条压住最后一个输入框。
 * 另外加了两条通用体检：横向溢出、触控尺寸。
 */
import { expect, test } from '@playwright/test';

import {
    addColumnRecord, attachDiagnostics, createProject, expectFormChrome, expectNoProblems,
    expectNoHorizontalOverflow, expectTabbarChrome, expectTablesScrollable, expectTapTargets,
    gotoRoute, openApp, screenshot, tabbarState,
} from './helpers.mjs';

test('列表页：底部 3 个 Tab 图标真的画出来了，且没有横向溢出', async ({ page }) => {
    const diagnostics = attachDiagnostics(page);
    await openApp(page);

    await expectTabbarChrome(page, { label: '项目列表' });
    await expectNoHorizontalOverflow(page, '项目列表');
    await expectTapTargets(page, { label: '项目列表' });

    // 报告页同样是列表壳
    await gotoRoute(page, '#/reports', 'reports.index');
    await expectTabbarChrome(page, { label: '报告管理' });
    await expectNoHorizontalOverflow(page, '报告管理');

    await screenshot(page, '10-布局-报告列表');
    expectNoProblems(diagnostics, '列表页');
});

test('表单页：只有操作条、Tab 真的隐藏、滚到底最后一个输入框不被遮住', async ({ page }) => {
    const diagnostics = attachDiagnostics(page);
    await openApp(page);
    const projectId = await createProject(page, { projectNo: 'LAY-01', houseName: '布局验证楼' });

    await gotoRoute(page, '#/projects/new', 'projects.new');
    await expectFormChrome(page, { label: '新建项目' });

    await gotoRoute(page, `#/projects/${projectId}/records/new/column`, 'records.new');
    await expectFormChrome(page, { label: '新增检测记录' });

    await gotoRoute(page, '#/reports/new', 'reports.new');
    await expectFormChrome(page, { label: '缺陷填报' });

    await gotoRoute(page, '#/me/profile', 'me.profile');
    await expectFormChrome(page, { label: '个人信息配置' });

    await screenshot(page, '11-布局-个人信息配置页');
    expectNoProblems(diagnostics, '表单页');
});

test('表单页在桌面端（1280×900）：操作条回到文档流、顶栏导航出现、不遮挡输入框', async ({ page }) => {
    const diagnostics = attachDiagnostics(page);
    await page.setViewportSize({ width: 1280, height: 900 });
    await openApp(page);
    await createProject(page, { projectNo: 'DESK-01', houseName: '桌面验证楼' });
    await gotoRoute(page, '#/projects/new', 'projects.new');

    // 桌面端 app.css 把操作条改成 position: static（回到文档流）—— 所以"遮挡"这个风险在这里
    // 应该是结构性消失的；但留白规则（body.has-action-bar）仍然要成立，否则最后一个字段贴边。
    await expectFormChrome(page, { label: '桌面端新建项目' });
    const position = await page.evaluate(
        () => getComputedStyle(document.querySelector('.action-bar')).position);
    expect(position, '桌面端操作条应在文档流里（app.css 的 ≥960px 规则）').toBe('static');

    // 桌面端应该出现顶栏导航
    const topnavVisible = await page.evaluate(() => {
        const nav = document.querySelector('#topnav');
        return nav ? nav.getBoundingClientRect().width > 100 : false;
    });
    expect(topnavVisible, '桌面端应显示顶栏导航').toBe(true);
    // 移动端底栏在桌面端应当消失
    const tabbarDisplay = await page.evaluate(
        () => getComputedStyle(document.querySelector('#tabbar')).display);
    expect(tabbarDisplay, '桌面端底部 Tab 不显示').toBe('none');

    await screenshot(page, '12-布局-桌面端表单');
    expectNoProblems(diagnostics, '桌面端');
});

test('详情页：检测记录可展开，宽表格在容器内横向滚动而不是撑宽整页', async ({ page }) => {
    const diagnostics = attachDiagnostics(page);
    await openApp(page);
    const projectId = await createProject(page, { projectNo: 'TBL-01', houseName: '表格验证楼' });
    await addColumnRecord(page, projectId);

    await expectNoHorizontalOverflow(page, '项目详情');
    await expectTablesScrollable(page);

    // 展开记录：数据表 7 列在 375px 下必然超宽，但应该由容器滚动
    await page.locator('details.record summary').first().click();
    await expectNoHorizontalOverflow(page, '项目详情（展开记录）');
    await expectTablesScrollable(page);

    const table = await page.evaluate(() => {
        const element = document.querySelector('.data-table');
        if (!element) return null;
        const rect = element.getBoundingClientRect();
        return { width: Math.round(rect.width), columns: element.querySelectorAll('thead th').length };
    });
    expect(table, '应渲染检测数据表').not.toBeNull();
    expect(table.columns, '立柱表应有 检测面 + 5 读数 + 最小值 = 7 列').toBe(7);

    await screenshot(page, '13-布局-详情页展开记录');
    expectNoProblems(diagnostics, '详情页');
});

test('数据管理页：容量信息/按钮都在，且没有横向溢出', async ({ page }) => {
    const diagnostics = attachDiagnostics(page);
    await openApp(page);
    await gotoRoute(page, '#/me/data', 'me.data');

    const text = await page.locator('#view').textContent();
    expect(text).toContain('已用空间');
    // 浏览器里 navigator.storage 存在 → 应显示真实数字而不是"不提供容量信息"
    expect(text).not.toContain('当前浏览器不提供容量信息');
    await expect(page.getByRole('button', { name: '申请持久化授权' })).toBeVisible();
    await expect(page.getByRole('button', { name: '导出备份（.zip）' })).toBeVisible();
    await expectNoHorizontalOverflow(page, '数据管理');

    await screenshot(page, '14-布局-数据管理');
    expectNoProblems(diagnostics, '数据管理');
});

test('存储配额：申请的持久化授权在真浏览器里有明确结果（不静默失败）', async ({ page }) => {
    const diagnostics = attachDiagnostics(page);
    await openApp(page);
    await gotoRoute(page, '#/me/data', 'me.data');

    await page.getByRole('button', { name: '申请持久化授权' }).click();
    // 结果文案只有四种，但必须出现其中一种（不能点了没反应）
    await expect(page.locator('#view')).toContainText(
        /已获持久化授权|未获持久化授权|不支持持久化|申请持久化失败/, { timeout: 20_000 });
    const persisted = await page.evaluate(async () => navigator.storage.persisted());
    expect(typeof persisted).toBe('boolean');

    // 页面上显示的已用空间应是个数字（KB/MB）
    const status = await page.evaluate(() => {
        const rows = [...document.querySelectorAll('#view table tr')]
            .map((row) => row.textContent.replace(/\s+/g, ' ').trim());
        return rows.find((row) => row.includes('已用空间')) ?? '';
    });
    expect(status).toMatch(/(KB|MB|GB)/);

    expectNoProblems(diagnostics, '持久化授权');
});

test('触控尺寸：主要操作按钮 ≥ 32px（拇指可点）', async ({ page }) => {
    await openApp(page);
    await expectTapTargets(page, { label: '项目列表' });
    await createProject(page, { projectNo: 'TAP-01', houseName: '触控验证楼' });
    await expectTapTargets(page, { label: '项目详情' });
    await gotoRoute(page, '#/reports/new', 'reports.new');
    await expectTapTargets(page, { label: '缺陷填报' });
});

test('tabbar 样式与 body 标记一致（表单页/列表页互不串味）', async ({ page }) => {
    await openApp(page);
    const list = await tabbarState(page);
    expect(list.hiddenAttr).toBe(false);
    expect(list.display).not.toBe('none');

    await gotoRoute(page, '#/projects/new', 'projects.new');
    const form = await tabbarState(page);
    expect(form.hiddenAttr).toBe(true);
    expect(form.display).toBe('none');
    expect(await page.evaluate(() => document.body.classList.contains('has-action-bar')))
        .toBe(true);

    await gotoRoute(page, '#/projects', 'projects.index');
    const back = await tabbarState(page);
    expect(back.display).not.toBe('none');
    expect(await page.evaluate(() => document.body.classList.contains('has-action-bar')))
        .toBe(false);
});
