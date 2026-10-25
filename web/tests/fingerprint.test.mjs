/* 闸门 C：**纯 JS** 的文档自检（不借助 Python）。
 *
 * 这一层验三件事，缺一不可：
 *  1. **能跑通**：用 JS 引擎现场生成 docx → 用 JS 指纹实现算指纹 → 与 Python 冻结的
 *     指纹 JSON 逐属性一致。这是"没有 Python 的环境也能自检"的闭环。
 *  2. **抽得全**：两个指纹对象**完全相同**（连键集合与顺序都一样）——
 *     只要 JS 少抽了一个维度，diff 就会报键不一致，所以"相等"这件事本身证明了抽取完整。
 *  3. **抓得住**：往基线 docx 里逐个"下毒"（改文字 / 改行高 / 破坏合并 / 改页面网格），
 *     必须有差异、且落在**预期的那一类路径**上。
 *
 * 第 3 条是这个项目反复吃过的亏（M5 设计 §0.1：闸门绿了先问"这个属性到底有没有被比"）：
 * 一个只会说"一致"的自检，和不存在的自检没有区别。
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import JSZip from 'jszip';
import { JSDOM } from 'jsdom';

import {
    diff, fingerprintDocument, mediaSizes, paragraphImages, summarizeDiffs,
} from '../app/report/fingerprint.js';
import { renderDocx } from '../app/report/engine.js';

const ROOT = new URL('../../', import.meta.url);
const DOMParserImpl = new JSDOM('').window.DOMParser;

const READ = (path) => new Uint8Array(readFileSync(new URL(path, ROOT)));
const BASELINE_DOCX = new Uint8Array(readFileSync(new URL('tests/fixtures/generated_baseline.docx', ROOT)));
const BASELINE_FINGERPRINT = JSON.parse(
    readFileSync(new URL('tests/fixtures/generated_baseline.fingerprint.json', ROOT), 'utf8'));
const FIXTURE = JSON.parse(
    readFileSync(new URL('web/assets/fixture_data.json', ROOT), 'utf8'));
const BASE_DOCX = READ('webapp/resources/report_base.docx');

/** 从 docx 字节里取出 document.xml 与 media（与 tools/js/check_gate_c.mjs 同一逻辑）。 */
async function readDocx(bytes) {
    const zip = await JSZip.loadAsync(bytes);
    const documentXml = await zip.file('word/document.xml').async('string');
    const media = [];
    for (const name of Object.keys(zip.files)) {
        if (!name.startsWith('word/media/') || name.endsWith('/')) continue;
        media.push({ name, bytes: await zip.file(name).async('uint8array') });
    }
    return { documentXml, media };
}

const fingerprintOf = async (bytes) => fingerprintDocument(await readDocx(bytes), { DOMParserImpl });

/* --------------------------------------------------------------------------
 * 1 + 2：JS 引擎现场产物 → JS 指纹 → 与 Python 冻结的指纹一致
 * ------------------------------------------------------------------------ */

test('闸门 C：JS 引擎现场生成的 docx，其 JS 指纹与 Python 冻结的指纹完全一致', async () => {
    const bytes = await renderDocx(FIXTURE.project, FIXTURE.groups, { baseDocxBytes: BASE_DOCX });
    const actual = await fingerprintOf(bytes);

    const problems = diff(BASELINE_FINGERPRINT, actual, 'doc');
    assert.deepEqual(problems, [],
        `闸门 C 不一致：\n${summarizeDiffs(problems).join('\n')}`);

    // 相等还不够 —— 还要确认这份指纹**非空**（否则"两个空对象相等"也是绿）
    assert.equal(actual.children.length, 14);
    assert.equal(actual.tables.length, 2);
    assert.equal(actual.tables[0].rows.length, 12, '立柱表应为 表头 2 行 + 10 个检测面');
    assert.match(actual.children[0].text, /^项目编号：/);
});

test('闸门 C：冻结基线 docx 的指纹也等于冻结的指纹 JSON（两边同源）', async () => {
    const actual = await fingerprintOf(BASELINE_DOCX);
    assert.deepEqual(diff(BASELINE_FINGERPRINT, actual, 'doc'), []);
});

test('抽取是完整的：两个指纹的键集合完全一致（少一个维度就会报键不一致）', async () => {
    const actual = await fingerprintOf(BASELINE_DOCX);
    const keysOf = (value) => Object.keys(value).sort();
    assert.deepEqual(keysOf(actual), keysOf(BASELINE_FINGERPRINT));
    assert.deepEqual(keysOf(actual.children[0]), keysOf(BASELINE_FINGERPRINT.children[0]));
    assert.deepEqual(keysOf(actual.tables[0]), keysOf(BASELINE_FINGERPRINT.tables[0]));
    assert.deepEqual(keysOf(actual.tables[0].rows[0].cells[0]),
        keysOf(BASELINE_FINGERPRINT.tables[0].rows[0].cells[0]));
});

/* --------------------------------------------------------------------------
 * 3：抓得住 —— 往 XML 里下毒，必须报在预期的路径上
 * ------------------------------------------------------------------------ */

const POISONS = [
    ['一处文字改一个字', (xml) => xml.replace('A06YG-2026-001', 'A06YG-2026-002'),
        'children[0].text'],
    ['数据行的行高改了', (xml) => xml.replace('<w:trHeight w:val="522"/>', '<w:trHeight w:val="527"/>'),
        // trHeight 是 `[val, hRule]` 二元组，diff 递归到元素级 → 落点是 [0]
        'tables[0].rows[2].trHeight[0]'],
    ['纵向合并的续格被删掉了（合并结构变了）', (xml) => xml.replace('<w:vMerge/>', ''),
        'tables[0].rows[1].cells[0].vMerge'],
    ['单元格宽度改了', (xml) => xml.replace('<w:tcW w:type="dxa" w:w="1077"/>',
        '<w:tcW w:type="dxa" w:w="1088"/>'),
        'tables[0].rows[0].cells[0].tcW.w'],
    ['表级单元格边距被补了 top', (xml) => xml.replace('<w:tblCellMar><w:left',
        '<w:tblCellMar><w:top w:type="dxa" w:w="0"/><w:left'),
        'tables[0].tblCellMar.top'],
    ['docGrid 行距改了', (xml) => xml.replace('w:linePitch="312"', 'w:linePitch="360"'),
        'children[13].docGrid.linePitch'],
    ['合并网格被破坏（表头跨列数改了）', (xml) => xml.replace('<w:gridSpan w:val="7"/>', '<w:gridSpan w:val="6"/>'),
        'tables[0].rows[0].cells[3].gridSpan'],
];

test('闸门 C 抓得住：7 处下毒都必须报在预期路径上', async () => {
    const { documentXml, media } = await readDocx(BASELINE_DOCX);
    const healthy = fingerprintDocument({ documentXml, media }, { DOMParserImpl });
    assert.deepEqual(diff(BASELINE_FINGERPRINT, healthy, 'doc'), [], '先确认原样是一致（阴性对照）');

    for (const [label, poison, expectedPath] of POISONS) {
        const mutated = poison(documentXml);
        // 用 ok 而不是 notEqual：后者失败时会把整份 XML 打到日志里
        assert.ok(mutated !== documentXml, `下毒没生效（字符串没匹配上）：${label}`);

        const fingerprint = fingerprintDocument({ documentXml: mutated, media }, { DOMParserImpl });
        const problems = diff(BASELINE_FINGERPRINT, fingerprint, 'doc');
        const paths = problems.map((item) => item.path);

        assert.ok(problems.length > 0, `没抓到：${label}`);
        assert.ok(paths.some((path) => path === `doc.${expectedPath}`),
            `${label} 抓到了，但落点不对：期望 doc.${expectedPath}，实际 ${paths.slice(0, 3).join(', ')}`);
    }
});

/* --------------------------------------------------------------------------
 * 闸门 C **看不见**的一样东西（必须写下来，否则将来会有人以为它"验过了"）
 * ------------------------------------------------------------------------ */

test('已知盲区：指纹不区分 <w:vMerge/> 与 <w:vMerge w:val="continue"/>', async () => {
    // 为什么这是"已知盲区"而不是 bug：与 Python 的 `cell_fingerprint` 一致 ——
    // 那边写的是 `(val_of(...) or "continue")`，两种写法归一成同一个值。
    // **真正抓得住它的是闸门 A/B 的 `layout_grid`**（那边只认"无 val = 续格"）。
    // 也就是说：闸门 C 单独绿 ≠ 合并结构一定对。
    // 这条测试把"口径边界"钉在代码里，而不是只写在文档里。
    const { documentXml, media } = await readDocx(BASELINE_DOCX);
    const mutated = documentXml.replace('<w:vMerge/>', '<w:vMerge w:val="continue"/>');
    assert.notEqual(mutated, documentXml, '下毒没生效');

    const fingerprint = fingerprintDocument({ documentXml: mutated, media }, { DOMParserImpl });
    assert.deepEqual(diff(BASELINE_FINGERPRINT, fingerprint, 'doc'), [],
        '如果这里开始报差异，说明口径变了 —— 请同步 Python 的 cell_fingerprint 与本文档');

    // 但"续格被整个删掉"这种**结构性**改动必须能抓到（上面 POISONS 里已经验过）
    const structural = documentXml.replace('<w:vMerge/>', '');
    const caught = diff(BASELINE_FINGERPRINT,
        fingerprintDocument({ documentXml: structural, media }, { DOMParserImpl }), 'doc');
    assert.ok(caught.some((item) => item.path === 'doc.tables[0].rows[1].cells[0].vMerge'));
});

/* --------------------------------------------------------------------------
 * 图片尺寸：EXIF 摆正 + 多重集排序（用仓库里真实的夹具图片）
 * ------------------------------------------------------------------------ */

test('媒体像素尺寸：按 EXIF 摆正后再比，且与部件编号无关', () => {
    const portrait = new Uint8Array(readFileSync(
        new URL('tests/fixtures/attachment/9c8b7a6d5e4f3a2b1c0d9e8f7a6b5c4d_现场照片_竖拍.jpg', ROOT)));
    const portraitOriented = new Uint8Array(readFileSync(
        new URL('tests/fixtures/attachment/9c8b7a6d5e4f3a2b1c0d9e8f7a6b5c4d_现场照片_竖拍_摆正.jpg', ROOT)));
    const landscape = new Uint8Array(readFileSync(
        new URL('tests/fixtures/attachment/5f3a1c7e9b2d4a6f8c0e1d2b3a4c5d6e_现场照片_横拍.jpg', ROOT)));

    // 存储 600×800 + Orientation=6 → 比较时按摆正后的 800×600
    assert.deepEqual(mediaSizes([{ name: 'word/media/image1.jpg', bytes: portrait }]), [[800, 600]]);
    assert.deepEqual(mediaSizes([{ name: 'word/media/image2.jpg', bytes: portraitOriented }]), [[800, 600]]);
    assert.deepEqual(mediaSizes([{ name: 'word/media/image3.jpg', bytes: landscape }]), [[800, 600]]);

    // 多重集：顺序无关、编号无关
    assert.deepEqual(
        mediaSizes([
            { name: 'word/media/b.jpg', bytes: portrait },
            { name: 'word/media/a.jpg', bytes: landscape },
        ]),
        [[800, 600], [800, 600]]);

    // 认不出的部件跳过（Python 那边会抛错，这里选择"不因为一个坏部件炸掉整份自检"）
    assert.deepEqual(mediaSizes([{ name: 'word/media/x.bin', bytes: new Uint8Array([1, 2, 3, 4]) }]), []);
});

test('段落的图片显示尺寸：取 wp:extent，不依赖关系 id', () => {
    const xml = `<?xml version="1.0"?>
<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
     xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
  <w:r><w:drawing><wp:inline><wp:extent cx="5588000" cy="4191000"/></wp:inline></w:drawing></w:r>
</w:p>`;
    const document = new DOMParserImpl().parseFromString(xml, 'application/xml');
    const paragraph = document.getElementsByTagNameNS(
        'http://schemas.openxmlformats.org/wordprocessingml/2006/main', 'p')[0];
    assert.deepEqual(paragraphImages(paragraph), [[5588000, 4191000]]);
});
