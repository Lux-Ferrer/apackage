/* 存储配额与持久化：现场工具的**真实**风险，不是纸面条款。
 *
 * 为什么单独一个模块（而不是塞进 repo）：
 *   - 它要回答的是"还能不能继续存"，属于**容量策略**，跨记录/图片/备份共用；
 *   - 它依赖 `navigator.storage`（浏览器独占），必须能注入假实现才可测；
 *   - 它有一条**必须显式提示用户**的规则：iOS Safari 对未获持久化的站点有约 7 天
 *     闲置清理策略 —— 对"现场记录、回办公室导出"的用法，这是丢数据的风险。
 *
 * 对应设计文档 3.5。配额数字不写死在代码里，一律现问浏览器（各平台差异极大）。
 */

/** 用到多少比例开始警告（此时提示清理，但仍允许继续）。 */
export const QUOTA_WARN_RATIO = 0.85;
/** 用到多少比例直接拦下新上传。 */
export const QUOTA_BLOCK_RATIO = 0.95;
/** 单张原图上限（与 config.MAX_IMAGE_BYTES 一致，仅用于"这一张放得下吗"的估算）。 */
export const DEFAULT_MAX_IMAGE_BYTES = 20 * 1024 * 1024;

/** navigator.storage 拿不到时的兜底（老 Safari / 隐私模式）。 */
export function defaultStorage() {
    return globalThis.navigator?.storage ?? null;
}

/** 人类可读的字节数。 */
export function formatBytes(bytes) {
    const value = Number(bytes);
    if (!Number.isFinite(value) || value < 0) return '—';
    if (value < 1024) return `${Math.round(value)} B`;
    const units = ['KB', 'MB', 'GB', 'TB'];
    let size = value / 1024;
    let unit = 0;
    while (size >= 1024 && unit < units.length - 1) {
        size /= 1024;
        unit += 1;
    }
    return `${size >= 100 ? Math.round(size) : size.toFixed(1)} ${units[unit]}`;
}

/** 是否已获持久化授权；拿不到 API、或 API 返回空值 → null（= 未知，不要当成"已授权"）。 */
export async function isPersisted(storage = defaultStorage()) {
    if (!storage?.persisted) return null;
    try {
        const value = await storage.persisted();
        return value === null || value === undefined ? null : Boolean(value);
    } catch {
        return null;
    }
}

/**
 * 申请持久化。
 *
 * @returns {Promise<{supported: boolean, persisted: boolean|null, reason: string}>}
 *   `persisted === false` 时 UI **必须**提示"数据可能被系统清理，请及时导出备份"。
 */
export async function requestPersistence(storage = defaultStorage()) {
    if (!storage?.persist) {
        return {
            supported: false,
            persisted: null,
            reason: '当前浏览器不支持持久化存储申请（Safari 需要把页面「添加到主屏幕」后才会授予）',
        };
    }
    try {
        const persisted = Boolean(await storage.persist());
        return {
            supported: true,
            persisted,
            reason: persisted
                ? '已获持久化授权，系统不会自动清理本应用的数据'
                : '未获持久化授权：系统可能在闲置后清理数据，请定期导出备份',
        };
    } catch (error) {
        return { supported: true, persisted: null, reason: `申请持久化失败：${error?.message ?? error}` };
    }
}

/**
 * 读取配额状况。
 *
 * @returns {Promise<{supported: boolean, usage: number, quota: number, free: number,
 *                    ratio: number, persisted: boolean|null}>}
 *   `supported: false` 时各数字为 0，UI 应显示"当前浏览器不提供容量信息"。
 */
export async function quotaStatus(storage = defaultStorage()) {
    const persisted = await isPersisted(storage);
    if (!storage?.estimate) {
        return { supported: false, usage: 0, quota: 0, free: 0, ratio: 0, persisted };
    }
    try {
        const estimate = await storage.estimate() ?? {};
        const usage = Number(estimate.usage) || 0;
        const quota = Number(estimate.quota) || 0;
        return {
            supported: quota > 0,
            usage,
            quota,
            free: Math.max(0, quota - usage),
            ratio: quota > 0 ? usage / quota : 0,
            persisted,
        };
    } catch {
        return { supported: false, usage: 0, quota: 0, free: 0, ratio: 0, persisted };
    }
}

/**
 * 还能不能存下一张图（上传前调用，配合 `importImage` 使用）。
 *
 * 判定顺序：不支持估算 → 放行（不能因为问不到就不让用户记录）；
 * 剩余空间不够这一张 → 拦下；比例超阈值 → 拦下；超警告线 → 放行但带提示。
 *
 * @returns {Promise<{allowed: boolean, level: 'ok'|'warn'|'block'|'unknown', message: string}>}
 */
export async function checkUploadQuota(neededBytes = DEFAULT_MAX_IMAGE_BYTES, options = {}) {
    const warnRatio = options.warnRatio ?? QUOTA_WARN_RATIO;
    const blockRatio = options.blockRatio ?? QUOTA_BLOCK_RATIO;
    const status = await quotaStatus(options.storage ?? defaultStorage());
    const needed = Number(neededBytes) || 0;

    if (!status.supported) {
        return {
            allowed: true,
            level: 'unknown',
            message: '当前浏览器不提供容量信息，无法预估剩余空间',
            status,
        };
    }
    if (status.free < needed) {
        return {
            allowed: false,
            level: 'block',
            message: `剩余空间不足（可用 ${formatBytes(status.free)}，这张最多 ${formatBytes(needed)}）。`
                + '请先导出备份并清理历史报告。',
            status,
        };
    }
    if (status.ratio >= blockRatio) {
        return {
            allowed: false,
            level: 'block',
            message: `存储已用 ${(status.ratio * 100).toFixed(1)}%（${formatBytes(status.usage)}`
                + ` / ${formatBytes(status.quota)}），请先导出备份并清理历史报告。`,
            status,
        };
    }
    if (status.ratio >= warnRatio) {
        return {
            allowed: true,
            level: 'warn',
            message: `存储已用 ${(status.ratio * 100).toFixed(1)}%，建议尽快导出备份。`,
            status,
        };
    }
    return {
        allowed: true,
        level: 'ok',
        message: `已用 ${formatBytes(status.usage)} / ${formatBytes(status.quota)}`,
        status,
    };
}

/**
 * 当前实际缓存着的应用壳版本（从 Cache Storage 的 key 里读）。
 *
 * 为什么不直接 import `assets/shell.js`：那份清单是 **Service Worker 的内部物**，
 * 内容由"全部被缓存文件"算出来 —— 它要是也被 app import，它自己就得进清单，
 * 于是"它的内容取决于包含它的集合"成了循环。所以改为在运行时读缓存名，
 * 好处是显示的是**真正装着的那一版**，而不只是"构建时那一版"。
 *
 * @returns {Promise<string|null>} 没有离线缓存时返回 null
 */
export async function shellVersion({ caches: cacheStorage = globalThis.caches } = {}) {
    const prefix = 'curtain-wall-shell-';
    if (!cacheStorage?.keys) return null;
    try {
        const keys = await cacheStorage.keys();
        const mine = keys.filter((name) => name.startsWith(prefix)).sort();
        return mine.length ? mine[mine.length - 1].slice(prefix.length) : null;
    } catch {
        return null;
    }
}


/** 「我的 → 数据管理」那一行文案（含未获持久化时的丢数据警告）。 */
export async function describeStorage(options = {}) {
    const status = await quotaStatus(options.storage ?? defaultStorage());
    const lines = [];
    if (!status.supported) {
        lines.push('当前浏览器不提供容量信息');
    } else {
        lines.push(`已存储 ${formatBytes(status.usage)} / ${formatBytes(status.quota)}`
            + `（${(status.ratio * 100).toFixed(1)}%）`);
    }
    if (status.persisted === false) {
        lines.push('⚠️ 未获持久化授权：系统可能在闲置后清理数据（iOS Safari 约 7 天），请定期导出备份');
    } else if (status.persisted === true) {
        lines.push('已获持久化授权，系统不会自动清理数据');
    }
    return { status, lines };
}
