/* 附页：两列信息表、页码、图片嵌入与缺失降级。
 *
 * 断言走**生成的 XML**（交付物与闸门关心的东西），不碰 docx 库的内部对象。
 * 附页的期望结构由 `tests/fixtures/attachment_baseline.docx`（Python 引擎冻结产物）定义，
 * 这里只锁"引擎自己的结构决策"；逐属性对拍是 `tools/compare_report_with_sample.py` 的职责。
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import JSZip from 'jszip';

import { CONFIG } from '../app/config.js';
import { SPEC } from '../app/report/spec.js';
import { fitImageTwips } from '../app/report/attachments.js';
import { attachmentRows } from '../app/report/attachments.js';
import { attachmentViews } from '../app/report/attachments.js';
import { renderDocx } from '../app/report/engine.js';

const BASE_DOCX = new Uint8Array(
    readFileSync(new URL('../../webapp/resources/report_base.docx', import.meta.url)));

const PROJECT = { project_no: 'P-1', house_name: '示例', house_address: '', client_org: '', test_date: '' };
const GROUP = {
    template_type: 'column',
    records: [{
        record: { floor: '六层', member_position: '1', size_result: '63×164', requirement_text: '不应小于3.0mm' },
        faces: [{ face: 'B', readings_text: ['2.99', '3.02', '3.01', '3.01', '2.99'], min_text: '2.99' }],
    }],
};

/** 一份缺陷行（`image_path` 是 images store 的主键）。 */
function defect(overrides = {}) {
    return {
        id: 1,
        defect_type: '密封胶开裂',
        project_part: '东立面三层 1# 立柱',
        risk_level: '高',
        rectification_plan: '清除后重新注胶。',
        related_standards: null,
        extra_advice: null,
        reporter_name: 'Zeyu Jin',
        reporter_department: '结构工程部',
        image_path: 'abc123_隐患照片.jpg',
        created_at: '2026-09-20 10:24:00',
        ...overrides,
    };
}

/** 假编解码器：解码尺寸给定，编码返回一个可 arrayBuffer 的假 blob。 */
function fakeCodec({ width, height }) {
    return {
        decode: async () => ({ source: {}, width, height, orientation: 1 }),
        createCanvas: (canvasWidth, canvasHeight) => ({
            getContext: () => ({
                save() {}, restore() {}, setTransform() {}, fillRect() {}, fillStyle: '', drawImage() {},
            }),
            convertToBlob: async () => ({
                size: 100,
                type: 'image/jpeg',
                arrayBuffer: async () => new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46,
                    0x49, 0x46, 0x00, 0x01]).buffer,
            }),
        }),
    };
}

async function bodyXml(bytes) {
    const zip = await JSZip.loadAsync(bytes);
    return {
        xml: await zip.file('word/document.xml').async('string'),
        zip,
    };
}

/** 取出全部附页表格（两列、grid 1600/7200）。 */
function attachmentTables(xml) {
    return (xml.match(/<w:tbl>[\s\S]*?<\/w:tbl>/g) ?? [])
        .filter((table) => /<w:gridCol w:w="1600"\/><w:gridCol w:w="7200"\/>/.test(table));
}

function paragraphsWith(xml, needle) {
    return (xml.match(/<w:p\b[\s\S]*?<\/w:p>/g) ?? []).filter((p) => p.includes(needle));
}

/* --------------------------------------------------------------------------
 * 版式换算（与 Python 的 fit_image_twips 同源）
 * ------------------------------------------------------------------------ */

test('fitImageTwips：适配上限且不放大（与 Python 逐值一致）', () => {
    // Python: scale = min(8800/w, 8000/h, 15)；800×600 → 8800×6600
    assert.deepEqual(fitImageTwips(800, 600), [8800, 6600]);
    // 3200×2400 → 长边贴 8800
    assert.deepEqual(fitImageTwips(3200, 2400), [8800, 6600]);
    // 小图按 1px=15twips 的自然尺寸，不拉伸
    assert.deepEqual(fitImageTwips(100, 50), [1500, 750]);
    // 很高的图受 8000 twips 高度上限约束
    assert.deepEqual(fitImageTwips(1000, 5000), [1600, 8000]);
    // 非法尺寸 → 0,0（排版层会当成缺失）
    assert.deepEqual(fitImageTwips(0, 100), [0, 0]);
    assert.deepEqual(fitImageTwips(-1, -1), [0, 0]);
});

test('attachmentRows：9 行，顺序与标签来自 config（不硬编码在引擎里）', () => {
    const rows = attachmentRows({
        defect: defect(), original_name: '隐患照片.jpg', missing: false, compressed: false,
    });
    assert.equal(rows.length, CONFIG.ATTACHMENT_ORDER.length);
    assert.equal(rows.length, 9);
    assert.deepEqual(rows.map((row) => row.label),
        CONFIG.ATTACHMENT_ORDER.map((key) => CONFIG.ATTACHMENT_LABELS[key]));
    assert.ok(rows.every((row) => row.height === SPEC.attachment.rowHeightTwips));
    // 「图片文件」那一行是可追溯的原文件名
    assert.equal(rows.at(-1).value, '隐患照片.jpg');
});

test('attachmentRows：空字段显示「无」，压缩与缺失标注在图片文件行上', () => {
    const base = { defect: defect(), original_name: '隐患照片.jpg' };
    const empty = attachmentRows({ ...base, missing: false, compressed: false });
    assert.equal(empty.find((row) => row.label === '补充建议').value, CONFIG.EMPTY_TEXT);
    assert.equal(empty.find((row) => row.label === '相关规范').value, CONFIG.EMPTY_TEXT);
    assert.equal(empty.find((row) => row.label === '报告人').value, 'Zeyu Jin（结构工程部）');
    assert.equal(empty.find((row) => row.label === '报告时间').value, '2026-09-20 10:24');

    const compressed = attachmentRows({ ...base, missing: false, compressed: true });
    assert.equal(compressed.at(-1).value, '隐患照片.jpg（已压缩）');
    const missing = attachmentRows({ ...base, missing: true, compressed: false });
    assert.equal(missing.at(-1).value, '隐患照片.jpg（文件缺失）');
});

/* --------------------------------------------------------------------------
 * 装配：标题分页、两列表、图片嵌入
 * ------------------------------------------------------------------------ */

test('附页标题：编号 / 加粗 / 居中 / pageBreakBefore（每份独立成页）', async () => {
    const views = await attachmentViews([defect(), defect({ id: 2, project_part: '西立面' })], {
        loadImage: async () => null,
        codec: fakeCodec({ width: 800, height: 600 }),
    });
    const { xml } = await bodyXml(await renderDocx(PROJECT, [GROUP], {
        attachments: views, baseDocxBytes: BASE_DOCX,
    }));

    const titles = paragraphsWith(xml, '检测报告附页');
    assert.equal(titles.length, 2);
    assert.match(titles[0], />检测报告附页（1\/2）</);
    assert.match(titles[1], />检测报告附页（2\/2）</);
    for (const title of titles) {
        assert.match(title, /<w:pageBreakBefore\/>/, '标题必须带分页，否则附页会挤在上一页');
        assert.match(title, /<w:jc w:val="center"\/>/);
        assert.match(title, /<w:b\/>/, '标题加粗');
    }
});

test('两列信息表：grid 1600/7200、行高 400、标签加粗居中、内容左对齐', async () => {
    const view = (await attachmentViews([defect()], {
        loadImage: async () => null,
        codec: fakeCodec({ width: 800, height: 600 }),
    }))[0];
    const { xml } = await bodyXml(await renderDocx(PROJECT, [GROUP], {
        attachments: [view], baseDocxBytes: BASE_DOCX,
    }));

    const tables = attachmentTables(xml);
    assert.equal(tables.length, 1);
    const rows = tables[0].match(/<w:tr\b[\s\S]*?<\/w:tr>/g);
    assert.equal(rows.length, 9);

    for (const row of rows) {
        assert.match(row, /<w:trHeight w:val="400"\/>/);
        const cells = row.match(/<w:tc>[\s\S]*?<\/w:tc>/g);
        assert.equal(cells.length, 2, '两列信息表每行恰好两格');
        assert.match(cells[0], /<w:tcW\b[^>]*w:w="1600"[^>]*\/>/, '标签列宽 1600');
        assert.match(cells[1], /<w:tcW\b[^>]*w:w="7200"[^>]*\/>/, '内容列宽 7200');
        assert.match(cells[0], /<w:b\/>/, '标签列加粗');
        assert.ok(!/<w:b\/>/.test(cells[1]), '内容列不加粗');
        assert.match(cells[0], /<w:jc w:val="center"\/>/, '标签居中');
        assert.match(cells[1], /<w:jc w:val="left"\/>/, '内容左对齐');
    }
    // 空字段「无」出现在产物里
    assert.match(xml, />无</);
});

test('图片嵌入：显示尺寸 = twips × 635 EMU，媒体部件带上原图字节', async () => {
    const view = (await attachmentViews([defect()], {
        loadImage: async () => ({ fake: true }),
        codec: fakeCodec({ width: 800, height: 600 }),
    }))[0];
    assert.deepEqual([view.image_width_px, view.image_height_px], [800, 600]);

    const bytes = await renderDocx(PROJECT, [GROUP], { attachments: [view], baseDocxBytes: BASE_DOCX });
    const { xml, zip } = await bodyXml(bytes);

    // 「隐患图片」标签 + 图片段落
    assert.equal(paragraphsWith(xml, '隐患图片').length, 1);
    const [widthTwips, heightTwips] = fitImageTwips(800, 600);
    assert.match(xml, new RegExp(`<wp:extent cx="${widthTwips * 635}" cy="${heightTwips * 635}"/>`));

    const media = Object.keys(zip.files).filter((name) => name.startsWith('word/media/') && !name.endsWith('/'));
    assert.equal(media.length, 1, '必须恰好嵌入一张图');
    assert.match(media[0], /\.jpe?g$/);
});

test('图片缺失：降级成一行说明，不嵌图、也不抛错', async () => {
    const views = await attachmentViews([defect()], {
        loadImage: async () => null,
        codec: fakeCodec({ width: 800, height: 600 }),
    });
    assert.equal(views[0].missing, true);

    const bytes = await renderDocx(PROJECT, [GROUP], { attachments: views, baseDocxBytes: BASE_DOCX });
    const { xml, zip } = await bodyXml(bytes);

    assert.match(xml, /（图片缺失：隐患照片\.jpg）/);
    assert.equal(paragraphsWith(xml, '隐患图片').length, 0);
    assert.ok(!/<w:drawing/.test(xml), '降级时不该写 drawing');
    assert.equal(Object.keys(zip.files)
        .filter((name) => name.startsWith('word/media/') && !name.endsWith('/')).length, 0);
});

test('图片解码抛错时只影响这一份附页（其余照常导出）', async () => {
    const broken = {
        decode: async () => { throw new Error('坏图'); },
        createCanvas: () => { throw new Error('坏图'); },
    };
    const views = await attachmentViews(
        [defect(), defect({ id: 2, image_path: 'def456_另一张.jpg' })],
        {
            loadImage: async (key) => (key.startsWith('abc') ? { good: true } : null),
            codec: broken,
        });
    assert.equal(views[0].missing, true, '坏图 → 降级');
    assert.equal(views[1].missing, true, '第二张本来就没有');
    assert.equal(views.length, 2, '两份附页都要留着');
});

test('三份附页：编号连续、顺序跟随缺陷行顺序', async () => {
    const rows = [
        defect({ id: 1, project_part: 'A' }),
        defect({ id: 2, project_part: 'B' }),
        defect({ id: 3, project_part: 'C' }),
    ];
    const views = await attachmentViews(rows, {
        loadImage: async () => null,
        codec: fakeCodec({ width: 800, height: 600 }),
    });
    const { xml } = await bodyXml(await renderDocx(PROJECT, [GROUP], {
        attachments: views, baseDocxBytes: BASE_DOCX,
    }));

    assert.deepEqual(
        paragraphsWith(xml, '检测报告附页').map((p) => /检测报告附页（\d\/\d）/.exec(p)[0]),
        ['检测报告附页（1/3）', '检测报告附页（2/3）', '检测报告附页（3/3）']);
    assert.equal(attachmentTables(xml).length, 3);
});

test('附页在备注之后、文末空段之前（顺序与 Python 一致）', async () => {
    const views = await attachmentViews([defect()], {
        loadImage: async () => null,
        codec: fakeCodec({ width: 800, height: 600 }),
    });
    const { xml } = await bodyXml(await renderDocx(PROJECT, [GROUP], {
        attachments: views, baseDocxBytes: BASE_DOCX,
    }));

    const noteAt = xml.indexOf('备注：');
    const titleAt = xml.indexOf('检测报告附页');
    assert.ok(noteAt > 0 && titleAt > noteAt, '附页必须在备注之后');
});

/* --------------------------------------------------------------------------
 * 回归：没有附页时，产物必须与 M2 完全一致
 * ------------------------------------------------------------------------ */

test('无附页时正文序列不变（附页是纯追加，不影响 M2 路径）', async () => {
    const without = await bodyXml(await renderDocx(PROJECT, [GROUP], { baseDocxBytes: BASE_DOCX }));
    const empty = await bodyXml(await renderDocx(PROJECT, [GROUP], {
        attachments: [], baseDocxBytes: BASE_DOCX,
    }));
    assert.equal(empty.xml, without.xml);

    // 只看**正文级**元素：表格先摘掉（单元格里的 <w:p> 混在一起会数错）。
    // 注意文末空段是自闭合的 <w:p/>，用 /<w:p>/ 会漏掉它（踩过一次）。
    const stripped = without.xml.replace(/<w:tbl>[\s\S]*?<\/w:tbl>/g, 'TBL');
    const tags = [...stripped.matchAll(/<w:p\/>|<w:p>|TBL/g)]
        .map((match) => (match[0] === 'TBL' ? 'tbl' : 'p'));
    // 信息段 5 + 章节标题 1 + 表 + 空段 + 备注 + 文末空段
    assert.deepEqual(tags, ['p', 'p', 'p', 'p', 'p', 'p', 'tbl', 'p', 'p', 'p']);
    assert.ok(!/检测报告附页/.test(without.xml));
});
