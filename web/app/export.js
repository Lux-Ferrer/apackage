/* 项目级 Word 导出：数据 → docx → 下载。
 *
 * 与 Flask 的 `routes/projects.py::export` 对应。换到浏览器之后**唯一实质的区别**是
 * "交付方式"：那边是 `send_file`，这边是造一个 Blob URL 再点一个 `<a download>`。
 * 产物本身由 `report/engine.js` 生成 —— 它已经被闸门 A/B 锁死，这里不参与排版。
 *
 * 三件容易做错的事，都写在这里：
 *  1. **文件名**必须按 `config.REPORT_FILENAME` 拼，并清理非法字符（对应 Python 的
 *     `report_filename`）—— 手机上文件名带 `/` 或 `:` 会直接下载失败；
 *  2. **有附页 / 无附页是两条路径**：没有关联报告时不要白跑一遍图片现压；
 *  3. 图片现压必须在**读取阶段**做完（IndexedDB 的事务纪律），这一点由
 *     `report/attachments.js` 负责，本模块只是调用方。
 */

import { CONFIG } from './config.js';
import { SPEC } from './report/spec.js';
import { attachmentViews } from './report/attachments.js';
import { renderDocx } from './report/engine.js';
import * as defects from './repo/defects.js';
import * as images from './repo/images.js';
import * as measurements from './repo/measurements.js';
import * as projects from './repo/projects.js';

const UNSAFE_FILENAME_CHARS = '\\/:*?"<>|';

/** `项目编号_房屋名称_检测报告.docx`（清理非法字符并限长，对应 Python 的 report_filename）。 */
export function reportFilename(project) {
    const dot = CONFIG.REPORT_FILENAME.lastIndexOf('.');
    const template = dot >= 0 ? CONFIG.REPORT_FILENAME.slice(0, dot) : CONFIG.REPORT_FILENAME;
    const extension = dot >= 0 ? CONFIG.REPORT_FILENAME.slice(dot + 1) : 'docx';
    const stem = template
        .replace('{project_no}', project?.project_no ?? '')
        .replace('{house_name}', project?.house_name ?? '');
    const cleaned = Array.from(stem)
        .map((char) => (UNSAFE_FILENAME_CHARS.includes(char) || char.charCodeAt(0) < 32 ? '_' : char))
        .join('')
        .trim()
        .replace(/^\.+|\.+$/g, '');
    return `${(cleaned || '检测报告').slice(0, 120)}.${extension || 'docx'}`;
}

/**
 * 生成一份项目报告。
 *
 * @param {object} db
 * @param {number|string} projectId
 * @param {object} [options]
 *   withAttachments  是否把关联缺陷报告作为附页追加（默认 false）
 *   baseDocxBytes    底座模板字节（提供 styles/theme）；不传则跳过第 ⑥ 个补丁 —— 只该在测试里这么做
 *   onProgress       `(stage) => void`，用于"正在生成"提示
 * @returns {Promise<{bytes: Uint8Array, filename: string, attachmentCount: number}>}
 */
export async function buildProjectReport(db, projectId, options = {}) {
    const onProgress = options.onProgress ?? (() => {});
    onProgress('读取项目');
    const project = await projects.get(db, projectId);
    if (!project) throw new NotFoundError(`项目不存在：#${projectId}`);

    onProgress('读取检测记录');
    const groups = await measurements.groupedByTemplate(db, project.id);
    const totalRecords = groups.reduce((sum, group) => sum + group.records.length, 0);
    if (!totalRecords) throw new EmptyProjectError('这个项目还没有检测记录，先录入再导出。');

    let views = [];
    if (options.withAttachments) {
        const rows = await defects.listForProject(db, project.id);
        if (rows.length) {
            onProgress(`压缩附页图片（${rows.length} 份）`);
            views = await attachmentViews(rows, {
                loadImage: async (key) => {
                    const record = await images.get(db, key);
                    return record ? record.blob : null;
                },
                // ⚠️ 必须把注入的编解码器传下去：浏览器里留空（走 canvas 默认实现），
                // Node/jsdom 测试里是替身。漏传的后果很隐蔽 —— 附页会**静默降级成"图片缺失"**
                // 而不是报错（被 safeExportCopy 吞掉了），只有闸门/测试读 XML 才发现。
                codec: options.pipeline,
                maxPixels: SPEC.attachment.imageMaxPixels,
                quality: SPEC.attachment.imageJpegQuality / 100,
            });
        }
    }

    onProgress('生成 Word');
    const bytes = await renderDocx(project, groups, {
        attachments: views,
        baseDocxBytes: options.baseDocxBytes,
    });
    return {
        bytes,
        filename: reportFilename(project),
        attachmentCount: views.length,
        recordCount: totalRecords,
    };
}

/** 项目不存在。 */
export class NotFoundError extends Error {
    constructor(message) {
        super(message);
        this.name = 'NotFoundError';
    }
}

/** 空项目导出：单独一个错误类型，UI 可以给"先去录入"这样的引导。 */
export class EmptyProjectError extends Error {
    constructor(message) {
        super(message);
        this.name = 'EmptyProjectError';
    }
}

/**
 * 触发下载。
 *
 * 用 Blob URL + `<a download>`，不依赖 File System Access API（iOS Safari 没有）。
 * 一定要 `revokeObjectURL`：手机上几十 MB 的 URL 不释放会一直占着内存。
 */
export function downloadBlob(blobOrBytes, filename, { document: doc = globalThis.document } = {}) {
    const blob = blobOrBytes instanceof Blob
        ? blobOrBytes
        : new Blob([blobOrBytes], { type: DOCX_MIME });
    const url = URL.createObjectURL(blob);
    const anchor = doc.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.rel = 'noopener';
    doc.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    // 立刻 revoke 在部分浏览器上会打断下载；给一个宽裕的延迟
    globalThis.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    return { url, size: blob.size, filename };
}

export const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

/** 「导出 Word」按钮的统一入口：生成 + 下载 + 给一句结果文案。 */
export async function exportProject(db, projectId, options = {}) {
    const result = await buildProjectReport(db, projectId, options);
    downloadBlob(result.bytes, result.filename, options);
    return result;
}
