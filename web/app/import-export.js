/* 备份与恢复：整个 IndexedDB → 一个 zip → 再导回来。
 *
 * 为什么这一版**必须**有它
 * ------------------------
 * 现场工具的用法是"手机上记录、回办公室导出"，而 iOS Safari 对**未获持久化授权**的站点
 * 有约 7 天的闲置清理策略 —— 数据是可能凭空消失的。所以"导出一份备份"不是加分项，
 * 而是这一版的基本可用性要求（`M5-真机验证checklist.md` A 组）。
 *
 * 备份格式（`.zip`）
 * -----------------
 *   backup.json          全部结构化数据（5 个 store），不含图片二进制
 *   images/<图片 key>     原图字节，文件名就是 key（沿用"从 key 反推原始文件名"）
 *
 * 两个刻意的决定：
 *  1. **不备份缩略图**：它是**可从原图重新生成的派生值**（设计文档 3.4 的有意偏离只针对
 *     "落不落库"，不是"要不要进备份"）。导入时现重建 → 备份体积小一半以上，
 *     而且改了缩略图参数后导入的自然就是新参数的结果。
 *  2. **导入 = 覆盖**：备份是完整快照，没有"合并"的语义基础（跨快照的 id 冲突无解）。
 *     所以 UI 必须先 `inspectBackup()` 把"将覆盖什么"讲清楚，再让用户确认。
 */

import JSZip from 'jszip';

import { STORE } from './db.js';
import { rebuildThumbnail } from './image-pipeline.js';
import { stamp } from './repo/defects.js';

export const BACKUP_FORMAT = 'curtain-wall-inspection-backup';
export const BACKUP_VERSION = 1;
/** 备份里的图片目录（文件名 = images store 的主键 = `<uuid>_<原名>.<ext>`）。 */
export const IMAGE_PREFIX = 'images/';

const ALL_STORES = [STORE.projects, STORE.records, STORE.readings, STORE.defects, STORE.images];

/* --------------------------------------------------------------------------
 * 导出
 * ------------------------------------------------------------------------ */

/** 读出全部数据（图片记录会把 blob 单独摘出来，避免在 JSON 里出现二进制）。 */
async function readAll(db, includeThumb = false) {
    return db.read(ALL_STORES, async (ctx) => {
        const [projects, records, readings, defects, images] = await Promise.all([
            ctx.getAll(STORE.projects), ctx.getAll(STORE.records), ctx.getAll(STORE.readings),
            ctx.getAll(STORE.defects), ctx.getAll(STORE.images),
        ]);
        return { projects, records, readings, defects, images, includeThumb };
    });
}

/** 一份备份的**结构**（不含图片二进制）—— 导出与导入两侧共用同一套字段名。 */
function toBackupData(snapshot, now = new Date()) {
    return {
        format: BACKUP_FORMAT,
        version: BACKUP_VERSION,
        exported_at: stamp(now),
        counts: {
            projects: snapshot.projects.length,
            records: snapshot.records.length,
            readings: snapshot.readings.length,
            defects: snapshot.defects.length,
            images: snapshot.images.length,
        },
        tables: {
            projects: snapshot.projects,
            records: snapshot.records,
            readings: snapshot.readings,
            defects: snapshot.defects,
            // 图片只留元数据：blob 走 zip 里的独立文件，thumb 刻意不带（见模块 docstring）
            images: snapshot.images.map(({ blob, thumb, ...meta }) => meta),
        },
    };
}

/** 备份文件名：`幕墙检测备份_20260925_1030.zip`。 */
export function backupFilename(now = new Date()) {
    const pad = (value) => String(value).padStart(2, '0');
    const date = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
    const time = `${pad(now.getHours())}${pad(now.getMinutes())}`;
    return `幕墙检测备份_${date}_${time}.zip`;
}

/**
 * 生成备份 zip。
 *
 * @returns {Promise<{blob: Blob, filename: string, counts: object, missingImages: string[]}>}
 *   `missingImages`：记录里登记了图片但原图已经不在的那些 key（备份会跳过它们，
 *   但要**显式告诉用户**，而不是安静地少几张图）
 */
export async function exportBackup(db, options = {}) {
    const now = options.now ?? new Date();
    const snapshot = await readAll(db);
    const data = toBackupData(snapshot, now);

    const zip = new JSZip();
    zip.file('backup.json', `${JSON.stringify(data, null, 2)}\n`);

    const folder = zip.folder('images');
    const missingImages = [];
    for (const record of snapshot.images) {
        if (!record.blob) {
            missingImages.push(record.id);
            continue;
        }
        folder.file(record.id, record.blob);
    }
    if (missingImages.length) {
        data.counts.missing_images = missingImages.length;
        zip.file('backup.json', `${JSON.stringify(data, null, 2)}\n`);
    }

    const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' });
    return { blob, filename: backupFilename(now), counts: data.counts, missingImages };
}

/* --------------------------------------------------------------------------
 * 导入
 * ------------------------------------------------------------------------ */

/** 备份文件不合法（不是 zip / 缺 backup.json / 格式或版本不认）。 */
export class BackupError extends Error {
    constructor(message) {
        super(message);
        this.name = 'BackupError';
    }
}

/**
 * 只看不写：把备份"将覆盖什么"讲清楚。
 *
 * 与 `exportBackup` 对称，导入前必须先调它 —— 破坏性操作前给用户看具体数字，
 * 这是 M4「删除确认文案写明影响面」的同一条纪律。
 */
export async function inspectBackup(file) {
    const zip = await loadZip(file);
    const data = await readBackupJson(zip);

    /* ⚠️ `zip.files` 是**对象**（`{ 路径: ZipObject }`），不是数组。
     * 真机 bug：这里曾经写成 `zip.files.filter(...)` → `TypeError: zip.files.filter is not a
     * function`，而 UI 在导入前**必须先调本函数**，于是「导入备份」这条唯一的救命通道
     * 100% 失败（提示：导入失败：zip.files.filter is not a function）。
     * 之所以没被测试抓到：当时**没有任何测试覆盖备份导入**（现在有了：
     * `web/tests/import_export.test.mjs` + `web/e2e/07-data-safety.spec.mjs`）。 */
    const listed = new Set(
        Object.entries(zip.files)
            .filter(([name, entry]) => name.startsWith(IMAGE_PREFIX) && !entry.dir)
            .map(([name]) => name.slice(IMAGE_PREFIX.length)),
    );

    const registered = data.tables.images.map((row) => row.id);
    return {
        exportedAt: data.exported_at,
        counts: data.counts,
        imageFiles: listed.size,
        missingImages: registered.filter((key) => !listed.has(key)),
        orphanImages: [...listed].filter((key) => !registered.includes(key)),
    };
}

async function loadZip(file) {
    try {
        // File/Blob 与 Uint8Array/ArrayBuffer 都接受
        return await JSZip.loadAsync(file);
    } catch {
        throw new BackupError('这不是一个有效的 zip 备份文件');
    }
}

async function readBackupJson(zip) {
    const entry = zip.file('backup.json');
    if (!entry) throw new BackupError('备份里缺少 backup.json');

    let data;
    try {
        data = JSON.parse(await entry.async('string'));
    } catch {
        throw new BackupError('backup.json 不是有效的 JSON（文件可能已损坏）');
    }
    if (data?.format !== BACKUP_FORMAT) {
        throw new BackupError(`这不是本工具的备份文件（format=${data?.format ?? '缺失'}）`);
    }
    if (Number(data.version) > BACKUP_VERSION) {
        throw new BackupError(
            `备份版本 ${data.version} 比当前程序（${BACKUP_VERSION}）新，请先升级工具`);
    }
    if (!data.tables || !Array.isArray(data.tables.projects)) {
        throw new BackupError('backup.json 结构不完整（缺少 tables.projects）');
    }
    return data;
}

/**
 * 导入备份：**覆盖**当前全部数据。
 *
 * 顺序（都是同一个事务，任一步失败整体回滚）：
 *   1. 清空 5 个 store；
 *   2. 按 backup.json 写入结构化数据（图片只写元数据）；
 *   3. 把 zip 里的原图字节配上缩略图写进 `images`。
 *
 * 第 3 步的缩略图是**现重建**的（备份里本来就没有），所以需要浏览器能解码图片；
 * 单张坏图只丢它自己（`failed` 计数），不影响其它数据 —— 与"图片压缩失败不能让整份报告导不出来"
 * 是同一条纪律。
 *
 * ⚠️ 重建缩略图必须在**开事务之前**做完：IndexedDB 的事务在 await 非 IDB Promise 时
 * 会自动提交（见 `db.js` 纪律第 3 条）。所以这里是"先全部算好、再一次性写"。
 */
export async function importBackup(db, file, options = {}) {
    const zip = await loadZip(file);
    const data = await readBackupJson(zip);

    // ① 先把图片全部读出来并重建缩略图（事务之外）
    const images = [];
    let failed = 0;
    for (const meta of data.tables.images) {
        const entry = zip.file(IMAGE_PREFIX + meta.id);
        if (!entry) {
            failed += 1;
            continue;                       // 备份里就没有这张图 → 记录保留、图片缺失（走降级）
        }
        const blob = await entry.async('blob');
        const mime = blob.type || meta.mime || 'image/jpeg';
        const typed = blob.type ? blob : blob.slice(0, blob.size, mime);
        let thumb = null;
        try {
            thumb = await rebuildThumbnail(typed, options.pipeline);
        } catch {
            thumb = null;                   // 缩略图重建失败仍然保留原图
        }
        images.push({ ...meta, blob: typed, thumb });
    }

    // ② 再一次性覆盖写库
    const written = await db.write(ALL_STORES, async (ctx) => {
        for (const store of ALL_STORES) await ctx.clear(store);
        for (const row of data.tables.projects) await ctx.put(STORE.projects, row);
        for (const row of data.tables.records) await ctx.put(STORE.records, row);
        for (const row of data.tables.readings) await ctx.put(STORE.readings, row);
        for (const row of data.tables.defects) await ctx.put(STORE.defects, row);
        for (const row of images) await ctx.put(STORE.images, row);
        return {
            projects: data.tables.projects.length,
            records: data.tables.records.length,
            readings: data.tables.readings.length,
            defects: data.tables.defects.length,
            images: images.length,
        };
    });

    return { imported: written, imageFailed: failed, exportedAt: data.exported_at };
}

/**
 * 重建全部缩略图（改了缩略图参数、或从没有缩略图的旧备份恢复之后用）。
 * 实现在 `repo/images.js`，这里只做转发，好让"数据管理"页只 import 一个模块。
 */
export { rebuildThumbnails } from './repo/images.js';
