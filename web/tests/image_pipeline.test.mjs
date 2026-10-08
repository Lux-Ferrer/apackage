/* 图片管线：EXIF 摆正矩阵、缩放决策、导入/导出编排。
 *
 * Node 里没有 canvas（`createImageBitmap` / `OffscreenCanvas` 都是 undefined），
 * 这是**设计就承认的边界**：本测试用假编解码器验证"决策"，像素级重采样由真机验证覆盖。
 * 其中 `orientationTransform` 那张 8 项矩阵表用**角点映射**逐条验证 —— 它是最容易写错的
 * 一处（写错就会双重旋转），而矩阵是纯数学，可以完全离线验。
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
    THUMB_MAX_PIXELS, encodeViaCanvas, exportCopy, fitDimensions, orientationSwaps,
    orientedDimensions, orientationTransform, parseJpegOrientation, prepareImage,
    rebuildThumbnail,
} from '../app/image-pipeline.js';

/* --------------------------------------------------------------------------
 * 纯函数：方向与尺寸
 * ------------------------------------------------------------------------ */

test('orientationSwaps：只有 5~8 是宽高互换的', () => {
    assert.deepEqual([1, 2, 3, 4, 5, 6, 7, 8].map(orientationSwaps),
        [false, false, false, false, true, true, true, true]);
    assert.equal(orientationSwaps(undefined), false);
    assert.equal(orientationSwaps('6'), true);
});

test('orientedDimensions：竖拍（Orientation=6）存储 600×800 → 显示 800×600', () => {
    assert.deepEqual(orientedDimensions(600, 800, 6), [800, 600]);
    assert.deepEqual(orientedDimensions(600, 800, 8), [800, 600]);
    assert.deepEqual(orientedDimensions(600, 800, 1), [600, 800]);
    assert.deepEqual(orientedDimensions(600, 800, 3), [600, 800]);
    assert.deepEqual(orientedDimensions(600, 800, null), [600, 800]);
});

test('fitDimensions：只缩不放，长边贴合上限', () => {
    assert.deepEqual(fitDimensions(3200, 2400, 1600), [1600, 1200]);
    assert.deepEqual(fitDimensions(2400, 3200, 1600), [1200, 1600]);
    assert.deepEqual(fitDimensions(800, 600, 1600), [800, 600]);      // 不放大
    assert.deepEqual(fitDimensions(1600, 1600, 1600), [1600, 1600]);  // 恰好等于上限不算超
    assert.deepEqual(fitDimensions(100, 100, THUMB_MAX_PIXELS), [100, 100]);
    assert.deepEqual(fitDimensions(1, 4000, 1600), [1, 1600]);        // 极窄图不塌成 0
});

/* --------------------------------------------------------------------------
 * EXIF 摆正矩阵：用角点映射验证，而不是对拍矩阵字面量
 * ------------------------------------------------------------------------ */

/** 把源图左上/右上/左下/右下四个角映射到目标坐标。 */
function cornerMap(orientation, displayWidth, displayHeight) {
    const [a, b, c, d, e, f] = orientationTransform(orientation, displayWidth, displayHeight);
    const swapped = orientationSwaps(orientation);
    const sourceWidth = swapped ? displayHeight : displayWidth;
    const sourceHeight = swapped ? displayWidth : displayHeight;
    const map = (x, y) => [a * x + c * y + e, b * x + d * y + f];
    return {
        box: [displayWidth, displayHeight],
        topLeft: map(0, 0),
        topRight: map(sourceWidth, 0),
        bottomLeft: map(0, sourceHeight),
        bottomRight: map(sourceWidth, sourceHeight),
    };
}

test('orientationTransform：四个角都落在目标矩形内（8 个方向都不越界）', () => {
    for (const orientation of [1, 2, 3, 4, 5, 6, 7, 8]) {
        const { box, topLeft, topRight, bottomLeft, bottomRight }
            = cornerMap(orientation, 800, 600);
        for (const [x, y] of [topLeft, topRight, bottomLeft, bottomRight]) {
            assert.ok(x >= -0.001 && x <= box[0] + 0.001,
                `方向 ${orientation}：x=${x} 超出 [0, ${box[0]}]`);
            assert.ok(y >= -0.001 && y <= box[1] + 0.001,
                `方向 ${orientation}：y=${y} 超出 [0, ${box[1]}]`);
        }
    }
});

test('orientationTransform：关键角点（会抓到"旋转方向反了"/复制粘贴漏改）', () => {
    // 目标画布 800×600；方向 5~8 的源图按存储尺寸 600×800 落图
    // 1 = 原样
    assert.deepEqual(cornerMap(1, 800, 600).topLeft, [0, 0]);
    // 3 = 旋转 180°：源左上 → 目标右下
    assert.deepEqual(cornerMap(3, 800, 600).topLeft, [800, 600]);
    // 6 = 顺时针 90°：源左上 → 目标右上，源右上 → 目标右下
    assert.deepEqual(cornerMap(6, 800, 600).topLeft, [800, 0]);
    assert.deepEqual(cornerMap(6, 800, 600).topRight, [800, 600]);
    // 8 = 逆时针 90°：源左上 → 目标左下，源右上 → 目标左上
    assert.deepEqual(cornerMap(8, 800, 600).topLeft, [0, 600]);
    assert.deepEqual(cornerMap(8, 800, 600).topRight, [0, 0]);
    // 5 = 主对角线转置：源左上不动，源右上 → 目标左下
    assert.deepEqual(cornerMap(5, 800, 600).topLeft, [0, 0]);
    assert.deepEqual(cornerMap(5, 800, 600).topRight, [0, 600]);
    // 7 = 副对角线转置：源左上 → 目标右下
    assert.deepEqual(cornerMap(7, 800, 600).topLeft, [800, 600]);
});

test('orientationTransform：8 个方向的矩阵两两不同（防"抄漏一个"）', () => {
    const seen = new Map();
    for (const orientation of [1, 2, 3, 4, 5, 6, 7, 8]) {
        const key = orientationTransform(orientation, 800, 600).join(',');
        assert.ok(!seen.has(key),
            `方向 ${orientation} 与方向 ${seen.get(key)} 的矩阵相同（${key}）`);
        seen.set(key, orientation);
    }
    assert.equal(seen.size, 8);
});

test('orientationTransform：宽高互换的方向用"显示宽高"反推存储尺寸', () => {
    // 显示 800×600、方向 6 → 存储 600×800（源角点按存储尺寸给）
    const [a, b, c, d, e, f] = orientationTransform(6, 800, 600);
    assert.deepEqual([a, b, c, d, e, f], [0, 1, -1, 0, 800, 0]);
    // 方向 1 时源尺寸就是显示尺寸
    assert.deepEqual(orientationTransform(1, 800, 600), [1, 0, 0, 1, 0, 0]);
    assert.deepEqual(orientationTransform(99, 800, 600), [1, 0, 0, 1, 0, 0]);
});

/* --------------------------------------------------------------------------
 * JPEG EXIF 解析（降级路径）
 * ------------------------------------------------------------------------ */

/** 造一段最小 JPEG：SOI + APP1(Exif + TIFF, Orientation=o) + EOI。 */
function fakeJpegWithOrientation(orientation, { little = true } = {}) {
    const tiff = new Uint8Array(26);
    const view = new DataView(tiff.buffer);
    if (little) {
        view.setUint16(0, 0x4949, true);
    } else {
        view.setUint16(0, 0x4d4d, false);
    }
    view.setUint16(2, 0x002a, little);
    view.setUint32(4, 8, little);          // IFD0 偏移
    view.setUint16(8, 1, little);          // 一个条目
    view.setUint16(10, 0x0112, little);    // Orientation
    view.setUint16(12, 3, little);         // SHORT
    view.setUint32(14, 1, little);         // count
    view.setUint16(18, orientation, little);
    view.setUint32(22, 0, little);         // next IFD

    const exif = new Uint8Array(6 + tiff.length);
    exif.set([0x45, 0x78, 0x69, 0x66, 0x00, 0x00], 0);   // "Exif\0\0"
    exif.set(tiff, 6);

    const size = exif.length + 2;
    const out = new Uint8Array(4 + size + 2);
    out.set([0xff, 0xd8, 0xff, 0xe1], 0);
    new DataView(out.buffer).setUint16(4, size, false);
    out.set(exif, 6);
    out.set([0xff, 0xd9], 6 + exif.length);
    return out;
}

test('parseJpegOrientation：读得出小端/大端 TIFF 里的 Orientation', () => {
    for (const orientation of [1, 3, 6, 8]) {
        assert.equal(parseJpegOrientation(fakeJpegWithOrientation(orientation)), orientation);
        assert.equal(parseJpegOrientation(
            fakeJpegWithOrientation(orientation, { little: false })), orientation);
    }
});

test('parseJpegOrientation：没有 EXIF / 不是 JPEG / 数据截断 → null（不抛错）', () => {
    assert.equal(parseJpegOrientation(null), null);
    assert.equal(parseJpegOrientation(new Uint8Array([0xff, 0xd8, 0xff, 0xd9])), null);
    assert.equal(parseJpegOrientation(new Uint8Array([1, 2, 3, 4, 5, 6])), null);
    assert.equal(parseJpegOrientation(new Uint8Array(0)), null);
    // 截断在 APP1 长度字段处
    assert.equal(parseJpegOrientation(new Uint8Array([0xff, 0xd8, 0xff, 0xe1, 0x00])), null);
    const truncated = fakeJpegWithOrientation(6).slice(0, 12);
    assert.equal(parseJpegOrientation(truncated), null);
});

/* --------------------------------------------------------------------------
 * 编排：假编解码器
 * ------------------------------------------------------------------------ */

/** 假的解码结果 + 假画布：只记录"按什么尺寸编了什么"。 */
function fakeCodec({ width, height, orientation = 1 }) {
    const encoded = [];
    const decode = async () => ({ source: { fake: true }, width, height, orientation });
    const createCanvas = (canvasWidth, canvasHeight) => {
        const canvas = {
            width: canvasWidth,
            height: canvasHeight,
            getContext: () => ({
                save() {}, restore() {}, setTransform() {}, fillRect() {},
                fillStyle: '#fff',
                drawImage() {},
            }),
            convertToBlob: async ({ type, quality }) => {
                encoded.push({ width: canvasWidth, height: canvasHeight, type, quality });
                return { size: canvasWidth * canvasHeight, type };
            },
        };
        return canvas;
    };
    return { decode, createCanvas, encoded };
}

test('prepareImage：原图字节原样保留，只多生成一张缩略图', async () => {
    const file = { size: 2_345_678, type: 'image/jpeg' };
    const codec = fakeCodec({ width: 3200, height: 2400 });

    const record = await prepareImage(file, codec);

    assert.equal(record.blob, file, '原图必须是同一个对象（原图是证据，不重压）');
    assert.equal(record.bytes, 2_345_678);
    assert.equal(record.mime, 'image/jpeg');
    assert.deepEqual([record.width, record.height], [3200, 2400]);
    // 缩略图 240px：只编了一张，且是 JPEG q75
    assert.deepEqual(codec.encoded, [
        { width: 240, height: 180, type: 'image/jpeg', quality: 0.75 },
    ]);
});

test('prepareImage：竖拍照片按 EXIF 摆正后再算缩略图尺寸', async () => {
    const codec = fakeCodec({ width: 600, height: 800, orientation: 6 });
    const record = await prepareImage({ size: 100, type: 'image/jpeg' }, codec);

    assert.deepEqual([record.width, record.height], [800, 600], '记录里存的是摆正后的尺寸');
    assert.deepEqual(codec.encoded, [
        { width: 240, height: 180, type: 'image/jpeg', quality: 0.75 },
    ]);
});

test('exportCopy：未超 1600px → 仍重压成 JPEG，但标为「未压缩」', async () => {
    const codec = fakeCodec({ width: 800, height: 600 });
    const result = await exportCopy({ size: 10, type: 'image/png' }, codec);

    assert.deepEqual([result.width, result.height], [800, 600]);
    assert.equal(result.compressed, false, '没缩小就不该显示「已压缩」');
    assert.deepEqual(codec.encoded, [
        { width: 800, height: 600, type: 'image/jpeg', quality: 0.8 },
    ]);
});

test('exportCopy：超过 1600px → 等比缩小并标为「已压缩」', async () => {
    const codec = fakeCodec({ width: 3200, height: 2400 });
    const result = await exportCopy({ size: 10, type: 'image/jpeg' }, codec);

    assert.deepEqual([result.width, result.height], [1600, 1200]);
    assert.equal(result.compressed, true);
});

test('exportCopy：方向 6 且未超限 → 摆正后按显示尺寸编码', async () => {
    const codec = fakeCodec({ width: 600, height: 800, orientation: 6 });
    const result = await exportCopy({ size: 10, type: 'image/jpeg' }, codec);

    assert.deepEqual([result.width, result.height], [800, 600], '按摆正后的宽高');
    assert.equal(result.compressed, false);
    assert.deepEqual(codec.encoded, [
        { width: 800, height: 600, type: 'image/jpeg', quality: 0.8 },
    ]);
});

test('encodeViaCanvas：按方向设置画布变换（换宽高的方向画的是存储尺寸）', async () => {
    const calls = [];
    const context = {
        save() {}, restore() {}, fillRect() {}, fillStyle: '',
        setTransform(...args) { calls.push(['setTransform', ...args]); },
        drawImage(...args) { calls.push(['drawImage', args[1], args[2], args[3], args[4]]); },
    };
    const createCanvas = (width, height) => ({
        width, height, getContext: () => context,
        convertToBlob: async () => ({ size: 1 }),
    });

    await encodeViaCanvas({ source: {}, width: 600, height: 800, orientation: 6 }, 800, 600,
        { createCanvas });

    assert.deepEqual(calls[0], ['setTransform', 1, 0, 0, 1, 0, 0], '先重置再铺白底');
    assert.deepEqual(calls[1], ['setTransform', 0, 1, -1, 0, 800, 0], '方向 6 的矩阵');
    assert.deepEqual(calls[2], ['drawImage', 0, 0, 600, 800], '源按存储尺寸落图');
});

test('rebuildThumbnail：只重编缩略图，尺寸随参数走', async () => {
    const codec = fakeCodec({ width: 3200, height: 2400 });
    await rebuildThumbnail({ size: 1 }, codec);
    assert.deepEqual(codec.encoded, [
        { width: 240, height: 180, type: 'image/jpeg', quality: 0.75 },
    ]);

    const larger = fakeCodec({ width: 3200, height: 2400 });
    await rebuildThumbnail({ size: 1 }, { ...larger, thumbMaxPixels: 480 });
    assert.deepEqual(larger.encoded, [
        { width: 480, height: 360, type: 'image/jpeg', quality: 0.75 },
    ]);
});
