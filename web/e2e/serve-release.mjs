#!/usr/bin/env node
/* 把**交付包本身**跑起来，给 Playwright 用。
 *
 * 三步：
 *   1. 找 `dist/mcc-inspection-tool-v*.zip`（多个版本取文件名排序最后一个）；
 *   2. 解到 `_work/e2e/site/`（每次先清空，避免上一轮的残留文件掩盖"包漏了文件"）；
 *   3. 用**包里自带的那份** `serve_static.py` 起服务。
 *
 * 为什么第 3 步不用 Playwright 自带的静态服务：这一层的价值就在于"客户拿到的东西能跑"。
 * 包的服务器要是 MIME 配错了（`.mjs` → text/plain 就是白屏），测试必须能发现它。
 *
 * 用法：`node web/e2e/serve-release.mjs --port 8123`（由 playwright.config.mjs 的 webServer 调用）
 */
import { spawn } from 'node:child_process';
import { mkdirSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import JSZip from 'jszip';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const DIST = join(ROOT, 'dist');
const SITE_ROOT = join(ROOT, '_work', 'e2e', 'site');

function argValue(name, fallback) {
    const index = process.argv.indexOf(`--${name}`);
    return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function latestZip() {
    const names = readdirSync(DIST).filter((name) => /^mcc-inspection-tool-v[\d.]+\.zip$/.test(name));
    if (!names.length) {
        throw new Error(`dist/ 里没有交付包：${DIST}\n先跑 python tools/make_release_zip.py`);
    }
    return join(DIST, names.sort().at(-1));
}

async function extract(zipPath) {
    rmSync(SITE_ROOT, { recursive: true, force: true });
    mkdirSync(SITE_ROOT, { recursive: true });

    const archive = await JSZip.loadAsync(readFileSync(zipPath));
    let count = 0;
    for (const [entryName, entry] of Object.entries(archive.files)) {
        if (entry.dir) continue;
        const target = join(SITE_ROOT, entryName);
        mkdirSync(dirname(target), { recursive: true });
        const { writeFileSync } = await import('node:fs');
        writeFileSync(target, await entry.async('nodebuffer'));
        count += 1;
    }
    return count;
}

async function main() {
    const port = Number(argValue('port', '8123'));
    const zipPath = latestZip();
    const files = await extract(zipPath);
    const site = join(SITE_ROOT, 'mcc-inspection-tool');
    console.log(`[e2e] 交付包：${zipPath.replace(`${ROOT}\\`, '')}（${files} 个文件已解压）`);

    const python = process.env.PYTHON ?? 'python';
    const child = spawn(python, ['serve_static.py', '--port', String(port), '--dir', '.'],
        { cwd: site, stdio: 'inherit' });

    const stop = (signal) => {
        try { child.kill(signal); } catch { /* 已经退出了 */ }
    };
    for (const signal of ['SIGINT', 'SIGTERM', 'SIGBREAK', 'SIGHUP']) {
        process.on(signal, () => { stop('SIGTERM'); process.exit(0); });
    }
    child.on('exit', (code) => process.exit(code ?? 0));
}

main().catch((error) => {
    console.error(`[e2e] 启动失败：${error.message}`);
    process.exit(1);
});
