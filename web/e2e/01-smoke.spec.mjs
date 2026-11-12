/* 主流程：建项目 → 填检测记录 → 填缺陷报告（含图，绑定项目）→ 导出 Word → 导出备份。
 *
 * 这条链路上每一环都必须**真的发生在浏览器里**：IndexedDB 写入、canvas 缩略图、
 * docx 生成（docx 库 + JSZip）、Blob 下载。所以它同时是"功能验收"和"环境冒烟"：
 * 用例结束时断言这一整轮**没有任何控制台错误、未捕获异常、失败请求或 4xx**。
 *
 * 关键断言都落在**产物**上（python-docx / Pillow 读出来的东西），不是"按钮点了没报错"。
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test } from '@playwright/test';

import { PRODUCT } from '../app/product.js';
import {
    FIXTURES, addColumnRecord, addDefect, attachDiagnostics, createProject, downloadFrom,
    expectFormChrome, expectNoHorizontalOverflow, expectNoProblems, expectTabbarChrome,
    exportButton, gotoRoute, openApp, screenshot, verifyBackup, verifyDocx, waitForRoute,
} from './helpers.mjs';

test('主流程（375×812 真机视口）：建项目 → 检测记录 → 缺陷报告 → 导出 Word → 导出备份', async ({ page }, testInfo) => {
    const diagnostics = attachDiagnostics(page);
    const shots = [];

    /* ---- 1. 打开应用 ---- */
    await openApp(page);
    await expectTabbarChrome(page);
    await expectNoHorizontalOverflow(page, '项目列表');
    await expect(page.locator('#view h1')).toHaveText('项目');
    shots.push(await screenshot(page, '01-项目列表-空'));

    /* ---- 2. 建项目 ---- */
    const projectId = await createProject(page, {
        projectNo: 'E2E-001', houseName: '端到端验证楼',
        address: '深圳市南山区科技园', client: '中冶建筑研究总院（深圳）有限公司',
    });
    expect(projectId).toBeGreaterThan(0);
    await expect(page.locator('#view')).toContainText('端到端验证楼');
    await expect(page.locator('#view')).toContainText('E2E-001');
    // 没有关联报告时只有「导出 Word」一个导出入口（按钮组里还有「编辑项目」「删除项目」）
    await expect(page.locator('.head-actions button').filter({ hasText: /导出 Word/ })).toHaveCount(1);
    await expect(page.locator('.head-actions button').filter({ hasText: /附加|仅导出/ })).toHaveCount(0);
    shots.push(await screenshot(page, '02-项目详情-空'));

    /* ---- 3. 填检测记录（5 个读数 → 自动算最小值） ---- */
    await addColumnRecord(page, projectId, {
        floor: '六层', position: '1', face: 'B',
        readings: ['2.99', '3.02', '3.01', '3.01', '2.98'],
    });
    const recordSummary = page.locator('details.record summary').first();
    await expect(recordSummary).toContainText('六层 · 构件 1');
    await expect(recordSummary).toContainText('1 个面（B）');
    // 展开后能看到 5 个读数与自动算出的最小值（2.98 是我故意给的最小值）
    await page.locator('details.record').first().locator('summary').click();
    const recordBody = page.locator('details.record').first();
    for (const value of ['2.99', '3.02', '3.01', '2.98']) {
        await expect(recordBody).toContainText(value);
    }
    const minCell = await page.evaluate(() => {
        const row = document.querySelector('details.record .data-table tbody tr');
        return row ? [...row.children].map((cell) => cell.textContent.trim()) : null;
    });
    expect(minCell, '检测面行应有 检测面 + 5 读数 + 最小值 共 7 格').toHaveLength(7);
    expect(minCell[6], '最小应是 2.98').toBe('2.98');
    shots.push(await screenshot(page, '03-项目详情-检测记录'));

    /* ---- 4. 填缺陷报告（真实 PNG 走 canvas 管线）并绑定项目 ---- */
    const defectId = await addDefect(page, {
        imagePath: join(FIXTURES, 'portrait.png'),
        projectPart: '东立面三层 1# 立柱',
        plan: '清除原密封胶，重新打胶并压实，固化前不得淋雨',
        projectId,
    });
    expect(defectId).toBeGreaterThan(0);
    const detailText = await page.locator('#view').textContent();
    expect(detailText, '报告详情里应有默认报告人署名').toContain('检测员（检测部）');
    expect(detailText).toContain('端到端验证楼');
    // 大图真的渲染出来了（不是破图）
    const imageState = await page.evaluate(() => {
        const image = document.querySelector('#view figure.photo img');
        return image ? { naturalWidth: image.naturalWidth, naturalHeight: image.naturalHeight } : null;
    });
    expect(imageState, '报告详情应显示隐患图片').not.toBeNull();
    expect(imageState.naturalWidth, '图片应真的解码出来（800px 宽）').toBe(800);
    expect(imageState.naturalHeight).toBe(1600);
    shots.push(await screenshot(page, '04-报告详情'));

    /* ---- 5. 回项目详情 → 附加 1 份并导出 ---- */
    await gotoRoute(page, `#/projects/${projectId}`, 'projects.detail');
    const button = exportButton(page, true);
    await expect(button).toHaveText(/附加 1 份并导出/);
    const docxDownload = await downloadFrom(page, button, 'smoke-report.docx');
    expect(docxDownload.suggested, '文件名应按 项目编号_房屋名称_检测报告.docx 拼接')
        .toBe('E2E-001_端到端验证楼_检测报告.docx');
    await expect(page.locator('#flashes')).toContainText('已导出');
    shots.push(await screenshot(page, '05-导出完成'));

    const docx = verifyDocx(docxDownload.path);
    expect(docx.tables, '应有一张检测表').toBeGreaterThanOrEqual(1);
    expect(docx.has_column_title, '应含立柱检测表标题').toBe(true);
    expect(docx.attachment_pages, '应含 1 份附页').toBe(1);
    expect(docx.reporter_lines.join(), '附页里的报告人应是默认署名').toContain('检测员（检测部）');
    expect(docx.missing_image_marks, '图片必须真的嵌进去，不能是"图片缺失"').toBe(0);
    expect(docx.media.length, '应嵌入 1 张图片').toBe(1);
    expect([docx.media[0].width, docx.media[0].height], '嵌入图的像素尺寸应与原图一致')
        .toEqual([800, 1600]);
    expect(docx.compress_marks, '800×1600 未超限，不该标「已压缩」').toBe(0);

    /* ---- 6. 我的 → 数据管理 → 导出备份 ---- */
    await gotoRoute(page, '#/me/data', 'me.data');
    const overview = await page.locator('#view').textContent();
    expect(overview).toContain('1 个');
    expect(overview).toContain('1 条');
    expect(overview).toContain('1 份');
    shots.push(await screenshot(page, '06-数据管理'));

    const backupButton = page.getByRole('button', { name: '导出备份（.zip）' });
    const backupDownload = await downloadFrom(page, backupButton, 'smoke-backup.zip');
    expect(backupDownload.suggested).toMatch(/^幕墙检测备份_\d{8}_\d{4}\.zip$/);
    const backup = verifyBackup(backupDownload.path);
    expect(backup.format).toBe('curtain-wall-inspection-backup');
    expect(backup.counts.projects, '备份里应有 1 个项目').toBe(1);
    expect(backup.counts.defects, '备份里应有 1 份报告').toBe(1);
    expect(backup.image_files, '备份应含 1 张原图').toBe(1);
    expect(backup.thumbnail_rows, '缩略图不该进备份（可从原图重建）').toBe(0);
    expect(backup.images[0].format, '备份存的是原图（PNG），不是重压后的副本').toBe('PNG');

    /* ---- 7. 个人信息配置：改名字后，新建报告的署名跟着变 ---- */
    await gotoRoute(page, '#/me', 'me.index');
    await expect(page.locator('#view')).toContainText('检测员');
    await gotoRoute(page, '#/me/profile', 'me.profile');
    await expectFormChrome(page, { label: '个人信息配置页' });
    await page.locator('#profile-form [name="reporter_name"]').fill('张三');
    await page.locator('#profile-form [name="reporter_department"]').fill('幕墙检测二部');
    await page.locator('.action-bar button[type="submit"]').click();
    await waitForRoute(page, 'me.index');
    await expect(page.locator('#view .profile-name')).toHaveText('张三');
    await expect(page.locator('#flashes')).toContainText('个人信息已保存');
    shots.push(await screenshot(page, '07-我的-改署名后'));

    await gotoRoute(page, '#/reports/new', 'reports.new');
    await expect(page.locator('#view')).toContainText('张三（幕墙检测二部）');

    /* ---- 8. 关于页：产品信息，没有开发期痕迹 ---- */
    await gotoRoute(page, '#/about', 'pages.about');
    const aboutText = await page.locator('#view').textContent();
    /* 版本号不写死在这里：唯一真相源是 `web/app/product.js`，
     * 页面必须显示 `v<PRODUCT.version>`。写死的话每次发版都要改测试，
     * 而且改了测试就等于"放过"了版本号不一致的 bug。 */
    expect(aboutText).toContain(`v${PRODUCT.version}`);
    expect(aboutText).toContain('中冶建筑研究总院');
    expect(aboutText).not.toContain('模块进度');
    shots.push(await screenshot(page, '08-关于'));

    /* ---- 9. 全程零错误 ---- */
    expectNoProblems(diagnostics, '主流程');

    for (const path of shots) {
        await testInfo.attach(path.split(/[\\/]/).pop(), { path, contentType: 'image/png' });
    }
    testInfo.attach('docx-校验结果', {
        body: JSON.stringify(docx, null, 2), contentType: 'application/json',
    });
    testInfo.attach('备份-校验结果', {
        body: JSON.stringify(backup, null, 2), contentType: 'application/json',
    });
    // 用一句可读的摘要留在报告里
    console.log(`[smoke] docx ${docxDownload.size} B / ${docx.tables} 表 / 附页 ${docx.attachment_pages}；`
        + `备份 ${backupDownload.size} B / ${backup.image_files} 图`);
    /* 防御性：确保这两个文件确实被读进来了（避免断言全部空转） */
    expect(readFileSync(docxDownload.path).length).toBe(docxDownload.size);
});
