/* 图片头部读取（JPEG SOF / PNG IHDR）+ EXIF 剥离。
 *
 * 这是**测试设施**（`tools/js/image-headers.mjs`），但它是 Node 端闸门替身的承重件：
 * 替身靠它算出"这张图多大"，算错就会让闸门祝福一个错的产物。所以它值得直接单测，
 * 而不只依赖闸门本身。
 *
 * 用例用的是**真实的夹具图片字节**（tests/fixtures/attachment/），不是构造出来的假头 ——
 * 这样连"Pillow 写出来的 JPEG 长什么样"也一并锁住了。
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { parseJpegOrientation, orientedDimensions } from '../app/image-pipeline.js';
import { parseImageSize, stripJpegExif } from '../../tools/js/image-headers.mjs';

const FIXTURES = new URL('../..//tests/fixtures/attachment/', import.meta.url);
const PORTRAIT = '9c8b7a6d5e4f3a2b1c0d9e8f7a6b5c4d_现场照片_竖拍.jpg';
const PORTRAIT_ORIENTED = '9c8b7a6d5e4f3a2b1c0d9e8f7a6b5c4d_现场照片_竖拍_摆正.jpg';
const LANDSCAPE = '5f3a1c7e9b2d4a6f8c0e1d2b3a4c5d6e_现场照片_横拍.jpg';

const read = (name) => new Uint8Array(readFileSync(new URL(name, FIXTURES)));

test('parseImageSize：读出真实夹具 JPEG 的存储尺寸', () => {
    assert.deepEqual(parseImageSize(read(LANDSCAPE)), { width: 800, height: 600, type: 'jpeg' });
    // 竖拍图**存储**是 600×800（方向靠 EXIF，不靠像素）
    assert.deepEqual(parseImageSize(read(PORTRAIT)), { width: 600, height: 800, type: 'jpeg' });
    assert.deepEqual(parseImageSize(read(PORTRAIT_ORIENTED)),
        { width: 800, height: 600, type: 'jpeg' });
});

test('夹具自洽：竖拍图 = 摆正副本按 EXIF 方向摆正后的结果', () => {
    const stored = parseImageSize(read(PORTRAIT));
    const orientation = parseJpegOrientation(read(PORTRAIT));
    const oriented = parseImageSize(read(PORTRAIT_ORIENTED));
    assert.equal(orientation, 6, '竖拍图必须带 EXIF Orientation=6');
    assert.deepEqual(orientedDimensions(stored.width, stored.height, orientation),
        [oriented.width, oriented.height]);
    // 摆正副本自己不该再带方向标记（否则会被"再摆一次"）
    assert.equal(parseJpegOrientation(read(PORTRAIT_ORIENTED)), null);
    assert.equal(parseJpegOrientation(read(LANDSCAPE)), null);
});

test('parseImageSize：PNG 走 IHDR', () => {
    // 1×1 透明 PNG（最小合法文件）
    const png = new Uint8Array(Buffer.from(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8AAAwAB/AGt'
        + 'C0G0AAAAAElFTkSuQmCC', 'base64'));
    assert.deepEqual(parseImageSize(png), { width: 1, height: 1, type: 'png' });
});

test('parseImageSize：认不出/截断 → null（不抛错）', () => {
    assert.equal(parseImageSize(null), null);
    assert.equal(parseImageSize(new Uint8Array(0)), null);
    assert.equal(parseImageSize(new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8, 9])), null);
    assert.equal(parseImageSize(read(LANDSCAPE).slice(0, 40)), null, 'SOF 之前截断');
    assert.equal(parseImageSize(read(PORTRAIT_ORIENTED).slice(0, 10)), null);
});

test('stripJpegExif：剥掉 EXIF 段，其余字节与尺寸不变', () => {
    const original = read(PORTRAIT);
    const stripped = stripJpegExif(original);

    assert.ok(stripped.length < original.length, '剥掉 EXIF 后应该更短');
    assert.equal(parseJpegOrientation(stripped), null, '剥完不该再读得出方向');
    assert.deepEqual(parseImageSize(stripped), parseImageSize(original), '尺寸不受影响');
    // SOI / EOI 保留
    assert.deepEqual([stripped[0], stripped[1]], [0xff, 0xd8]);
    assert.deepEqual([stripped.at(-2), stripped.at(-1)], [0xff, 0xd9]);
});

test('stripJpegExif：没有 EXIF 时原样返回（不破坏字节）', () => {
    const original = read(LANDSCAPE);
    const stripped = stripJpegExif(original);
    assert.deepEqual([...stripped], [...original]);
});

test('stripJpegExif：非 JPEG 原样返回', () => {
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 1, 2, 3]);
    assert.deepEqual([...stripJpegExif(png)], [...png]);
});
