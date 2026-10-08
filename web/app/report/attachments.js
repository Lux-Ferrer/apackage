/* 附页（缺陷报告）的渲染数据与版式换算：引擎与数据层之间的那一层。
 *
 * 与 `webapp/services/defects.py::attachment_views` + `webapp/services/word_report.py`
 * 的附页部分一一对应。分成两半，是为了让"能在 Node 里跑的"与"必须在浏览器里跑的"分开：
 *
 *   - **纯函数**：`fitImageTwips` / `attachmentRows`（版式换算 → 数值，无副作用）
 *   - **装配**：`attachmentViews()` —— 现压图片副本（`exportCopy`），**导出时现压、不落库**，
 *     与 Python 的 `defects.attachment_views(rows, workdir)` 同构。
 *
 * 图片**读不出来也要把附页导出去**：任何一张图坏掉只把这一项标成 `missing`，
 * 排版层降级成「（图片缺失：原名）」，绝不让整份报告失败。
 */

import { CONFIG } from '../config.js';
import { SPEC } from './spec.js';
import { fieldValues } from '../repo/defects.js';
import { originalNameFromPath } from '../repo/images.js';
import { exportCopy } from '../image-pipeline.js';

/** 附页版式参数（唯一数据源是 report_layout.json 的 attachment 段）。 */
export const ATTACHMENT = SPEC.attachment;

/** 96 DPI 下 1 px = 15 twips（用于"不放大原图"的上限，与 Python 侧同源）。 */
export const NATIVE_TWIPS_PER_PIXEL = 1440 / 96;

/**
 * 像素尺寸 → 嵌入用的 twips：适配附页的最大宽/高，且**不放大**。
 *
 * 上限取 `min(最大宽/像素宽, 最大高/像素高, 1px=15twips)` —— 最后一项保证小图不会被
 * 拉伸到超过其 96 DPI 的自然尺寸。
 */
export function fitImageTwips(widthPx, heightPx, spec = ATTACHMENT) {
    if (!(widthPx > 0) || !(heightPx > 0)) return [0, 0];
    const scale = Math.min(
        spec.imageMaxWidthTwips / widthPx,
        spec.imageMaxHeightTwips / heightPx,
        NATIVE_TWIPS_PER_PIXEL,
    );
    return [Math.round(widthPx * scale), Math.round(heightPx * scale)];
}

/**
 * 附页的两列信息表（需求报告 4.4）：标签列加粗居中、内容列左对齐。
 *
 * 行序由 `CONFIG.ATTACHMENT_ORDER` 决定（与 Python 的 `config.ATTACHMENT_ORDER` 同源）。
 */
export function attachmentRows(view) {
    const values = fieldValues(view);
    return CONFIG.ATTACHMENT_ORDER.map((key) => ({
        label: CONFIG.ATTACHMENT_LABELS[key],
        value: values[key],
        height: ATTACHMENT.rowHeightTwips,
    }));
}

/**
 * 缺陷行 → 附页渲染数据（导出流程用）。
 *
 * @param {Array} rows  缺陷行（含 `image_path`）
 * @param {object} options
 *   loadImage: `async (key) => Blob|null`   按 image_key 取原图（UI 传 IndexedDB 读取器）
 *   codec:     `{decode, createCanvas}`     注入的编解码器（Node 端是头部读取替身）
 *   maxPixels / quality                     导出副本参数，默认取版式规格
 * @returns {Promise<Array>} 每项：`{defect, original_name, missing, compressed,
 *                                  image_bytes, image_width_px, image_height_px}`
 */
export async function attachmentViews(rows, options = {}) {
    const loadImage = options.loadImage ?? (async () => null);
    const maxPixels = options.maxPixels ?? ATTACHMENT.imageMaxPixels;
    const quality = options.quality ?? ATTACHMENT.imageJpegQuality / 100;

    const views = [];
    for (const row of rows) {
        const relative = row.image_path;
        const view = {
            defect: row,
            original_name: originalNameFromPath(relative),
            image_bytes: null,
            image_width_px: 0,
            image_height_px: 0,
            compressed: false,
            missing: Boolean(relative),
        };

        if (relative) {
            const blob = await loadImage(relative);
            if (blob) {
                const prepared = await safeExportCopy(blob,
                    { ...options.codec, maxPixels, quality });
                if (prepared) {
                    view.image_bytes = new Uint8Array(await prepared.blob.arrayBuffer());
                    view.image_width_px = prepared.width;
                    view.image_height_px = prepared.height;
                    view.compressed = prepared.compressed;
                    view.missing = false;
                }
            }
        }
        views.push(view);
    }
    return views;
}

/** 一张图压不出来只影响这一项（对应 Python 里 `export_copy` 的 `except → None`）。 */
async function safeExportCopy(blob, options) {
    try {
        return await exportCopy(blob, options);
    } catch {
        return null;
    }
}
