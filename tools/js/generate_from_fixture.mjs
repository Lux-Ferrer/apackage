/* M5-2 的 Node CLI：读 fixture_data.json → 用 JS 引擎生成 docx。
 *
 * 用途是"移植验收"：拿基准自己的数据，用 JS 引擎重新生成，再交给
 * `tools/compare_report_with_sample.py --expected <冻结基线> --actual <本产物>`
 * 逐属性对拍（差异清单就是 M5-2 后续收敛的 TODO）。
 *
 * 用法：
 *     node tools/js/generate_from_fixture.mjs [输出路径] [--data <fixture_data.json>]
 *     默认输出 _work/js_generated.docx
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { renderDocx } from '../../web/app/report/engine.js';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

const argv = process.argv.slice(2);
const outputIndex = argv.findIndex((value) => !value.startsWith('--'));
const dataIndex = argv.indexOf('--data');
const dataPath = dataIndex >= 0 ? argv[dataIndex + 1] : 'web/assets/fixture_data.json';
const outputPath = outputIndex >= 0 ? argv[outputIndex] : '_work/js_generated.docx';

const payload = JSON.parse(readFileSync(resolve(ROOT, dataPath), 'utf8'));
const baseDocxBytes = new Uint8Array(readFileSync(resolve(ROOT, 'webapp/resources/report_base.docx')));

const bytes = await renderDocx(payload.project, payload.groups, {
    attachments: payload.attachments ?? [],
    baseDocxBytes,
});

const target = resolve(ROOT, outputPath);
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, bytes);

const faces = payload.groups.reduce(
    (sum, group) => sum + group.records.reduce((count, item) => count + item.faces.length, 0), 0);
console.log(`已生成：${target}`);
console.log(`  数据源：${dataPath}（项目 ${payload.project.project_no}；`
    + `${payload.groups.length} 组 / ${faces} 个检测面）`);
console.log(`  字节数：${bytes.length}`);
