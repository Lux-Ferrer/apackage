/* 模块图自检：**这个前端真的能在浏览器里加载起来吗？**
 *
 * 为什么值得单独测
 * ----------------
 * 纯静态、无打包器的代价是"路径写错 = 白屏"，而白屏没有任何测试会告诉你 ——
 * 单元测试直接 import 源文件，绕过了浏览器真正走的解析路径：
 *   1. `index.html` 里的 `<link>` / `<script src>` 路径；
 *   2. `import map` 是否覆盖了源码里用到的**每一个裸模块名**（docx / jszip）；
 *   3. 每条相对 import 的目标文件是否真的存在（大小写敏感：Windows 上不报错、Linux 上 404）。
 *
 * 这个文件就是在没有浏览器的情况下把这三件事查一遍。它挡住的正是"改完能跑测试、
 * 打开网页却白屏"这一类交付事故。
 */
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const WEB_DIR = fileURLToPath(new URL('..', import.meta.url));
const INDEX_HTML = resolve(WEB_DIR, 'index.html');

/** 递归列出目录下的全部文件。 */
function walk(directory) {
    const found = [];
    for (const entry of readdirSync(directory)) {
        const full = resolve(directory, entry);
        if (statSync(full).isDirectory()) found.push(...walk(full));
        else found.push(full);
    }
    return found;
}

/** `index.html` 里声明的导入映射。 */
function importMap() {
    const html = readFileSync(INDEX_HTML, 'utf8');
    const match = /<script type="importmap">([\s\S]*?)<\/script>/.exec(html);
    assert.ok(match, 'index.html 必须有 import map（没有它，浏览器解析不了裸模块名 docx / jszip）');
    return JSON.parse(match[1]).imports ?? {};
}

/** 一条 import 语句 → 模块说明符。覆盖 `import x from 'y'` / `import 'y'` / `export … from 'y'`。 */
function specifiersOf(source) {
    const found = [];
    const patterns = [
        /^\s*import\s+[^'"]*from\s*['"]([^'"]+)['"]/gm,
        /^\s*import\s*['"]([^'"]+)['"]/gm,
        /^\s*export\s+[^'"]*from\s*['"]([^'"]+)['"]/gm,
        /import\(\s*['"]([^'"]+)['"]\s*\)/g,          // 动态 import（导出/备份是懒加载的）
    ];
    for (const pattern of patterns) {
        for (const match of source.matchAll(pattern)) found.push(match[1]);
    }
    return found;
}

test('index.html 引用的每个本地资源都存在（写错路径 = 白屏）', () => {
    const html = readFileSync(INDEX_HTML, 'utf8');
    const refs = [
        ...html.matchAll(/<link[^>]+href="([^"]+)"/g),
        ...html.matchAll(/<script[^>]+src="([^"]+)"/g),
    ].map((match) => match[1]).filter((href) => !href.startsWith('http'));

    assert.ok(refs.length >= 3, '至少应有 2 个样式表 + 1 个入口脚本');
    for (const ref of refs) {
        const target = resolve(WEB_DIR, ref.replace(/^\.\//, ''));
        assert.ok(existsSync(target), `index.html 引用了不存在的文件：${ref}`);
    }
});

test('源码里的每条相对 import 都能解析到真实文件', () => {
    const files = walk(resolve(WEB_DIR, 'app')).filter((path) => path.endsWith('.js'));
    assert.ok(files.length >= 15, `web/app 下应有足够多的模块（实际 ${files.length}）`);

    const missing = [];
    for (const file of files) {
        for (const specifier of specifiersOf(readFileSync(file, 'utf8'))) {
            if (!specifier.startsWith('.')) continue;                 // 裸名由 import map 负责
            const target = resolve(dirname(file), specifier);
            if (!existsSync(target)) {
                missing.push(`${file.slice(WEB_DIR.length)} → ${specifier}`);
            }
        }
    }
    assert.deepEqual(missing, [], '存在解析不到的相对 import');
});

test('import map 覆盖了源码里用到的全部裸模块名', () => {
    const mapping = importMap();
    const files = walk(resolve(WEB_DIR, 'app')).filter((path) => path.endsWith('.js'));

    const bare = new Set();
    for (const file of files) {
        for (const specifier of specifiersOf(readFileSync(file, 'utf8'))) {
            if (specifier.startsWith('.') || specifier.startsWith('/')) continue;
            bare.add(specifier.split('/')[0]);                        // `docx` / `jszip`
        }
    }

    for (const name of bare) {
        assert.ok(mapping[name], `import map 缺少裸模块名「${name}」的映射`);
        const target = resolve(WEB_DIR, mapping[name].replace(/^\.\//, ''));
        assert.ok(existsSync(target), `import map 把「${name}」指向了不存在的文件：${mapping[name]}`);
    }
    // 反向：映射里不该有指向不存在文件的条目
    for (const [name, href] of Object.entries(mapping)) {
        assert.ok(existsSync(resolve(WEB_DIR, href.replace(/^\.\//, ''))),
            `import map 的「${name}」指向不存在的文件：${href}`);
    }
});

test('vendored 库带版本标记（升级依赖后能看出该重新 vendor）', () => {
    for (const name of ['docx.mjs', 'jszip.min.js']) {
        const path = resolve(WEB_DIR, 'vendor', name);
        assert.ok(existsSync(path), `缺少 vendored 文件：vendor/${name}`);
        const head = readFileSync(path, 'utf8').slice(0, 400);
        assert.match(head, /vendored：由 tools\/export_web_assets\.py/,
            `vendor/${name} 缺少由生成器写入的文件头`);
        assert.match(head, /（v\d+\.\d+\.\d+）/, `vendor/${name} 的文件头里应有来源版本号`);
    }
});

test('入口 main.js 只在自己被显式要求时才自动启动（否则测试 import 会误触发）', () => {
    const source = readFileSync(resolve(WEB_DIR, 'app', 'main.js'), 'utf8');
    assert.match(source, /if \(globalThis\.__APP_BOOT__\)/,
        'main.js 的自动启动必须挂在显式标记上');
    const html = readFileSync(INDEX_HTML, 'utf8');
    assert.match(html, /__APP_BOOT__ = true/, 'index.html 必须设置这个标记');
});
