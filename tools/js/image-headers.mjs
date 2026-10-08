/* Node 端的**图片头部读取**：JPEG SOF / PNG IHDR 的像素尺寸。
 *
 * 为什么需要它：闸门 A 要在 Node 里跑，而 Node 没有 canvas
 * （`createImageBitmap` / `OffscreenCanvas` 都是 undefined），
 * 拿不到"解码后的位图"。但替身需要的其实只有两件事：
 *   ① 图片的**显示尺寸**（读文件头 + EXIF 方向即可，不需要解码像素）；
 *   ② 一份"已摆正、无 EXIF"的字节（见 fixture-codec.mjs）。
 * 这两件事都可以在 Node 里做对，于是闸门 A 的附页部分不是"跳过验证"，而是**换了个替身**。
 *
 * ⚠️ 不要用它替代浏览器路径做产品逻辑 —— 它只服务测试设施。它的正确性由
 * `web/tests/image_headers.test.mjs` 与闸门本身（`media` 像素尺寸核对）双重上锁。
 */

const SOF_MARKERS = new Set([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7,
    0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf]);

/**
 * 读出图片的**存储尺寸**（不考虑 EXIF 方向）与格式。
 *
 * @param {Uint8Array} bytes
 * @returns {{width: number, height: number, type: 'jpeg'|'png'}|null}
 */
export function parseImageSize(bytes) {
    if (!bytes || bytes.length < 8) return null;
    if (bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e) return parsePng(bytes);
    if (bytes[0] === 0xff && bytes[1] === 0xd8) return parseJpeg(bytes);
    return null;
}

function parsePng(bytes) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    // IHDR 必须是第一个块：8 字节签名 + 4 长度 + 4 类型
    if (view.byteLength < 24) return null;
    if (view.getUint32(12) !== 0x49484452) return null;          // 'IHDR'
    return { width: view.getUint32(16), height: view.getUint32(20), type: 'png' };
}

function parseJpeg(bytes) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    let offset = 2;
    while (offset + 4 <= view.byteLength) {
        if (view.getUint8(offset) !== 0xff) return null;
        const marker = view.getUint8(offset + 1);
        if (marker === 0xd8 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) {
            offset += 2;
            continue;
        }
        if (marker === 0xda || marker === 0xd9) return null;       // 进入扫描数据
        const size = view.getUint16(offset + 2);
        if (size < 2) return null;
        if (SOF_MARKERS.has(marker)) {
            if (offset + 9 > view.byteLength) return null;
            return {
                height: view.getUint16(offset + 5),
                width: view.getUint16(offset + 7),
                type: 'jpeg',
            };
        }
        offset += 2 + size;
    }
    return null;
}

/**
 * 去掉 JPEG 的 APP1/Exif 段，其余字节原样保留。
 *
 * 为什么需要：canvas 画一遍再编码，产物是**已摆正且没有 EXIF** 的。
 * 替身没法旋转像素（见 fixture-codec.mjs），但至少要把 EXIF 拿掉 ——
 * 否则 Word 会按残留的方向标记"再摆一次"，那是一个我们不会真的交付的产物。
 */
export function stripJpegExif(bytes) {
    if (!(bytes[0] === 0xff && bytes[1] === 0xd8)) return bytes;
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const pieces = [bytes.subarray(0, 2)];
    let offset = 2;
    while (offset + 4 <= view.byteLength) {
        if (view.getUint8(offset) !== 0xff) break;
        const marker = view.getUint8(offset + 1);
        if (marker === 0xda) break;                                // 扫描数据：原样收尾
        if (marker === 0xd8 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) {
            pieces.push(bytes.subarray(offset, offset + 2));
            offset += 2;
            continue;
        }
        const size = view.getUint16(offset + 2);
        if (size < 2 || offset + 2 + size > view.byteLength) break;
        const isExif = marker === 0xe1
            && String.fromCharCode(...bytes.subarray(offset + 4, offset + 8)) === 'Exif';
        if (!isExif) pieces.push(bytes.subarray(offset, offset + 2 + size));
        offset += 2 + size;
    }
    pieces.push(bytes.subarray(offset));
    return concat(pieces);
}

function concat(pieces) {
    const total = pieces.reduce((sum, piece) => sum + piece.length, 0);
    const out = new Uint8Array(total);
    let at = 0;
    for (const piece of pieces) {
        out.set(piece, at);
        at += piece.length;
    }
    return out;
}
