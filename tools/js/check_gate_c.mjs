/* 闸门 C：**不借助 Python** 核对导出产物。
 *
 * 与闸门 A/B 的分工（M5 设计 §4.1）：
 *   A  JS 产物 vs Python 冻结基线         ← 需要 Python
 *   B  JS 产物 vs 真实客户报告裁剪版       ← 需要 Python
 *   C  JS 产物 vs 语言中立的指纹 JSON      ← **只要 Node**（本文件）
 *
 * 为什么必须有 C：闸门 A/B 都依赖 Python 脚本，那意味着"没有 Python 的环境
 * （PWA 自身、只有 Node 的 CI 步骤）无法自检"。C 让这条链在任何 JS 运行时里都能闭环 ——
 * 也能让"用户在手机上导出后自己验一下"在将来成为可能。
 *
 * 用法：
 *   node tools/js/check_gate_c.mjs                       # 默认比 _work/js_generated.docx
 *   node tools/js/check_gate_c.mjs --actual <docx> --expected <json>
 *   node tools/js/check_gate_c.mjs --fingerprint <docx>  # 只打印指纹（用于重新冻结）
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import JSZip from 'jszip';
import { JSDOM } from 'jsdom';

import { diff, fingerprintDocument, summarizeDiffs } from '../../web/app/report/fingerprint.js';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const DOMParserImpl = new JSDOM('').window.DOMParser;

const args = process.argv.slice(2);
const option = (name, fallback) => {
    const index = args.indexOf(name);
    return index >= 0 ? args[index + 1] : fallback;
};

const expectedPath = resolve(ROOT, option('--expected', 'tests/fixtures/generated_baseline.fingerprint.json'));
const actualPath = resolve(ROOT, option('--actual', '_work/js_generated.docx'));
const fingerprintTarget = option('--fingerprint', null);
const target = fingerprintTarget ? resolve(ROOT, fingerprintTarget) : actualPath;

/** 从 docx 里取出 document.xml 与全部 media（不落盘）。 */
async function readDocx(path) {
    const zip = await JSZip.loadAsync(readFileSync(path));
    const documentXml = await zip.file('word/document.xml').async('string');
    const media = [];
    for (const name of Object.keys(zip.files)) {
        if (!name.startsWith('word/media/') || name.endsWith('/')) continue;
        media.push({ name, bytes: await zip.file(name).async('uint8array') });
    }
    return { documentXml, media };
}

const actualFingerprint = fingerprintDocument(await readDocx(target), { DOMParserImpl });

if (fingerprintTarget) {
    const out = resolve(ROOT, option('--out', '') || '');
    if (option('--out', null)) {
        mkdirSync(dirname(out), { recursive: true });
        writeFileSync(out, `${JSON.stringify(actualFingerprint, null, 2)}\n`);
        console.log(`指纹已写入：${option('--out')}`);
    } else {
        console.log(JSON.stringify(actualFingerprint, null, 2));
    }
    process.exit(0);
}

const expected = JSON.parse(readFileSync(expectedPath, 'utf8'));
const problems = diff(expected, actualFingerprint, 'doc');

console.log(`闸门 C：${expectedPath.split(/[\\/]/).pop()}（期望） vs ${target.split(/[\\/]/).pop()}（实际）`);
console.log(`  比对项：正文序列 + ${actualFingerprint.tables.length} 张表（含每格属性）+ `
    + `合并网格 + 嵌入图片（${actualFingerprint.media.length} 张）`);
console.log('  纯 JS 实现：web/app/report/fingerprint.js（与 Python 版同构）');

if (!problems.length) {
    console.log('结果：全部一致 ✅');
    process.exit(0);
}

console.log(`结果：不一致 ${problems.length} 处`);
for (const line of summarizeDiffs(problems, Number(option('--show', 20)))) console.log(`  ${line}`);
process.exit(1);
