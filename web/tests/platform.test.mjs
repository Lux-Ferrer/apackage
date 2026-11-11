/* 平台假设：`web/app` 里跑的代码必须**在浏览器里也能跑**。
 *
 * 真机 Bug（M5 验收，阻塞核心流程）：手机上点「附加 1 份并导出」/「仅导出检测报告」，
 * 页面顶部报 `导出失败：nodebuffer is not supported by this platform`。
 *
 * 根因：`report/engine.js` 用的是 `Packer.toBuffer(doc)` —— 它就是
 * `Packer.pack(file, "nodebuffer")`，而 JSZip 打包前会 `checkSupport("nodebuffer")`，
 * 该能力在**加载时**被算成常量 `support.nodebuffer = typeof Buffer !== "undefined"`。
 * Node 里有 Buffer，浏览器里没有。
 *
 * 为什么闸门和 200 多个测试全绿它还活着？因为它们**全跑在 Node/jsdom 上**，而 Node 恰好
 * 有 `Buffer`；`ui.test.mjs` 里那条"点导出 → 触发下载"的端到端用例走的也是 jsdom。
 * 测试环境比真实环境更宽容，于是把浏览器的缺失补上了 —— 这跟 M5 里"库抽象漏掉外壳"
 * 是同一类错误，只是这次漏掉的是**运行时能力**。
 *
 * 所以这一层不替引擎补环境，而是**把环境拿走**：删掉全局 `Buffer`，并且必须在
 * `import` 之前删（库在加载时就把能力算死了，加载后再删是自欺欺人 —— 第一次写这个
 * 测试就踩了：删晚了只会得到 `Buffer is not defined`，复现不了真机那条错）。
 */
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

// ① 顺序是这条测试的全部要点：先拆能力，再加载依赖
delete globalThis.Buffer;

const { renderDocx, Packer, buildProjectReport } = await import('../app/report/engine.js');
const { default: JSZip } = await import('jszip');

const BASE_DOCX = new Uint8Array(
    readFileSync(new URL('../../webapp/resources/report_base.docx', import.meta.url)));
const APP_DIR = fileURLToPath(new URL('../app/', import.meta.url));

const CLAUSE = '立柱铝型材开口部位的厚度不应小于3.0mm';
const PROJECT = { project_no: 'PLAT-01', house_name: '平台验证楼' };

/** 一个立柱式构件（2 个面，每面 5 个读数）。 */
const GROUPS = [{
    template_type: 'column',
    records: [{
        record: { floor: '六层', member_position: '1', size_result: '63×164', requirement_text: CLAUSE },
        faces: ['B', 'H'].map((face) => ({
            face, readings_text: ['2.99', '3.02', '3.01', '3.01', '2.99'], min_text: '2.99',
        })),
    }],
}];

/* --------------------------------------------------------------------------
 * 1. 导出不能依赖 Buffer
 * ------------------------------------------------------------------------ */

test('这个用例确实跑在"没有 Buffer"的环境里（否则下面的断言都是假的）', () => {
    assert.equal(typeof globalThis.Buffer, 'undefined');
});

test('浏览器环境（无 Buffer）也能导出：同一个 Document 走 arraybuffer 出字节', async () => {
    const bytes = await renderDocx(PROJECT, GROUPS, { baseDocxBytes: BASE_DOCX });

    assert.ok(bytes instanceof Uint8Array);
    assert.equal(String.fromCharCode(bytes[0], bytes[1]), 'PK', '应是 zip 容器');

    const zip = await JSZip.loadAsync(bytes);
    for (const part of ['word/document.xml', 'word/styles.xml', 'word/theme/theme1.xml']) {
        assert.ok(zip.file(part), `缺少 ${part}`);
    }
    const xml = await zip.file('word/document.xml').async('string');
    assert.match(xml, /幕墙立柱截面尺寸检测结果/);
    assert.match(xml, /w:linePitch="312"/, '后处理补丁照常生效（不是只把字节凑出来）');

    /* 产物正确性由闸门 A 锁死：它对比的正是这份 JS 产物与冻结基线，逐字节。
     * 换输出类型（nodebuffer → arraybuffer）不改变 zip 内容，闸门 A 在 Node 里
     * 跑的就是浏览器要跑的那条语句 —— 这是选 arraybuffer 而不是"判断有没有 Buffer
     * 再分叉"的第二个理由：分叉出来的那半条腿永远没人跑。 */
});

test('（正向对照）没有 Buffer 时 toBuffer 抛的就是真机那条错 —— 这就是被修掉的根因', async () => {
    const doc = buildProjectReport(PROJECT, GROUPS, []);

    await assert.rejects(() => Packer.toBuffer(doc),
        /nodebuffer is not supported by this platform/,
        '真机报错必须能在这里复现；复现不了说明这条用例没在模拟浏览器');

    // 同一个 Document 换成 arraybuffer 就正常 —— 差异只有那一个输出类型
    const bytes = new Uint8Array(await Packer.toArrayBuffer(doc));
    assert.equal(String.fromCharCode(bytes[0], bytes[1]), 'PK');
});

/* --------------------------------------------------------------------------
 * 2. 真机加载的那份 vendor/ 库也要能跑
 * ------------------------------------------------------------------------ */
/* 闸门 A/B/C 与所有 Node 测试用的都是 `node_modules/docx`；
 * 而浏览器加载的是 `web/vendor/docx.mjs`（`export_web_assets.py` 从同一个包 vendor 出来）。
 * 两者是**不同的构建产物**，此前从未被任何闸门执行过 —— 顺手把这条路验掉。 */

test('真机真正加载的 web/vendor/docx.mjs 也能在无 Buffer 下打包', async () => {
    const vendored = await import('../vendor/docx.mjs');

    const doc = new vendored.Document({
        sections: [{
            children: [new vendored.Paragraph({
                children: [new vendored.TextRun({ text: '幕墙立柱截面尺寸检测结果' })],
            })],
        }],
    });

    const bytes = new Uint8Array(await vendored.Packer.toArrayBuffer(doc));
    assert.equal(String.fromCharCode(bytes[0], bytes[1]), 'PK');

    const zip = await JSZip.loadAsync(bytes);
    const xml = await zip.file('word/document.xml').async('string');
    assert.match(xml, /幕墙立柱截面尺寸检测结果/);

    // 同一个 bundle 里 toBuffer 仍然是 Node 专用出口（证明上面验的是真环境）
    await assert.rejects(() => vendored.Packer.toBuffer(doc),
        /nodebuffer is not supported by this platform/);
});

/* --------------------------------------------------------------------------
 * 3. 静态审计：`web/app` 里不许出现只有 Node 才有的东西
 * ------------------------------------------------------------------------ */
/* 上面两条只覆盖"导出"这一条路；这一条覆盖**没被跑到的模块**
 * （备份导入导出、图片管线、下载……），防止同一个坑换个地方再踩一次。 */

/** 这些标识符/写法在浏览器里不存在（或含义不同），`web/app` 一律不许出现。 */
const NODE_ONLY = [
    // Buffer：本次真机 Bug 的元凶；它在不在会让同一行代码在两端行为不同
    {
        pattern: /\bBuffer\b/,
        why: 'Buffer 只在 Node 存在，库看到它就会走 Node 分支 → 浏览器里抛 "nodebuffer is not supported by this platform"',
    },
    // 库的 Node 专用出口：写出来就是"在浏览器里必炸"的同义词
    { pattern: /Packer\s*\.\s*toBuffer\s*\(/, why: 'toBuffer = nodebuffer 输出；改用 toArrayBuffer' },
    { pattern: /\bnodebuffer\b/, why: 'JSZip 的 Node 输出类型；浏览器必须用 arraybuffer' },
    // 打包工具 / CommonJS 才有的东西
    { pattern: /\bprocess\s*\.\s*(env|argv|platform|cwd|exit)\b/, why: 'process 是 Node 的，浏览器里 undefined' },
    { pattern: /\brequire\s*\(/, why: '浏览器没有 require（本工程用原生 ES module + import map）' },
    { pattern: /\b__dirname\b|\b__filename\b/, why: 'CommonJS 的目录变量，ESM/浏览器都没有' },
];

/** 递归收集 `web/app` 下的 .js（顺序稳定 → 报错信息可复现）。 */
function appSources() {
    const files = [];
    const walk = (dir) => {
        for (const entry of readdirSync(dir, { withFileTypes: true })
            .sort((left, right) => (left.name < right.name ? -1 : 1))) {
            const full = join(dir, entry.name);
            if (entry.isDirectory()) walk(full);
            else if (entry.name.endsWith('.js')) files.push(full);
        }
    };
    walk(APP_DIR);
    return files;
}

/**
 * 把注释与字符串挖空再审计（保留换行，行号不变）。
 *
 * 必须做两件事，各踩过一次：
 *  - 注释里出现这些词是**好事**（engine.js 里就写着"不能用 toBuffer"）；
 *    不挖掉注释，正解会被判成违规。
 *  - 字符串里出现也可能（错误文案里就有一模一样的词）；
 *    不挖掉字符串，就分不清"写在文案里"和"真去调用"。
 */
function stripCommentsAndStrings(source) {
    let out = '';
    let index = 0;
    let state = 'code';                    // code | line | block | single | double | template
    while (index < source.length) {
        const char = source[index];
        const next = source[index + 1];
        if (state === 'code') {
            if (char === '/' && next === '/') { state = 'line'; index += 2; continue; }
            if (char === '/' && next === '*') { state = 'block'; index += 2; continue; }
            if (char === "'") { state = 'single'; out += ' '; index += 1; continue; }
            if (char === '"') { state = 'double'; out += ' '; index += 1; continue; }
            if (char === '`') { state = 'template'; out += ' '; index += 1; continue; }
            out += char;
            index += 1;
            continue;
        }
        if (state === 'line') {
            if (char === '\n') { state = 'code'; out += '\n'; }
            index += 1;
            continue;
        }
        if (state === 'block') {
            if (char === '*' && next === '/') { state = 'code'; index += 2; continue; }
            if (char === '\n') out += '\n';   // 保留行号
            index += 1;
            continue;
        }
        // 字符串内部：整体挖空，转义序列一起跳过
        if (char === '\\') { out += '  '; index += 2; continue; }
        const quote = state === 'single' ? "'" : state === 'double' ? '"' : '`';
        out += char === quote ? ' ' : (char === '\n' ? '\n' : ' ');
        if (char === quote) state = 'code';
        index += 1;
    }
    return out;
}

test('静态审计：web/app 里不出现 Node 专有 API（Buffer / process / require / toBuffer）', () => {
    const files = appSources();
    assert.ok(files.length >= 15, `审计范围应覆盖 web/app 全部模块，实际 ${files.length} 个`);

    const violations = [];
    for (const file of files) {
        const lines = stripCommentsAndStrings(readFileSync(file, 'utf8')).split('\n');
        lines.forEach((line, offset) => {
            for (const rule of NODE_ONLY) {
                if (!rule.pattern.test(line)) continue;
                violations.push(`${file.replace(APP_DIR, 'web/app/')}:${offset + 1}  ${rule.why}`);
            }
        });
    }

    assert.deepEqual(violations, [], `发现 Node 专有用法（浏览器里会崩）：\n${violations.join('\n')}`);
});

test('静态审计的去噪工具本身可信：注释/字符串里的词不算违规，真代码里的算', () => {
    // 真代码里出现 → 必须保留（否则审计等于没扫）
    assert.match(stripCommentsAndStrings('const b = Buffer.from(x);'), /Buffer/);
    assert.match(stripCommentsAndStrings('writeFileSync(await Packer.toBuffer(doc));'),
        /Packer\s*\.\s*toBuffer\s*\(/);
    // 注释里出现 → 必须挖掉（M5 的审计脚本被自己的注释骗过一次）
    assert.doesNotMatch(stripCommentsAndStrings('// 不能用 Buffer 哦'), /Buffer/);
    assert.doesNotMatch(stripCommentsAndStrings('/* Packer.toBuffer 会炸 */'), /toBuffer/);
    // 字符串里出现 → 也要挖掉（错误文案里就写着这个字）
    assert.doesNotMatch(stripCommentsAndStrings("throw new Error('nodebuffer is not supported')"),
        /nodebuffer/);
    // 但字符串**之外**的同名标识符仍要命中
    assert.match(stripCommentsAndStrings("throw new Error('x'); nodebuffer = 1"), /nodebuffer/);
    // 行号不能丢（违规要指到行）
    assert.equal(stripCommentsAndStrings('a\n// c\nb').split('\n').length, 3);
});
