/* M5-0 侦察原型：把 docx JS 库的输出打成"与对拍基线逐属性一致"。
 *
 * 状态：**原型，不是产品代码**。M5-2 的 `web/app/report/postprocess.js` 从这里长出来 ——
 * 6 个补丁的规格见 docs/management/M5-设计.md 1.4 节，本文件是它的可执行版本。
 *
 * 流程：生成最小样例 → JSZip 打 6 个补丁 → 落盘；
 *       再交给 tools/verify_docx_patches.py 用闸门自己的比较函数核对。
 *
 * 用法：
 *     node tools/js/prototype_postprocess.mjs                       # 写 _work/spike*.docx
 *     node tools/js/prototype_postprocess.mjs out.docx base.docx     # 自定义路径
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import JSZip from 'jszip';
import * as docx from 'docx';

const {
    Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
    WidthType, TableLayoutType, AlignmentType, HeightRule, BorderStyle, ImageRun,
} = docx;

/* 本项目的版式数值（真值在 webapp/resources/report_layout.json，原型里先写死） */
const SPEC = {
    page: { width: 11907, height: 16839, top: 1440, bottom: 1843, left: 907, right: 907,
            header: 850, footer: 964, linePitch: '312' },
    table: { width: 10833, align: 'center', layout: 'fixed', outerSz: 12, innerSz: 6,
             color: '000000', cellMarginLeft: 57, cellMarginRight: 57,
             look: { val: '0000', firstRow: '0', lastRow: '0', firstColumn: '0',
                     lastColumn: '0', noHBand: '0', noVBand: '0' } },
    columns: [1077, 850, 1416, 789, 790, 790, 789, 790, 790, 790, 1962],
    rows: { header: 567, data: 522 },
};

const OUT_SPIKE = process.argv[2] ?? '_work/spike.docx';
const BASE_TEMPLATE = process.argv[3] ?? 'webapp/resources/report_base.docx';
const OUT_PATCHED = OUT_SPIKE.replace(/\.docx$/, '_patched.docx');

const PNG_1PX = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==',
    'base64');

const mkdir = (file) => mkdirSync(dirname(file), { recursive: true });

/* ------------------------------------------------------------------ 生成 */
function buildSpike() {
    const cell = (text, extra = {}) => new TableCell({
        children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ text, bold: true, size: 20 })],
        })],
        verticalAlign: docx.VerticalAlignTable.CENTER,
        ...extra,
    });

    const table = new Table({
        columnWidths: SPEC.columns,
        width: { size: SPEC.table.width, type: WidthType.DXA },
        layout: TableLayoutType.FIXED,
        alignment: AlignmentType.CENTER,
        margins: { marginUnitType: WidthType.DXA, top: 0, bottom: 0,
                   left: SPEC.table.cellMarginLeft, right: SPEC.table.cellMarginRight },
        borders: {
            top: { style: BorderStyle.SINGLE, size: SPEC.table.outerSz, color: SPEC.table.color },
            bottom: { style: BorderStyle.SINGLE, size: SPEC.table.outerSz, color: SPEC.table.color },
            left: { style: BorderStyle.SINGLE, size: SPEC.table.outerSz, color: SPEC.table.color },
            right: { style: BorderStyle.SINGLE, size: SPEC.table.outerSz, color: SPEC.table.color },
            insideHorizontal: { style: BorderStyle.SINGLE, size: SPEC.table.innerSz, color: SPEC.table.color },
            insideVertical: { style: BorderStyle.SINGLE, size: SPEC.table.innerSz, color: SPEC.table.color },
        },
        tableLook: { firstRow: false, lastRow: false, firstColumn: false,
                     lastColumn: false, noHBand: false, noVBand: false },
        rows: [
            new TableRow({
                height: { value: SPEC.rows.header, rule: HeightRule.ATLEAST },
                children: [
                    cell('楼层'),
                    new TableCell({
                        verticalAlign: docx.VerticalAlignTable.CENTER,
                        children: [
                            new Paragraph({ alignment: AlignmentType.CENTER,
                                children: [new TextRun({ text: '检测构件', bold: true, size: 20 })] }),
                            new Paragraph({ alignment: AlignmentType.CENTER,
                                children: [new TextRun({ text: '位置', bold: true, size: 20 })] }),
                        ],
                    }),
                    cell('尺寸检测结果m×n'),
                    cell('厚度检测结果（mm）', { columnSpan: 7 }),
                    cell('立柱截面尺寸截面要求（mm）'),
                ],
            }),
            new TableRow({
                height: { value: SPEC.rows.data, rule: HeightRule.ATLEAST },
                children: [
                    cell('六层', { rowSpan: 2 }), cell('1'), cell('63×164'), cell('B'),
                    cell('2.99'), cell('2.98'), cell('2.97'), cell('2.96'), cell('2.95'),
                    cell('2.95'), cell('立柱铝型材开口部位…'),
                ],
            }),
            new TableRow({
                height: { value: SPEC.rows.data, rule: HeightRule.ATLEAST },
                children: [
                    cell('1'), cell('63×164'), cell('H'), cell('2.55'), cell('2.52'),
                    cell('2.53'), cell('2.53'), cell('2.52'), cell('2.52'),
                ],
            }),
        ],
    });

    return new Document({
        sections: [{
            properties: {
                page: {
                    size: { width: SPEC.page.width, height: SPEC.page.height },
                    margin: { top: SPEC.page.top, bottom: SPEC.page.bottom, left: SPEC.page.left,
                              right: SPEC.page.right, header: SPEC.page.header,
                              footer: SPEC.page.footer, gutter: 0 },
                },
            },
            children: [
                new Paragraph({
                    alignment: AlignmentType.CENTER,
                    spacing: { before: 300, after: 200 },
                    children: [new TextRun({ text: '幕墙立柱截面尺寸检测结果', bold: true, size: 32 })],
                }),
                table,
                new Paragraph({
                    children: [new ImageRun({
                        type: 'png', data: PNG_1PX,
                        /* twips → px（库只吃 96 DPI 像素）；1 px = 15 twips = 9525 EMU，
                           twips/15 让库算出的 EMU 恰好等于 twips × 635 */
                        transformation: { width: 8800 / 15, height: 8000 / 15 },
                    })],
                }),
            ],
        }],
    });
}

/* ---------------------------------------------------------------- 补丁 */
/* ① docGrid linePitch 360 → 312 */
const patchDocGrid = (xml) =>
    xml.replace(/(<w:docGrid[^>]*?)w:linePitch="\d+"/, `$1w:linePitch="${SPEC.page.linePitch}"`);

/* ② tblLook：补 val="0000"，并把布尔 false/true 归一成 0/1 */
const patchTableLook = (xml) =>
    xml.replace(/<w:tblLook\b[^>]*\/>/g, (tag) => {
        if (/\bw:val=/.test(tag)) return tag;
        const attrs = tag.replace(/^<w:tblLook\s*/, '').replace(/\/>$/, '')
            .replace(/([A-Za-z]+)="false"/g, '$1="0"')
            .replace(/([A-Za-z]+)="true"/g, '$1="1"');
        return `<w:tblLook w:val="${SPEC.table.look.val}" ${attrs}/>`;
    });

/* ③ trHeight：删掉 hRule（不写即"至少"，与基线一致） */
const patchRowHeight = (xml) =>
    xml.replace(/(<w:trHeight\b[^>]*?)\s+w:hRule="[^"]*"/g, '$1');

/* ④ tblCellMar：删掉 top / bottom（基线只写左右） */
const patchTableCellMargin = (xml) =>
    xml.replace(/<w:tblCellMar>(.*?)<\/w:tblCellMar>/gs,
        (_whole, inner) => `<w:tblCellMar>${inner.replace(/<w:(top|bottom)\b[^>]*\/>/g, '')}</w:tblCellMar>`);

/* ⑤ 续行格：补 vAlign（schema 序在 vMerge 之后 → 追加即合法）+ 空段落补 jc */
const patchContinuationCells = (xml) =>
    xml.replace(/<w:tc>(.*?)<\/w:tc>/gs, (whole, inner) => {
        const isContinuation = /<w:tcPr>/.test(inner)
            && /<w:vMerge\b(?![^>]*w:val="restart")/.test(inner);
        if (!isContinuation) return whole;
        let patched = inner;
        if (!/<w:vAlign\b/.test(patched)) {
            patched = patched.replace(/<\/w:tcPr>/, '<w:vAlign w:val="center"/></w:tcPr>');
        }
        patched = patched.replace(/<w:p\/>/g, '<w:p><w:pPr><w:jc w:val="center"/></w:pPr></w:p>');
        return `<w:tc>${patched}</w:tc>`;
    });

/* ⑥ styles.xml + theme1.xml：整份替换为底座模板里的（docDefaults 提供字体来源） */
async function replaceBaseParts(zip) {
    const baseZip = await JSZip.loadAsync(readFileSync(BASE_TEMPLATE));
    for (const part of ['word/styles.xml', 'word/theme/theme1.xml']) {
        const content = await baseZip.file(part)?.async('uint8array');
        if (content) {
            zip.file(part, content);
            console.log(`  ⑥ replaced ${part} (${content.length} bytes)`);
        } else {
            console.log(`  ⑥ MISSING in base template: ${part}`);
        }
    }
}

/* ---------------------------------------------------------------- 主流程 */
mkdir(OUT_SPIKE);
writeFileSync(OUT_SPIKE, await Packer.toBuffer(buildSpike()));
console.log('spike written      :', OUT_SPIKE);

const zip = await JSZip.loadAsync(readFileSync(OUT_SPIKE));
let xml = await zip.file('word/document.xml').async('string');
xml = patchDocGrid(xml);
console.log('  ① docGrid linePitch →', SPEC.page.linePitch);
xml = patchTableLook(xml);
console.log('  ② tblLook val=0000 + false→0');
xml = patchRowHeight(xml);
console.log('  ③ trHeight 删 hRule');
xml = patchTableCellMargin(xml);
console.log('  ④ tblCellMar 删 top/bottom');
xml = patchContinuationCells(xml);
console.log('  ⑤ 续行格补 vAlign + 空段落 jc');
zip.file('word/document.xml', xml);
await replaceBaseParts(zip);

mkdir(OUT_PATCHED);
writeFileSync(OUT_PATCHED, await zip.generateAsync({ type: 'nodebuffer', compression: 'DEFLATE' }));
console.log('patched written    :', OUT_PATCHED);
