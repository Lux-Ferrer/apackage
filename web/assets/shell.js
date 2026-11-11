/* 构建产物，请勿手改。
 *
 * 用途：离线预缓存清单 + 内容指纹版本号（Service Worker 据此判断要不要更新）。
 * 版本号只取决于被缓存文件的内容 —— 改了任何一个文件，SW 都会装新版本并清掉旧缓存。
 */

export const SHELL_VERSION = "9ac9be170ebb";

export const SHELL_ASSETS = Object.freeze([
    "app/clauses.js",
    "app/config.js",
    "app/db.js",
    "app/export.js",
    "app/image-pipeline.js",
    "app/import-export.js",
    "app/main.js",
    "app/product.js",
    "app/repo/defects.js",
    "app/repo/images.js",
    "app/repo/measurements.js",
    "app/repo/profile.js",
    "app/repo/projects.js",
    "app/report/attachments.js",
    "app/report/engine.js",
    "app/report/fingerprint.js",
    "app/report/image-size.js",
    "app/report/postprocess.js",
    "app/report/spec.js",
    "app/router.js",
    "app/storage.js",
    "app/thickness.js",
    "app/ui/dialog.js",
    "app/ui/dom.js",
    "app/ui/form.js",
    "app/ui/objecturl.js",
    "app/ui/record-form.js",
    "app/views/layout.js",
    "app/views/me.js",
    "app/views/profile.js",
    "app/views/projects.js",
    "app/views/records.js",
    "app/views/reports.js",
    "assets/report_base.docx",
    "icons/icon-192.png",
    "icons/icon-512-maskable.png",
    "icons/icon-512.png",
    "index.html",
    "manifest.webmanifest",
    "styles/app.css",
    "styles/m5.css",
    "vendor/docx.mjs",
    "vendor/jszip.js",
    "vendor/jszip.min.js",
]);

export default SHELL_ASSETS;
