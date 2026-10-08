/* 隐患图片：落库（IndexedDB Blob）、命名与可追溯、导出时的现压副本。
 *
 * 与 `webapp/services/images.py` 对应，但换了存储：
 *   Python：原图落盘 `uploads/defects/<uuid>_<原名>.<ext>`，压缩副本导出时现压 **不落库**
 *   M5    ：原图存 `images` store（key 沿用同一个落盘名），**缩略图也在导入时存一份**
 *
 * 两条原则的取舍（要写清楚，免得后人以为是偷懒）：
 *  1. key 仍然用 `<uuid4hex>_<清洗后的原名>.<ext>` —— 于是"从 key 反推原始文件名"
 *     这条既有原则**原样保留**，不需要额外的 original_name 字段，也不需要迁移补字段；
 *  2. **缩略图是唯一的有意偏离**："派生值不落库"在 Web 上靠 HTTP 缓存（`Cache-Control:
 *     immutable`）兜住重复解码，而纯静态 PWA 没有这一层 —— 列表每次渲染都要重新解码
 *     20MB 的 JPEG（手机上 0.1~0.3s/张），所以导入时生成并存一份 240px 缩略图。
 *     全尺寸的导出副本仍然现压、不落库。
 *
 * 本模块**不依赖 canvas**（压缩在 `image-pipeline.js`，浏览器专用），
 * 因此可以在 Node 里用 fake-indexeddb 做数据层测试。
 */

import { CONFIG } from '../config.js';
import { STORE } from '../db.js';
import { clean } from '../clauses.js';
import { prepareImage, rebuildThumbnail } from '../image-pipeline.js';
import { checkUploadQuota, DEFAULT_MAX_IMAGE_BYTES } from '../storage.js';
// 时间戳格式必须与报告一致（附页会按 yyyy-MM-dd HH:mm 显示），故复用同一个实现。
import { stamp } from './defects.js';

/** 图片校验失败（表单层展示原样文案；与 parseForm 的 `errors` 同名同义）。 */
export class ImageError extends Error {
    constructor(message) {
        super(message);
        this.name = 'ImageError';
    }
}

/** 空间不够（UI 应当引导"先导出备份再清理"，而不是让用户重试）。 */
export class QuotaError extends Error {
    constructor(message, status) {
        super(message);
        this.name = 'QuotaError';
        this.status = status;
    }
}

/** Windows/POSIX 下的非法文件名字符（保留中文，去掉分隔符与控制字符）。 */
const UNSAFE_NAME_CHARS = /[\\/:*?"<>|\u0000-\u001f]/g;
const NAME_MAX_LENGTH = 60;

/** 清洗上传时的原始文件名，保留可读性（含中文），去掉危险字符。 */
export function sanitizeOriginalName(name) {
    let text = String(name ?? '').split(/[\\/]/).pop() ?? '';
    text = text.replace(UNSAFE_NAME_CHARS, '_').trim().replace(/^\.+|\.+$/g, '');
    if (!text) return 'image';

    const dot = text.lastIndexOf('.');
    if (dot <= 0) return text.slice(0, NAME_MAX_LENGTH);
    const stem = (text.slice(0, dot) || 'image').slice(0, NAME_MAX_LENGTH);
    return `${stem}.${text.slice(dot + 1).toLowerCase()}`;
}

/** 从 key 反推原始文件名：`<uuid>_<原名>` → `<原名>`。 */
export function originalNameFromPath(key) {
    if (!key) return '';
    const name = String(key).split(/[\\/]/).pop();
    const dot = name.lastIndexOf('.');
    const stem = dot > 0 ? name.slice(0, dot) : name;
    const suffix = dot > 0 ? name.slice(dot + 1) : '';
    const separator = stem.indexOf('_');
    if (separator > 0 && separator < stem.length - 1) {
        const rest = stem.slice(separator + 1);
        return suffix ? `${rest}.${suffix}` : rest;
    }
    return name;
}

/** 生成入库用的 key（uuid + 清洗后的原名）。 */
export function makeImageKey(filename, uuid) {
    const original = sanitizeOriginalName(filename);
    const extension = (original.match(/\.[^.]+$/) ?? [''])[0]
        || (String(filename ?? '').match(/\.[^.]+$/) ?? ['.jpg'])[0].toLowerCase();
    const stem = original.replace(/\.[^.]+$/, '') || 'image';
    const value = (uuid ?? defaultUuid()).replace(/-/g, '');
    return `${(value + '_' + stem).slice(0, NAME_MAX_LENGTH + 40)}${extension}`;
}

function defaultUuid() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    return 'xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
        const random = Math.floor(Math.random() * 16);
        return (char === 'x' ? random : (random & 0x3) | 0x8).toString(16);
    });
}

/* --------------------------------------------------------------------------
 * 校验（对应 images.validate_upload）
 * ------------------------------------------------------------------------ */

/** 校验一个 File/Blob，返回错误信息（null = 通过）。 */
export function validateFile(file, options = {}) {
    const maxBytes = options.maxBytes ?? CONFIG.MAX_IMAGE_BYTES;
    const extensions = options.extensions ?? CONFIG.ALLOWED_IMAGE_EXTENSIONS;
    if (!file || !clean(file.name)) return '请上传隐患图片（拍照或从相册选择）';

    const match = /(\.[^.]+)$/.exec(file.name);
    const extension = match ? match[1].toLowerCase() : '';
    if (!extensions.includes(extension)) {
        return `图片格式只支持 ${extensions.join('、')}`;
    }
    if (!file.size) return '图片文件是空的，请重新选择';
    if (file.size > maxBytes) {
        return `图片不能超过 ${Math.floor(maxBytes / (1024 * 1024))} MB`
            + `（当前 ${(file.size / (1024 * 1024)).toFixed(1)} MB）`;
    }
    return null;
}

/* --------------------------------------------------------------------------
 * 导入（校验 → 配额 → 现算缩略图 → 与报告同一事务写入）
 * ------------------------------------------------------------------------ */

/**
 * 处理一张上传的图片，返回**可入库的图片记录**（尚未写库）。
 *
 * 顺序有讲究：图片解码与缩略图生成必须在**开事务之前**做完 ——
 * IndexedDB 的事务在"没有挂起请求 + 微任务清空"时自动提交，在事务里 await
 * canvas 编码必然抛 `TransactionInactiveError`（见 `db.js` 的纪律第 3 条）。
 *
 * @returns {Promise<object>} `{id, blob, thumb, width, height, bytes, mime, created_at}`
 */
export async function prepareUpload(db, file, options = {}) {
    const error = validateFile(file, options);
    if (error) throw new ImageError(error);

    if (options.checkQuota !== false) {
        const quota = await checkUploadQuota(
            Math.min(file.size || 0, options.maxBytes ?? DEFAULT_MAX_IMAGE_BYTES),
            options.quotaOptions);
        if (!quota.allowed) throw new QuotaError(quota.message, quota.status);
    }

    const prepared = await prepareImage(file, options.pipeline);
    return {
        id: makeImageKey(file.name, options.uuid),
        ...prepared,
        created_at: options.created_at ?? stamp(),
    };
}

/** 导入一张图片并落库。配 `defects.create(db, data, record)` 一起用（同一事务）。 */
export async function importImage(db, file, options = {}) {
    const record = await prepareUpload(db, file, options);
    await put(db, record);
    return record;
}

/** 列出全部图片 key（"重建缩略图"与"导出备份"都要遍历）。 */
export async function allKeys(db) {
    const rows = await all(db);
    return rows.map((row) => row.id);
}

/** 全部图片记录（按 key 升序；备份包要连原图一起导出）。 */
export function all(db) {
    return db.read([STORE.images], (ctx) => ctx.getAll(STORE.images));
}

/**
 * 批量重建缩略图（改了缩略图参数后用，对应设计文档 3.4 的"代价"一栏）。
 *
 * 缩略图是**可从原图重新生成**的纯派生值，所以重建永远安全：不动原图、不动业务字段。
 *
 * @returns {Promise<{total: number, rebuilt: number, failed: number}>}
 */
export async function rebuildThumbnails(db, options = {}) {
    const rows = await all(db);
    const updates = [];
    let failed = 0;
    for (const row of rows) {
        try {
            const thumb = await rebuildThumbnail(row.blob, options.pipeline);
            updates.push({ ...row, thumb });
        } catch {
            failed += 1;                       // 一张坏图不该让整批重建失败
        }
    }
    if (updates.length) {
        await db.write([STORE.images], async (ctx) => {
            for (const row of updates) await ctx.put(STORE.images, row);
        });
    }
    return { total: rows.length, rebuilt: updates.length, failed };
}

/* --------------------------------------------------------------------------
 * 读写
 * ------------------------------------------------------------------------ */

/** 写入一张图片（原图 + 缩略图 + 尺寸）。id 用 makeImageKey()。 */
export function put(db, record) {
    return db.write([STORE.images], (ctx) => ctx.put(STORE.images, record));
}

export function get(db, imageKey) {
    if (!imageKey) return Promise.resolve(null);
    return db.read([STORE.images], (ctx) => ctx.get(STORE.images, imageKey));
}

export async function exists(db, imageKey) {
    return (await get(db, imageKey)) !== null;
}

export function remove(db, imageKey) {
    if (!imageKey) return Promise.resolve();
    return db.write([STORE.images], (ctx) => ctx.delete(STORE.images, imageKey));
}

/** 附件视图用的图片记录 → 附页渲染数据（对齐 Python 的 attachment_views）。 */
export function attachmentView(defect, image) {
    return {
        defect,
        original_name: originalNameFromPath(defect.image_path),
        image,
        missing: Boolean(defect.image_path) && !image,
        compressed: false,        // 导出时现压；压缩与否由导出流程写入
    };
}
