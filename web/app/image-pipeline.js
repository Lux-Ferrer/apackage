/* 隐患图片管线：EXIF 摆正 → 等比缩放 → JPEG 现压 → 缩略图。
 *
 * 与 `webapp/services/images.py` 的 `_oriented_rgb` / `export_copy` / `thumbnail_bytes`
 * 是同一个职责，只是换了实现介质（Python 用 Pillow，浏览器用 canvas）。
 *
 * 三个决定，先说清楚理由：
 *
 * 1. **编解码器是注入的（`decode` / `createCanvas`）**。canvas 是浏览器独占能力，
 *    Node 里没有（`createImageBitmap` / `OffscreenCanvas` 都是 undefined），
 *    而"摆正后的尺寸、缩放决策、缩略图参数"这些**决策逻辑**必须能在 Node 里跑测试。
 *    所以本模块把"画布与解码"留在边界外，自己只做决策与编排：
 *    默认实现用浏览器 API，测试注入假编解码器。
 *
 * 2. **原图是证据，只压派生副本**。导入时 `prepareImage` **不动原图字节**（只额外生成
 *    缩略图，见设计文档 3.4 的那次有意偏离）；导出副本由 `exportCopy` 在导出时现压、
 *    不落库 —— 与 Python 侧"压缩副本是渲染产物"完全同构。所以"已压缩"这个标记
 *    是**导出时**算出来的，不是导入时。
 *
 * 3. **重编码即丢掉 EXIF，这是好事**。手机竖拍照片靠 EXIF Orientation 标记方向；
 *    canvas 画完再编码，产物已经摆正、EXIF 也没了 —— 不会出现"再摆一次"的双重旋转
 *    （Python 侧 `ImageOps.exif_transpose` 同样是像素旋转 + 标记清除）。
 *
 * ⚠️ 已知边界：缩放后的**像素尺寸**用 `Math.round` 等比取整，Pillow 的
 * `Image.thumbnail` 用"floor/ceil 取更接近等比的"，极端长宽比下两者可能差 1px。
 * 因此闸门 A 的附页夹具图片一律取 ≤1600px（不触发缩放），缩放路径由单测 + 真机验证覆盖。
 */

import { CONFIG } from './config.js';

/** 列表缩略图参数。取自 config（唯一真相源），`/100` 是因为 config 存的是 Pillow 的
 *  0~100 质量刻度，而 canvas 的 `quality` 是 0~1。 */
export const THUMB_MAX_PIXELS = CONFIG.THUMBNAIL_MAX_PIXELS;
export const THUMB_QUALITY = CONFIG.THUMBNAIL_JPEG_QUALITY / 100;

/* --------------------------------------------------------------------------
 * 纯函数：方向、尺寸
 * ------------------------------------------------------------------------ */

/** EXIF Orientation 1..8 中哪些是"宽高互换"的（5~8 含 90°/270° 旋转）。 */
export function orientationSwaps(orientation) {
    const value = Number(orientation) || 1;
    return value >= 5 && value <= 8;
}

/** 按 EXIF Orientation 换算摆正后的显示尺寸。 */
export function orientedDimensions(width, height, orientation) {
    return orientationSwaps(orientation) ? [height, width] : [width, height];
}

/** 等比缩放到 ≤ maxPixels（**不放大**），返回整数像素尺寸。 */
export function fitDimensions(width, height, maxPixels) {
    const w = Math.max(1, Math.round(Number(width) || 0));
    const h = Math.max(1, Math.round(Number(height) || 0));
    const limit = Math.max(1, Math.round(Number(maxPixels) || 0));
    const longest = Math.max(w, h);
    if (longest <= limit) return [w, h];
    const scale = limit / longest;
    return [Math.max(1, Math.round(w * scale)), Math.max(1, Math.round(h * scale))];
}

/**
 * EXIF Orientation → canvas 变换矩阵 `[a, b, c, d, e, f]`（`x' = a·x + c·y + e`）。
 *
 * 入参 `displayWidth` / `displayHeight` 是**摆正后**的目标画布尺寸；源图按"存储尺寸"
 * 落图（5~8 时存储尺寸是显示尺寸的宽高互换）。矩阵把源图的四个角映射到目标矩形的四个角，
 * 这张表由 `web/tests/image_pipeline.test.mjs` 用角点映射逐条验证。
 */
export function orientationTransform(orientation, displayWidth, displayHeight) {
    const value = Number(orientation) || 1;
    const swapped = orientationSwaps(value);
    const sourceWidth = swapped ? displayHeight : displayWidth;
    const sourceHeight = swapped ? displayWidth : displayHeight;
    switch (value) {
        case 2: return [1, 0, 0, -1, 0, sourceHeight];              // 水平镜像
        case 3: return [-1, 0, 0, -1, sourceWidth, sourceHeight];   // 旋转 180°
        case 4: return [-1, 0, 0, 1, sourceWidth, 0];               // 垂直镜像
        case 5: return [0, 1, 1, 0, 0, 0];                          // 主对角线转置
        case 6: return [0, 1, -1, 0, sourceHeight, 0];              // 顺时针 90°
        case 7: return [0, -1, -1, 0, sourceHeight, sourceWidth];   // 副对角线转置
        case 8: return [0, -1, 1, 0, 0, sourceWidth];               // 逆时针 90°
        default: return [1, 0, 0, 1, 0, 0];
    }
}

/* --------------------------------------------------------------------------
 * 纯函数：JPEG 头部读取（EXIF 降级路径）
 * ------------------------------------------------------------------------ */

/**
 * 从 JPEG 字节里读出 EXIF Orientation（1..8），读不到返回 null。
 *
 * 是 `createImageBitmap({imageOrientation:"from-image"})` 的**降级路径**：老浏览器不认
 * 这个选项时得自己看 Orientation 再在 canvas 上转。只做最小解析
 * （扫 APP1 / Exif / TIFF IFD0 的 0x0112），不引第三方库。
 */
export function parseJpegOrientation(bytes) {
    if (!bytes || bytes.length < 4) return null;
    if (bytes[0] !== 0xff || bytes[1] !== 0xd8) return null;      // 不是 JPEG

    const view = new DataView(bytes.buffer ?? bytes, bytes.byteOffset ?? 0, bytes.byteLength);
    let offset = 2;
    while (offset + 4 <= view.byteLength) {
        if (view.getUint8(offset) !== 0xff) return null;
        const marker = view.getUint8(offset + 1);
        if (marker === 0xd8 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) {
            offset += 2;
            continue;
        }
        if (marker === 0xda || marker === 0xd9) return null;       // 进入图像数据
        const size = view.getUint16(offset + 2);
        if (size < 2) return null;
        if (marker === 0xe1 && offset + 10 <= view.byteLength) {
            const tag = String.fromCharCode(
                view.getUint8(offset + 4), view.getUint8(offset + 5),
                view.getUint8(offset + 6), view.getUint8(offset + 7));
            if (tag === 'Exif') {
                const value = readOrientationFromTiff(view, offset + 10, size - 8);
                if (value) return value;
            }
        }
        offset += 2 + size;
    }
    return null;
}

/** 在 TIFF 头里找 IFD0 的 0x0112（Orientation）。 */
function readOrientationFromTiff(view, start, length) {
    if (length < 8 || start + 8 > view.byteLength) return null;
    const little = view.getUint16(start) === 0x4949;
    const read16 = (at) => view.getUint16(at, little);
    const read32 = (at) => view.getUint32(at, little);
    if (read16(start + 2) !== 0x002a) return null;

    const ifd = start + read32(start + 4);
    if (ifd + 2 > view.byteLength) return null;
    const count = read16(ifd);
    for (let index = 0; index < count; index += 1) {
        const entry = ifd + 2 + index * 12;
        if (entry + 12 > view.byteLength) return null;
        if (read16(entry) === 0x0112) {
            const value = read16(entry + 8);
            return value >= 1 && value <= 8 ? value : null;
        }
    }
    return null;
}

/* --------------------------------------------------------------------------
 * 浏览器默认编解码器
 * ------------------------------------------------------------------------ */

export function browserCanvas(width, height) {
    if (typeof OffscreenCanvas !== 'undefined') return new OffscreenCanvas(width, height);
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    return canvas;
}

/**
 * 默认解码器：按 EXIF 摆正解出位图。
 *
 * 首选 `createImageBitmap(..., {imageOrientation:"from-image"})`（Chrome 79+ / Safari 15+），
 * 它直接给出**摆正后**的位图，于是 `orientation = 1`。
 * 退回 `<img>` 时**显式设 `image-orientation: none`**，让"存储像素"原样进来，再由
 * `orientationTransform` 在画布上摆正 —— 这样新旧两种浏览器行为一致（2020 年前
 * `<img>` 默认就是 none，之后默认 from-image，显式声明把两代行为钉在一起）。
 */
export async function defaultDecode(blob) {
    if (typeof createImageBitmap === 'function') {
        try {
            const bitmap = await createImageBitmap(blob, { imageOrientation: 'from-image' });
            return { source: bitmap, width: bitmap.width, height: bitmap.height, orientation: 1 };
        } catch {
            /* 落到下面的 <img> 路径 */
        }
    }
    const url = URL.createObjectURL(blob);
    try {
        const bytes = new Uint8Array(await blob.arrayBuffer());
        const orientation = parseJpegOrientation(bytes) ?? 1;
        const image = await new Promise((resolve, reject) => {
            const element = new Image();
            element.style.imageOrientation = 'none';
            element.onload = () => resolve(element);
            element.onerror = () => reject(new Error('图片解码失败'));
            element.src = url;
        });
        return {
            source: image,
            width: image.naturalWidth || image.width,
            height: image.naturalHeight || image.height,
            orientation,
        };
    } finally {
        URL.revokeObjectURL(url);
    }
}

/**
 * 把解码结果画进 `targetWidth × targetHeight` 的画布并编码。
 *
 * 透明区域先铺白底再画（对应 Python 的 `_flatten_to_rgb`），否则 PNG 转 JPEG 会出黑底。
 */
export async function encodeViaCanvas(decoded, targetWidth, targetHeight,
    { quality = 0.8, createCanvas = browserCanvas, mime = 'image/jpeg' } = {}) {
    const canvas = createCanvas(targetWidth, targetHeight);
    const context = typeof canvas.getContext === 'function'
        ? canvas.getContext('2d') : canvas.getContext;
    const [a, b, c, d, e, f] = orientationTransform(
        decoded.orientation ?? 1, targetWidth, targetHeight);
    const swapped = orientationSwaps(decoded.orientation ?? 1);
    const sourceWidth = swapped ? targetHeight : targetWidth;
    const sourceHeight = swapped ? targetWidth : targetHeight;

    context.save();
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, targetWidth, targetHeight);
    context.setTransform(a, b, c, d, e, f);
    context.drawImage(decoded.source, 0, 0, sourceWidth, sourceHeight);
    context.restore();
    return canvas.convertToBlob({ type: mime, quality });
}

/* --------------------------------------------------------------------------
 * 编排
 * ------------------------------------------------------------------------ */

/**
 * 导入一张上传图片：校验后的原图 + 缩略图 + 尺寸。
 *
 * **原图字节原样落库**（只读它的尺寸与 EXIF 方向），有损处理一概不做 —— 与 Python
 * 侧"原图是证据"一致。缩略图是唯一落库的派生值（设计文档 3.4 的有意偏离）。
 *
 * @returns {Promise<{blob, thumb, width, height, bytes, mime, source_bytes}>}
 *   `width` / `height` 是**原图按 EXIF 摆正后**的像素尺寸。
 */
export async function prepareImage(file, options = {}) {
    const decode = options.decode ?? defaultDecode;
    const createCanvas = options.createCanvas ?? browserCanvas;
    const thumbMaxPixels = options.thumbMaxPixels ?? THUMB_MAX_PIXELS;

    const decoded = await decode(file);
    const [width, height] = orientedDimensions(
        decoded.width, decoded.height, decoded.orientation ?? 1);
    const [thumbWidth, thumbHeight] = fitDimensions(width, height, thumbMaxPixels);
    const thumb = await encodeViaCanvas(decoded, thumbWidth, thumbHeight,
        { quality: options.thumbQuality ?? THUMB_QUALITY, createCanvas, mime: 'image/jpeg' });

    return {
        blob: file,
        thumb,
        width,
        height,
        bytes: file.size ?? 0,
        mime: file.type || 'image/jpeg',
        source_bytes: file.size ?? 0,
    };
}

/**
 * 导出副本：**导出时现压**（不落库），对齐 Python 的 `images.export_copy`。
 *
 * **一律重压成 JPEG**（哪怕没有缩小）：
 *   - 与 Python 的 `export_copy` 一致（那边也是无条件 `rgb.save(target, "JPEG")`）；
 *   - 顺带把 EXIF 丢掉、PNG 转成 JPEG —— 一张 1600px 的 PNG 截图原样嵌进 docx 能有好几 MB。
 * `compressed` 只表示**是否真的缩小过**（Pillow 的 `was_large`），附页里显示成「已压缩」。
 *
 * @returns {Promise<{blob, width, height, compressed}>}
 */
export async function exportCopy(blob, options = {}) {
    const decode = options.decode ?? defaultDecode;
    const createCanvas = options.createCanvas ?? browserCanvas;
    const maxPixels = options.maxPixels ?? 1600;

    const decoded = await decode(blob);
    const [width, height] = orientedDimensions(
        decoded.width, decoded.height, decoded.orientation ?? 1);
    const compressed = Math.max(width, height) > maxPixels;
    const [targetWidth, targetHeight] = fitDimensions(width, height, maxPixels);
    const encoded = await encodeViaCanvas(decoded, targetWidth, targetHeight,
        { quality: options.quality ?? 0.8, createCanvas, mime: 'image/jpeg' });
    return { blob: encoded, width: targetWidth, height: targetHeight, compressed };
}

/**
 * 只重建缩略图（改了缩略图参数时用，对应设计文档 3.4 的"代价"一栏）。
 * 接受**原图** blob，所以不需要重压全尺寸副本。
 */
export async function rebuildThumbnail(blob, options = {}) {
    const decode = options.decode ?? defaultDecode;
    const createCanvas = options.createCanvas ?? browserCanvas;
    const decoded = await decode(blob);
    const [width, height] = orientedDimensions(
        decoded.width, decoded.height, decoded.orientation ?? 1);
    const [thumbWidth, thumbHeight] = fitDimensions(width, height,
        options.thumbMaxPixels ?? THUMB_MAX_PIXELS);
    return encodeViaCanvas(decoded, thumbWidth, thumbHeight,
        { quality: options.thumbQuality ?? THUMB_QUALITY, createCanvas, mime: 'image/jpeg' });
}
