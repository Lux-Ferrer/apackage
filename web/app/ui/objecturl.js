/* objectURL 的登记与释放。
 *
 * 为什么需要它（这一版特有的一个真实的内存坑）
 * --------------------------------------------
 * Flask 版的缩略图/大图是 `<img src="/reports/1/thumbnail">` —— 由浏览器按 URL 缓存，
 * 生命周期结束自动回收。M5 的图片在 IndexedDB 里，要显示就得先
 * `URL.createObjectURL(blob)`，而它**不会自己回收**：一个 20MB 原图的 objectURL
 * 会一直把那份数据钉在内存里，直到页面卸载。
 *
 * 表现是"翻十几条报告之后手机变卡/标签页被系统杀掉"，而且很难归因。
 * 所以这里把"这一屏建过的 URL"登记起来，**每次路由切换前统一释放**。
 *
 * ⚠️ 与 `export.js::downloadBlob` 的 URL 分开管：那个是给下载用的，
 * 提前释放会打断下载（它在自己的延时后释放）。
 */

const urls = new Set();

/** 建一个受管的 objectURL。 */
export function createObjectURL(blob) {
    const url = URL.createObjectURL(blob);
    urls.add(url);
    return url;
}

/** 释放所有受管 URL（路由切换前调用）。 */
export function releaseObjectURLs() {
    for (const url of urls) {
        try {
            URL.revokeObjectURL(url);
        } catch {
            /* 已经释放过就忽略 */
        }
    }
    const count = urls.size;
    urls.clear();
    return count;
}

/** 当前登记了几条（测试用）。 */
export function trackedCount() {
    return urls.size;
}
