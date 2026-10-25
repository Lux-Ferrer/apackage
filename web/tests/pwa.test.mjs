/* PWA（离线可用）的自检。
 *
 * 这一层最该防的不是"manifest 写错了"（那种一眼能看出来），而是：
 *   **离线清单漏了一个文件。**
 * 症状是：在线一切正常，一断网就白屏 —— 而且现场几乎无法复现、日志里什么都没有。
 * 所以这里不只看"清单里的文件是否存在"，还**反着查**：
 * 源码里 import 到的每一个模块、index.html 引用的每一个资源，都必须在清单里。
 *
 * 另外守两条已经踩过的坑：
 *  - 清单必须**版本化**（内容指纹），否则改了文件而 SW 不更新，用户会一直看到旧代码；
 *  - `sw.js` 不能自动 `skipWaiting()`，否则正在填表的页面会在脚下被换掉。
 */
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const WEB_DIR = fileURLToPath(new URL('..', import.meta.url));
const READ = (relative) => readFileSync(resolve(WEB_DIR, relative), 'utf8');
const EXISTS = (relative) => existsSync(resolve(WEB_DIR, relative));

const shell = await import('../assets/shell.js');
const { SHELL_ASSETS, SHELL_VERSION } = shell;

/* --------------------------------------------------------------------------
 * 清单本身
 * ------------------------------------------------------------------------ */

test('离线清单：每个文件都存在、路径是相对的正斜杠、且不含测试与生成器自身', () => {
    assert.ok(SHELL_ASSETS.length >= 20, `清单太短（${SHELL_ASSETS.length} 项），像是漏扫了`);
    for (const relative of SHELL_ASSETS) {
        assert.ok(!relative.startsWith('/') && !relative.includes('\\'),
            `清单里应写相对路径且用正斜杠：${relative}`);
        assert.ok(EXISTS(relative), `清单里有不存在的文件：${relative}`);
        assert.ok(!relative.startsWith('tests/'), `测试文件不该进离线缓存：${relative}`);
        assert.ok(relative !== 'sw.js', 'Service Worker 自己不该进预缓存清单');
        assert.ok(relative !== 'assets/shell.js', '清单文件自己不该进预缓存清单');
    }
    // 去重（重复项会让 cache.addAll 报错）
    assert.equal(new Set(SHELL_ASSETS).size, SHELL_ASSETS.length);
});

test('离线清单：入口、样式、vendor 库、底座模板、图标都必须在里面', () => {
    for (const required of [
        'index.html', 'manifest.webmanifest',
        'styles/app.css', 'styles/m5.css',
        'app/main.js', 'app/db.js', 'app/router.js', 'app/report/engine.js',
        'app/report/fingerprint.js', 'app/report/image-size.js',
        'vendor/docx.mjs', 'vendor/jszip.js', 'vendor/jszip.min.js',
        'assets/report_base.docx',
        'icons/icon-192.png', 'icons/icon-512.png', 'icons/icon-512-maskable.png',
    ]) {
        assert.ok(SHELL_ASSETS.includes(required), `离线清单缺少：${required}`);
    }
});

/* --------------------------------------------------------------------------
 * 反向核对：源码引用的东西一个都不能漏
 * ------------------------------------------------------------------------ */

/** 取出一个 JS 文件里的模块说明符（静态 import / 动态 import / export from）。 */
function specifiersOf(source) {
    const found = [];
    for (const pattern of [
        /^\s*import\s+[^'"]*from\s*['"]([^'"]+)['"]/gm,
        /^\s*import\s*['"]([^'"]+)['"]/gm,
        /^\s*export\s+[^'"]*from\s*['"]([^'"]+)['"]/gm,
        /import\(\s*['"]([^'"]+)['"]\s*\)/g,
    ]) {
        for (const match of source.matchAll(pattern)) found.push(match[1]);
    }
    return found;
}

function walk(directory) {
    const found = [];
    for (const entry of readdirSync(directory)) {
        const full = resolve(directory, entry);
        if (statSync(full).isDirectory()) found.push(...walk(full));
        else found.push(full);
    }
    return found;
}

test('反过来查：app/ 里 import 到的每个模块（含动态 import）都在离线清单里', () => {
    const files = walk(resolve(WEB_DIR, 'app')).filter((path) => path.endsWith('.js'));
    const missing = [];
    for (const file of files) {
        for (const specifier of specifiersOf(readFileSync(file, 'utf8'))) {
            if (!specifier.startsWith('.')) continue;               // 裸名走 vendor（另测）
            const target = resolve(dirname(file), specifier);
            const relative = target.slice(WEB_DIR.length).replace(/\\/g, '/');
            if (!EXISTS(relative)) continue;                        // 路径错由 module_graph 测
            if (!SHELL_ASSETS.includes(relative)) missing.push(relative);
        }
    }
    assert.deepEqual(missing, [], '这些模块被源码引用了，但不在离线清单里（断网会白屏）');
});

test('反过来查：index.html 引用到的每个本地资源都在离线清单里', () => {
    const html = READ('index.html');
    const refs = [
        ...html.matchAll(/<link[^>]+href="([^"]+)"/g),
        ...html.matchAll(/<script[^>]+src="([^"]+)"/g),
    ].map((match) => match[1]).filter((href) => !href.startsWith('http'));

    for (const href of refs) {
        const relative = href.replace(/^\.\//, '');
        assert.ok(SHELL_ASSETS.includes(relative), `index.html 引用了 ${relative}，但不在离线清单里`);
    }
});

test('反过来查：vendor 目录里的每个文件都在清单里（第三方库缺一个就是白屏）', () => {
    for (const name of readdirSync(resolve(WEB_DIR, 'vendor'))) {
        assert.ok(SHELL_ASSETS.includes(`vendor/${name}`), `vendor/${name} 不在离线清单里`);
    }
});

/* --------------------------------------------------------------------------
 * 版本化与更新策略
 * ------------------------------------------------------------------------ */

test('清单带内容指纹版本号；改了任一被缓存的文件，版本必须变', () => {
    assert.match(SHELL_VERSION, /^[0-9a-f]{12}$/, '版本号应是 12 位十六进制内容指纹');

    // 复算一遍：把清单里每个文件的内容再哈希一次，必须与生成器给的一致。
    // 这条等价于"sw.js 的缓存 key 真的跟着文件内容走"——不然用户会一直看到旧代码。
    // （用 WebCrypto，浏览器与 Node 都有）
    return (async () => {
        const encoder = new TextEncoder();
        const chunks = [];
        for (const relative of SHELL_ASSETS) {
            chunks.push(encoder.encode(relative));
            chunks.push(new Uint8Array([0]));
            chunks.push(new Uint8Array(readFileSync(resolve(WEB_DIR, relative))));
            chunks.push(new Uint8Array([0]));
        }
        const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
        const buffer = new Uint8Array(total);
        let offset = 0;
        for (const chunk of chunks) {
            buffer.set(chunk, offset);
            offset += chunk.length;
        }
        const digest = await globalThis.crypto.subtle.digest('SHA-256', buffer);
        const hex = Array.from(new Uint8Array(digest))
            .map((byte) => byte.toString(16).padStart(2, '0')).join('');
        assert.equal(hex.slice(0, 12), SHELL_VERSION,
            '版本号与"清单内容 + 文件内容"的哈希对不上：要么生成器改了口径，要么清单被手改过');
    })();
});

test('Service Worker：用生成的清单做预缓存、清旧缓存、且**不自动 skipWaiting**', () => {
    const source = READ('sw.js');
    assert.match(source, /from '\.\/assets\/shell\.js'/, 'sw.js 必须用生成的清单（不许手写文件列表）');
    assert.match(source, /SHELL_VERSION/, '缓存名必须带版本号');
    assert.match(source, /caches\.delete/, 'activate 里必须清掉旧缓存');
    assert.match(source, /clients\.claim\(\)/, 'activate 里应接管页面');

    // 关键：install 里不能**调用** skipWaiting（只允许在 message 里按页面要求调用）。
    // 两处细节，都是为了不误报：
    //   · 用"两个监听的索引之间"截取代码块（正则很容容易一路吞到文件末尾）；
    //   · 先**去掉注释**再查 —— sw.js 里正好有一句"这里不调用 skipWaiting()"的注释，
    //     直接搜字符串会把注释也算进去（这条测试第一版就是这么误报的）。
    const installAt = source.indexOf("addEventListener('install'");
    const activateAt = source.indexOf("addEventListener('activate'");
    assert.ok(installAt >= 0 && activateAt > installAt, 'sw.js 里应有 install 与 activate 两个监听');
    const stripComments = (code) => code
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/^\s*\/\/.*$/gm, '');
    const installBlock = stripComments(source.slice(installAt, activateAt));
    assert.ok(!/skipWaiting/.test(installBlock),
        'install 里不许 skipWaiting —— 新版本要等页面决定何时切，否则正在填的表单会被换掉');
    assert.match(source, /SKIP_WAITING/, '应支持页面通过消息触发 skipWaiting');
});

test('index.html 挂了 manifest 与图标；manifest 里的图标尺寸与真实 PNG 一致', () => {
    const html = READ('index.html');
    assert.match(html, /<link rel="manifest" href="\.\/manifest\.webmanifest">/);
    assert.match(html, /apple-touch-icon/);

    const manifest = JSON.parse(READ('manifest.webmanifest'));
    assert.equal(manifest.display, 'standalone');
    assert.equal(manifest.start_url, './index.html');
    assert.equal(manifest.scope, './');
    assert.equal(manifest.theme_color, '#1668dc');
    assert.ok(manifest.icons.length >= 3, '至少应有 192 / 512 / maskable 三个图标');

    // 图标的 sizes 声明必须与文件真实尺寸一致（写错了主屏幕图标会不显示）
    for (const icon of manifest.icons) {
        const relative = icon.src.replace(/^\.\//, '');
        assert.ok(EXISTS(relative), `manifest 指向了不存在的图标：${relative}`);
        assert.ok(SHELL_ASSETS.includes(relative), `图标 ${relative} 不在离线清单里`);
        const bytes = readFileSync(resolve(WEB_DIR, relative));
        const width = bytes.readUInt32BE(16);
        const height = bytes.readUInt32BE(20);
        assert.equal(`${width}x${height}`, icon.sizes, `${relative} 的真实尺寸与声明不符`);
    }
});
