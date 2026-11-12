/* 图片管线：只有真浏览器才验得了的三件事。
 *
 *  1. **EXIF 方向**：竖拍照片（Orientation=6）在页面上、缩略图里、以及**写进 docx 的像素**
 *     都必须是摆正的。jsdom 没有 `createImageBitmap`，这条永远测不出来 ——
 *     而客户现场十张照片里有八张是竖拍的。
 *  2. **透明 PNG 铺白底**：PNG 转 JPEG 时透明区不变白就会变成黑块（经典事故）。
 *  3. **大图等比压缩**：>1600px 的图导出时缩小，附页里标「已压缩」。
 *
 * 颜色约定见 `make_fixtures.py`：色带（红/绿/蓝/黄）的位置就是"方向对不对"的判据。
 */
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test } from '@playwright/test';

import {
    ARTIFACTS, FIXTURES, addColumnRecord, addDefect, attachDiagnostics, createProject,
    downloadFrom, expectNoProblems, exportButton, gotoRoute, imageRecords, openApp, screenshot,
    thumbnailBase64, verifyDocx, verifyImage,
} from './helpers.mjs';

test('EXIF 方向：竖拍照片在页面 / 缩略图 / docx 里都是正的', async ({ page }, testInfo) => {
    const diagnostics = attachDiagnostics(page);
    await openApp(page);
    const projectId = await createProject(page, { projectNo: 'EXIF-01', houseName: '方向验证楼' });
    await addColumnRecord(page, projectId);

    await addDefect(page, { imagePath: join(FIXTURES, 'rotated_exif.jpg'), projectId });

    /* ---- 1. 页面上的大图：浏览器自己按 EXIF 摆正 ---- */
    const shown = await page.evaluate(() => {
        const image = document.querySelector('#view figure.photo img');
        return { width: image.naturalWidth, height: image.naturalHeight };
    });
    expect([shown.width, shown.height], '存储 1200×800 + Orientation=6 → 页面应显示 800×1200')
        .toEqual([800, 1200]);

    /* ---- 2. 入库记录的尺寸 = 摆正后的尺寸 ---- */
    const records = await imageRecords(page);
    expect(records.length).toBe(1);
    expect([records[0].width, records[0].height], '入库尺寸应是摆正后的 800×1200')
        .toEqual([800, 1200]);
    expect(records[0].bytes, '原图字节应原样入库（不被重压）').toBeGreaterThan(0);

    /* ---- 3. 缩略图的像素：红带在顶部 ---- */
    const base64 = await thumbnailBase64(page, 0);
    const thumbPath = join(ARTIFACTS, 'exif-thumb.jpg');
    writeFileSync(thumbPath, Buffer.from(base64, 'base64'));
    const thumb = verifyImage(thumbPath);
    expect(thumb.height, '缩略图应保持竖向（高 > 宽）').toBeGreaterThan(thumb.width);
    expect(thumb.bands.top, `缩略图顶部应是红带，实际 ${thumb.bands.top}`).toBe('红');

    /* ---- 4. 写进 docx 的像素：同样是正的 ---- */
    await gotoRoute(page, `#/projects/${projectId}`, 'projects.detail');
    const download = await downloadFrom(page, exportButton(page, true), 'exif-report.docx');
    const docx = verifyDocx(download.path);
    expect(docx.media.length).toBe(1);
    const media = docx.media[0];
    expect([media.width, media.height], 'docx 里的像素应是摆正后的 800×1200')
        .toEqual([800, 1200]);
    expect(media.bands.top, 'docx 里图片的顶部应是红带（EXIF 真的被摆正了）').toBe('红');
    expect(docx.compress_marks, '1200px 未超限，不该标「已压缩」').toBe(0);

    await screenshot(page, '30-方向-报告详情');
    expectNoProblems(diagnostics, 'EXIF 方向');
    await testInfo.attach('exif-docx-media', {
        contentType: 'application/json', body: JSON.stringify({ thumb, media }, null, 2),
    });
});

test('透明 PNG 铺白底 + 大图等比压缩（附页标「已压缩」）', async ({ page }) => {
    const diagnostics = attachDiagnostics(page);
    await openApp(page);
    const projectId = await createProject(page, { projectNo: 'IMG-01', houseName: '图片验证楼' });
    await addColumnRecord(page, projectId);

    await addDefect(page, { imagePath: join(FIXTURES, 'alpha.png'), projectId });
    await addDefect(page, { imagePath: join(FIXTURES, 'large.png'), projectId });

    const records = await imageRecords(page);
    expect(records.length).toBe(2);
    const sizes = records.map((record) => [record.width, record.height]).sort((left, right) => left[0] - right[0]);
    expect(sizes, '两张图入库尺寸应与原图一致').toEqual([[800, 600], [2400, 1800]]);

    await gotoRoute(page, `#/projects/${projectId}`, 'projects.detail');
    const download = await downloadFrom(page, exportButton(page, true), 'image-report.docx');
    const docx = verifyDocx(download.path);
    expect(docx.media.length, '两份附页应各嵌一张图').toBe(2);
    expect(docx.compress_marks, '只有 2400px 那张该标「已压缩」').toBe(1);

    const small = docx.media.find((item) => item.width === 800);
    const big = docx.media.find((item) => item.width === 1600);
    expect(small, '透明 PNG 应保持 800×600').toBeTruthy();
    expect(big, '2400×1800 应等比缩到 1600×1200').toBeTruthy();
    expect([big.width, big.height]).toEqual([1600, 1200]);

    // 透明区（左上角）铺白后必须是白的；铺错就是大面积黑块
    const corner = small.corner;
    expect(corner.every((value) => value >= 240),
        `透明区应铺成白色，实际 RGB=${corner}`).toBe(true);
    expect(small.bands.top, '非透明区域的内容应保留（顶部红带）').toBe('红');

    expectNoProblems(diagnostics, '图片管线');
});
