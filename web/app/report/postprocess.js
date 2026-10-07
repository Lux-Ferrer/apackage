/* docx JS 库输出的后处理：把库写出来的 XML 补齐到与对拍基线**逐属性一致**。
 *
 * 这是 M5-0 侦察的产物落地（原型见 tools/js/prototype_postprocess.mjs，验证器见
 * tools/verify_docx_patches.py）。差异清单与理由写在 docs/management/M5-设计.md 1.4 节。
 *
 * 7 个补丁（前 6 个是 M5-0 验过的，第 7 个是 M5-2 写引擎时按基线 sectPr 发现的）：
 *   ① docGrid     库写 linePitch=360，基线是 312
 *   ② tblLook     库写 firstRow="false" 且无 w:val，基线是 val="0000" + 全 "0"
 *   ③ trHeight    库必写 hRule="atLeast"，基线不写（不写即"至少"）
 *   ④ tblCellMar  库补了 top/bottom=0，基线只写 left/right=57
 *   ⑤ 续行格      库生成的续格缺 vAlign 与段落 jc（表头续格还缺固定行距）
 *   ⑥ styles/theme 库的 docDefaults 是空的 → 整份替换为底座模板的
 *   ⑦ sectPr cols 库不写 <w:cols>，基线有 <w:cols w:space="720"/>
 *
 * ⚠️ 这些差异**都不属于 docx 库的公开 API 契约**（是它的内部实现细节）。
 * 升级 docx 后必须重跑：python tools/verify_docx_patches.py
 */

import JSZip from 'jszip';

import { SPEC } from './spec.js';

const W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';

/* --------------------------------------------------------------------------
 * ① docGrid：linePitch 改成规格值
 * ------------------------------------------------------------------------ */
export function patchDocGrid(xml, spec = SPEC) {
    const pitch = String(spec.page.docGridLinePitch);
    return xml.replace(/(<w:docGrid[^>]*?)w:linePitch="\d+"/, `$1w:linePitch="${pitch}"`);
}

/* --------------------------------------------------------------------------
 * ② tblLook：补 w:val，并把布尔 false/true 归一成 0/1
 * ------------------------------------------------------------------------ */
export function patchTableLook(xml, spec = SPEC) {
    const look = spec.table.look;
    return xml.replace(/<w:tblLook\b[^>]*\/>/g, (tag) => {
        if (/\bw:val=/.test(tag)) return tag;
        const attrs = tag
            .replace(/^<w:tblLook\s*/, '')
            .replace(/\/>$/, '')
            .replace(/([A-Za-z]+)="false"/g, '$1="0"')
            .replace(/([A-Za-z]+)="true"/g, '$1="1"');
        return `<w:tblLook w:val="${look.val}" ${attrs}/>`;
    });
}

/* --------------------------------------------------------------------------
 * ③ trHeight：删掉 hRule
 * ------------------------------------------------------------------------ */
export function patchRowHeight(xml) {
    return xml.replace(/(<w:trHeight\b[^>]*?)\s+w:hRule="[^"]*"/g, '$1');
}

/* --------------------------------------------------------------------------
 * ④ tblCellMar：只保留规格里声明的边
 * ------------------------------------------------------------------------ */
export function patchTableCellMargin(xml, spec = SPEC) {
    const keep = new Set(Object.keys(spec.table.tableCellMargin ?? {}));
    return xml.replace(/<w:tblCellMar>(.*?)<\/w:tblCellMar>/gs, (_whole, inner) => {
        const kept = inner.replace(/<w:(\w+)\b[^>]*\/>/g,
            (edge, side) => (keep.has(side) ? edge : ''));
        return `<w:tblCellMar>${kept}</w:tblCellMar>`;
    });
}

/* --------------------------------------------------------------------------
 * ⑤ 续行格：补 vAlign、把空段落补成居中；表头续格还要补固定行距
 *
 * 规格（来自 M5-0 侦察）：库对 rowSpan 生成的续格只写 tcW + vMerge，
 * 段落是裸的 <w:p/>；而基线要求 vAlign=center + 段落 jc=center，
 * 且表头若干续格带 spacing line=280 atLeast。
 * ------------------------------------------------------------------------ */
export function patchContinuationCells(xml, spec = SPEC) {
    const spacing = spec.cell.headerLineSpacing ?? {};
    const lineRule = spacing.lineRule ?? 'atLeast';
    const cellsForRow = [spacing.row0Cells ?? [], spacing.row1Cells ?? []];

    const patchTable = (tableXml) => {
        let rowIndex = -1;
        return tableXml.replace(/<w:tr\b[^>]*>.*?<\/w:tr>/gs, (rowXml) => {
            rowIndex += 1;
            let cellIndex = -1;
            return rowXml.replace(/<w:tc>.*?<\/w:tc>/gs, (cellXml) => {
                cellIndex += 1;
                const isContinuation = /<w:tcPr>/.test(cellXml)
                    && /<w:vMerge\b(?![^>]*w:val="restart")/.test(cellXml);
                if (!isContinuation) return cellXml;

                let patched = cellXml;
                if (!/<w:vAlign\b/.test(patched)) {
                    patched = patched.replace(/<\/w:tcPr>/, '<w:vAlign w:val="center"/></w:tcPr>');
                }

                const wantsLine = (cellsForRow[rowIndex] ?? []).includes(cellIndex);
                const paragraphProps = '<w:pPr>'
                    + (wantsLine && spacing.line
                        ? `<w:spacing w:line="${spacing.line}" w:lineRule="${lineRule}"/>` : '')
                    + '<w:jc w:val="center"/></w:pPr>';
                patched = patched.replace(/<w:p\/>/g, `<w:p>${paragraphProps}</w:p>`);
                return patched;
            });
        });
    };

    return xml.replace(/<w:tbl>.*?<\/w:tbl>/gs, patchTable);
}

/* --------------------------------------------------------------------------
 * ⑦ sectPr：基线有 <w:cols w:space="720"/>，库不写
 *    （schema 序里 cols 在 docGrid 之前，所以插在 docGrid 前面即合法）
 * ------------------------------------------------------------------------ */
export function patchSectionColumns(xml) {
    return xml.replace(/<w:sectPr\b[^>]*>.*?<\/w:sectPr>/gs, (sectXml) => {
        if (/<w:cols\b/.test(sectXml)) return sectXml;
        const cols = '<w:cols w:space="720"/>';
        if (/<w:docGrid\b/.test(sectXml)) {
            return sectXml.replace(/(<w:docGrid\b)/, `${cols}$1`);
        }
        return sectXml.replace(/<\/w:sectPr>/, `${cols}</w:sectPr>`);
    });
}

/* --------------------------------------------------------------------------
 * ⑧ pgSz：库会写 w:orient="portrait"，基线不写
 * ------------------------------------------------------------------------ */
export function patchPageSize(xml) {
    return xml.replace(/(<w:pgSz\b[^>]*?)\s+w:orient="[^"]*"/g, '$1');
}

/* --------------------------------------------------------------------------
 * ⑨ trPr：基线每行都有 <w:jc w:val="center"/>（行内居中），库不写
 *    schema 序里 jc 在 trHeight 之后 → 追加到 trPr 末尾即合法
 * ------------------------------------------------------------------------ */
export function patchRowAlignment(xml) {
    const TRPR = /<w:trPr\b[^>]*>[\s\S]*?<\/w:trPr>/;
    return xml.replace(/<w:tr\b[^>]*>[\s\S]*?<\/w:tr>/g, (rowXml) => {
        const trPr = TRPR.exec(rowXml);
        if (trPr) {
            // ⚠️ 只能在 **trPr 内部**找 jc —— 单元格段落里的 <w:jc> 也在同一段 XML 里，
            // 拿整行去测会误判成"已经有行内居中"而提前返回（这里踩过一次）。
            const inner = trPr[0].replace(/<\/w:trPr>$/, '');
            if (/<w:jc\b/.test(inner)) return rowXml;
            return rowXml.replace(trPr[0], `${inner}<w:jc w:val="center"/></w:trPr>`);
        }
        return rowXml.replace(/(<w:tr\b[^>]*>)/,
            '$1<w:trPr><w:jc w:val="center"/></w:trPr>');
    });
}

/* --------------------------------------------------------------------------
 * ⑩ tblBorders：基线每个边都带 w:space="0"，库不写
 * ------------------------------------------------------------------------ */
export function patchBorderSpacing(xml, spec = SPEC) {
    const space = spec.table.border.space ?? 0;
    return xml.replace(/<w:tblBorders>[\s\S]*?<\/w:tblBorders>/g, (borders) => borders.replace(
        /<w:(top|left|bottom|right|insideH|insideV)\b([^>]*?)\/>/g,
        (edge, _side, attrs) => (/\bw:space=/.test(attrs)
            ? edge
            : `<w:${_side}${attrs} w:space="${space}"/>`),
    ));
}

/* --------------------------------------------------------------------------
 * ⑪ vMerge：库写 <w:vMerge w:val="continue"/>，基线写 <w:vMerge/>（默认值即 continue）
 *
 * ⚠️ 这一处**必须补**：闸门的两个比较器严格度不同 ——
 *   `cell_fingerprint` 会做 `(val_of(...) or "continue")` 归一，看不出差别；
 *   但 `layout_grid`（合并网格检查）只认"无 val = 续格"，会把 `val="continue"`
 *   当成普通格 → 整张表的合并结构判错。语义等价也要写成一模一样。
 * ------------------------------------------------------------------------ */
export function patchVerticalMergeValue(xml) {
    return xml.replace(/<w:vMerge\b[^>]*\/>/g, (tag) => (
        /\bw:val="continue"/.test(tag) ? tag.replace(/\s*w:val="continue"/, '') : tag
    ));
}

/** 对 word/document.xml 施加全部补丁（①~⑤、⑦~⑪）。 */
export function patchDocumentXml(xml, spec = SPEC) {
    let patched = patchDocGrid(xml, spec);
    patched = patchTableLook(patched, spec);
    patched = patchRowHeight(patched);
    patched = patchTableCellMargin(patched, spec);
    patched = patchContinuationCells(patched, spec);
    patched = patchVerticalMergeValue(patched);
    patched = patchSectionColumns(patched);
    patched = patchPageSize(patched);
    patched = patchRowAlignment(patched);
    patched = patchBorderSpacing(patched, spec);
    return patched;
}

/* --------------------------------------------------------------------------
 * ⑥ styles.xml + theme1.xml：整份替换为底座模板的
 *    （语义等价于 Python 侧"从 report_base.docx 派生"）
 * ------------------------------------------------------------------------ */
export async function replaceBaseParts(zip, baseDocxBytes) {
    if (!baseDocxBytes) return [];
    const baseZip = await JSZip.loadAsync(baseDocxBytes);
    const replaced = [];
    for (const part of ['word/styles.xml', 'word/theme/theme1.xml']) {
        const entry = baseZip.file(part);
        if (!entry) continue;
        zip.file(part, await entry.async('uint8array'));
        replaced.push(part);
    }
    return replaced;
}

/**
 * 完整后处理：入 docx 字节，出补齐后的 docx 字节。
 *
 * @param {Uint8Array} docxBytes       库生成的 docx
 * @param {{baseDocxBytes?: Uint8Array, spec?: object}} [options]
 *        `baseDocxBytes` 是底座模板（提供 styles.xml / theme1.xml），浏览器端 fetch、Node 端读文件
 */
export async function postprocess(docxBytes, options = {}) {
    const spec = options.spec ?? SPEC;
    const zip = await JSZip.loadAsync(docxBytes);

    const documentXml = await zip.file('word/document.xml').async('string');
    zip.file('word/document.xml', patchDocumentXml(documentXml, spec));
    const replaced = await replaceBaseParts(zip, options.baseDocxBytes);

    return {
        bytes: await zip.generateAsync({ type: 'uint8array', compression: 'DEFLATE' }),
        replacedParts: replaced,
    };
}

export { W };
