/* M5 的 Node CLI：读 fixture_data.json → 用 JS 引擎生成 docx（闸门 A 的被测产物）。
 *
 * 用途是"移植验收"：拿基准自己的数据，用 JS 引擎重新生成，再交给
 * `python tools/compare_report_with_sample.py --expected <冻结基线> --actual <本产物>`
 * 逐属性对拍。
 *
 * 产物**两份**，覆盖引擎的两条路径：
 *   `_work/js_generated.docx`              无附页 → 对拍 `tests/fixtures/generated_baseline.docx`
 *   `_work/js_generated_attachments.docx`  含附页 → 对拍 `tests/fixtures/attachment_baseline.docx`
 * 两份共用同一批项目信息与检测记录，所以"有附页/无附页"的差异只可能来自附页本身。
 *
 * 图片走**替身编解码器**（Node 没有 canvas）：见 tools/js/fixture-codec.mjs 里对
 * "哪些是真的、哪些是替身"的逐条说明。
 *
 * 用法：
 *     node tools/js/generate_from_fixture.mjs [输出前缀] [--data <fixture_data.json>]
 *     默认输出前缀 _work/js_generated（→ 上面两个文件名）
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { attachmentViews } from '../../web/app/report/attachments.js';
import { renderDocx } from '../../web/app/report/engine.js';
import { imageCodec, passthroughCodec } from './fixture-codec.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

const argv = process.argv.slice(2);
const dataIndex = argv.indexOf('--data');
const dataPath = dataIndex >= 0 ? argv[dataIndex + 1] : 'web/assets/fixture_data.json';
const positional = argv.filter((value, index) => (
    !value.startsWith('--') && index !== dataIndex + 1));
const prefix = positional[0] ?? '_work/js_generated';
const baseDocxBytes = new Uint8Array(readFileSync(resolve(ROOT, 'webapp/resources/report_base.docx')));

/** 读仓库内文件；不存在返回 null（缺失图片的分支就靠它）。 */
function readFile(relative) {
    if (!relative) return null;
    const target = resolve(ROOT, relative);
    return existsSync(target) ? new Uint8Array(readFileSync(target)) : null;
}

const payload = JSON.parse(readFileSync(resolve(ROOT, dataPath), 'utf8'));

/* ---- 无附页：M2 路径 ---- */
const plainBytes = await renderDocx(payload.project, payload.groups, { baseDocxBytes });
const plainPath = resolve(ROOT, `${prefix}.docx`);
mkdirSync(dirname(plainPath), { recursive: true });
writeFileSync(plainPath, plainBytes);

/* ---- 含附页：M3 路径 ---- */
const entries = payload.attachments ?? [];

const decoded = [];
const views = await attachmentViews(entries.map((entry) => entry.defect), {
    // 按 image_path（= image key）找源图：夹具里"缺图"的那份指向不存在的文件，
    // 于是 loadImage 返回 null → missing=true → 引擎降级
    loadImage: async (key) => {
        const entry = entries.find((item) => item.defect.image_path === key);
        if (!entry?.source) return null;
        const bytes = readFile(entry.source);
        return bytes ? { path: entry.source, bytes } : null;
    },
    codec: codecFor(entries, decoded),
});

const attachmentBytes = await renderDocx(payload.project, payload.groups, {
    attachments: views,
    baseDocxBytes,
});
const attachmentPath = resolve(ROOT, `${prefix}_attachments.docx`);
writeFileSync(attachmentPath, attachmentBytes);

/* ---- 报告 ---- */
const faces = payload.groups.reduce(
    (sum, group) => sum + group.records.reduce((count, item) => count + item.faces.length, 0), 0);
console.log(`已生成：${plainPath}`);
console.log(`已生成：${attachmentPath}`);
console.log(`  数据源：${dataPath}（项目 ${payload.project.project_no}；`
    + `${payload.groups.length} 组 / ${faces} 个检测面；附页 ${views.length} 份）`);
for (const entry of decoded) {
    console.log(`  图片：${entry.path} 存储 ${entry.stored[0]}×${entry.stored[1]}`
        + ` → 摆正 ${entry.display[0]}×${entry.display[1]}`
        + `（EXIF 方向 ${entry.orientation}）`);
}
for (const view of views) {
    console.log(`  附页：${view.original_name} → `
        + (view.missing ? '降级（图片缺失）'
            : `${view.image_width_px}×${view.image_height_px} px`
              + `${view.compressed ? ' / 已压缩' : ''}`));
}

/**
 * 替身编解码器按"这张图有没有 EXIF 方向"分流：
 *   - 有方向 → imageCodec：按方向算显示尺寸，编码时交出 `_摆正` 副本（真的摆正过）
 *   - 没方向 → passthroughCodec：字节直通，只剥掉 EXIF
 * `attachmentViews` 每张图都会调用一次 decode/createCanvas，所以这里用"当前源路径"分流。
 */
function codecFor(list, log) {
    let current = null;
    const codecs = new Map();
    for (const entry of list) {
        if (!entry.source) continue;
        codecs.set(entry.source, entry.oriented_source
            ? imageCodec({
                path: entry.source,
                orientedPath: entry.oriented_source,
                readFile,
                log: (item) => log.push(item),
            })
            : passthroughCodec({ path: entry.source, readFile }));
    }
    return {
        decode: async (file) => {
            current = file?.path;
            const codec = codecs.get(current);
            if (!codec) throw new Error(`没有为 ${current} 准备编解码替身`);
            return codec.decode(file);
        },
        createCanvas: (width, height) => {
            const codec = codecs.get(current);
            if (!codec) throw new Error(`没有为 ${current} 准备编解码替身`);
            return codec.createCanvas(width, height);
        },
    };
}
