/* 从图片文件头读出像素尺寸（JPEG SOF / PNG IHDR）。
 *
 * 为什么产品代码需要它
 * --------------------
 * 闸门 C（**不借助 Python 的自检**）要核对"文档里嵌进去的图片到底多大"。
 * 浏览器里当然可以 `createImageBitmap`，但那要解码整张图 —— 而我们只需要两个整数。
 * 读文件头是零成本的，而且**在 Node 里也跑得起来**（没有 canvas 的环境同样可以用）。
 *
 * 这套解析也是"改扩展名的假图片"这类问题的第一道防线：认不出格式就返回 null，
 * 调用方自己决定怎么降级。
 */

/** JPEG 的 SOF 标记（帧头，带尺寸）；C4/C8/CC 是别的用途，不算。 */
const SOF_MARKERS = new Set([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7,
    0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf]);

/** 格式识别（只看魔术字节）。 */
export function sniffImageType(bytes) {
    if (!bytes || bytes.length < 4) return null;
    if (bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) {
        return 'png';
    }
    if (bytes[0] === 0xff && bytes[1] === 0xd8) return 'jpeg';
    if (bytes[0] === 0x47 && bytes[1] === 0x49 && bytes[2] === 0x46) return 'gif';
    if (bytes[0] === 0x42 && bytes[1] === 0x4d) return 'bmp';
    return null;
}

/**
 * 读出图片的**存储尺寸**（不考虑 EXIF 方向）与格式。
 *
 * @param {Uint8Array} bytes
 * @returns {{width: number, height: number, type: string}|null}
 */
export function parseImageSize(bytes) {
    if (!bytes || bytes.length < 8) return null;
    const type = sniffImageType(bytes);
    if (type === 'png') return parsePng(bytes);
    if (type === 'jpeg') return parseJpeg(bytes);
    return null;
}

function parsePng(bytes) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    if (view.byteLength < 24) return null;
    // IHDR 必须是第一个块：8 字节签名 + 4 长度 + 4 类型
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
