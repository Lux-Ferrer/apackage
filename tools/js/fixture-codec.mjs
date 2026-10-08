/* 闸门 A 用的**编解码替身**：让 JS 图片管线能在 Node 里跑完整条决策链。
 *
 * 这个文件存在的唯一原因是：**Node 没有 canvas**。浏览器上真实链路是
 *   createImageBitmap({imageOrientation:'from-image'}) → OffscreenCanvas → convertToBlob
 * 而闸门 A 要在 Node 里产出 docx，于是把这条链路的两个端点换成替身：
 *
 *   解码（4 件事都做**真的**）
 *     ① 从文件头读出存储尺寸            → tools/js/image-headers.mjs
 *     ② 读出 EXIF Orientation          → **复用产品代码** web/app/image-pipeline.js
 *     ③ 按方向算出显示尺寸              → **复用产品代码** orientedDimensions()
 *     ④ 返回 orientation 让画布变换生效  → 产品代码的 orientationTransform() 因此被真正执行
 *
 *   编码（**只是替身**）
 *     交出这份夹具的"已摆正、无 EXIF"字节。已摆正从哪来？夹具旁边那份 `_摆正` 副本
 *     （由 tools/attachment_fixture.py 用 Pillow 生成）。**没有它就直接抛错** ——
 *     宁可让闸门红，也不接受"把没摆正的像素塞进已摆正的尺寸里"这种假产物。
 *
 * 替身**不做重压缩**（那是 canvas 的活）：因此闸门 A 的夹具图片一律 ≤1600px。
 * 需要缩放的路径由 web/tests/image_pipeline.test.mjs + 真机验证覆盖；
 * 一旦替身被要求缩放，同样直接抛错（尺寸断言会先挡住）。
 *
 * 替身仍会核对"编出来的尺寸 == 管线声明的显示尺寸"，所以方向算错、尺寸算错都跑不掉；
 * 而"嵌进去的字节到底多大"由闸门的 `media` 像素尺寸独立核对。
 *
 * 用法：**一份图片一个替身**，所以不需要在编解码之间传递状态。
 *   - 带 EXIF 方向的图 → `imageCodec({path, orientedPath, readFile})`
 *   - 无方向问题的图   → `passthroughCodec({path, readFile})`
 */

import { orientedDimensions, parseJpegOrientation } from '../../web/app/image-pipeline.js';
import { parseImageSize, stripJpegExif } from './image-headers.mjs';

/**
 * 带 EXIF 方向的图片：替身按方向算显示尺寸，编码时交出**摆正副本**的字节。
 *
 * @param {object} options
 *   path:         源图在仓库内的相对路径（用于报错信息）
 *   orientedPath: 该图的"已摆正副本"路径（由 attachment_fixture.py 生成，必填）
 *   readFile:     `(path) => Uint8Array|null`
 *   log:          `(entry) => void` 记录解码结果（供 CLI 打印）
 * @returns {{decode: Function, createCanvas: Function}}
 */
export function imageCodec(options) {
    const { path, readFile, orientedPath = null, log } = options;

    const decode = async () => {
        const bytes = readFile(path);
        if (!bytes) throw new Error(`夹具图片读不到：${path}`);

        const size = parseImageSize(bytes);
        if (!size) throw new Error(`认不出图片格式：${path}`);

        const orientation = size.type === 'jpeg' ? (parseJpegOrientation(bytes) ?? 1) : 1;
        const [width, height] = orientedDimensions(size.width, size.height, orientation);
        log?.({ path, stored: [size.width, size.height], orientation, display: [width, height] });
        // 注意 width/height 返回的是**存储**尺寸 + orientation：摆正是画布变换的职责，
        // 这样产品代码的 orientationTransform() 才真的被执行到（而不是被替身绕过）。
        return {
            source: { bytes },
            width: size.width,
            height: size.height,
            orientation,
        };
    };

    const createCanvas = (width, height) => ({
        width,
        height,
        getContext: () => ({
            save() {}, restore() {}, setTransform() {}, fillRect() {},
            fillStyle: '', drawImage() {},
        }),
        convertToBlob: async () => {
            const source = orientedBytes();
            const size = parseImageSize(source);
            if (size.width !== width || size.height !== height) {
                throw new Error(
                    `夹具替身尺寸对不上：管线要求 ${width}×${height}，`
                    + `可用字节是 ${size.width}×${size.height}（${path}）。\n`
                    + '  常见原因：这张图需要**缩放**（Node 端替身做不到，'
                    + '请让夹具图片保持在 1600px 以内），或 _摆正 副本没生成。');
            }
            return {
                size: source.length,
                type: 'image/jpeg',
                arrayBuffer: async () => source.buffer.slice(
                    source.byteOffset, source.byteOffset + source.byteLength),
            };
        },
    });

    function orientedBytes() {
        const bytes = readFile(orientedPath);
        if (!bytes) {
            throw new Error(
                `摆正副本读不到：${orientedPath}（源图 ${path}）。\n`
                + '  请运行 python tools/attachment_fixture.py 重新生成夹具。');
        }
        return bytes;
    }

    return { decode, createCanvas };
}

/**
 * 无 EXIF 方向、无需摆正的图片：字节直通，只剥掉 EXIF（保持产物干净）。
 * 与 :func:`imageCodec` 分开是为了让"这张图根本没方向问题"这件事在夹具里显式可见。
 */
export function passthroughCodec({ path, readFile }) {
    let bytes = null;
    const decode = async () => {
        bytes = readFile(path);
        if (!bytes) throw new Error(`夹具图片读不到：${path}`);
        const size = parseImageSize(bytes);
        if (!size) throw new Error(`认不出图片格式：${path}`);
        return { source: {}, width: size.width, height: size.height, orientation: 1 };
    };
    const createCanvas = (width, height) => ({
        width,
        height,
        getContext: () => ({
            save() {}, restore() {}, setTransform() {}, fillRect() {},
            fillStyle: '', drawImage() {},
        }),
        convertToBlob: async () => {
            const stripped = stripJpegExif(bytes);
            const size = parseImageSize(stripped);
            if (size.width !== width || size.height !== height) {
                throw new Error(`夹具替身尺寸对不上：${width}×${height} vs ${size.width}×${size.height}`);
            }
            return {
                size: stripped.length,
                type: 'image/jpeg',
                arrayBuffer: async () => stripped.buffer.slice(
                    stripped.byteOffset, stripped.byteOffset + stripped.byteLength),
            };
        },
    });
    return { decode, createCanvas };
}

export { parseImageSize, stripJpegExif };
