/* 文档指纹 + 差异比较 —— **与 Python 版同构**，用来做闸门 C（不借助 Python 的自检）。
 *
 * 为什么要有它
 * ------------
 * 闸门 A/B 都靠 `tools/compare_report_with_sample.py`（Python）。那意味着：
 *   - 没有 Python 的环境（PWA 自身、只有 Node 的 CI 步骤）无法自检；
 *   - 也就无法让"用户在手机上导出后自己验一下"成为可能。
 * 所以这里把**同一套指纹与差异逻辑**用 JS 再实现一遍，比对对象是语言中立的
 * `tests/fixtures/generated_baseline.fingerprint.json`（由 `--fingerprint` 生成）。
 *
 * 一条纪律：**这个文件不允许"比 Python 宽松"**。
 * 它比 Python 版少比一项，闸门 C 就会安静地放过真问题 —— 那就是这个项目反复吃过的亏
 * （见 M5 设计 §0.1：闸门绿了先问"这个属性到底有没有被比"）。
 * `web/tests/fingerprint.test.mjs` 里有一组"故意改坏 → 必须被抓到"的对照。
 *
 * 环境无关：XML 解析器是**注入**的（浏览器用原生 `DOMParser`，Node 用 jsdom 的），
 * 于是同一份代码在产品里和在测试里跑的是同一个实现。
 */

import { parseImageSize } from './image-size.js';
import { orientedDimensions, parseJpegOrientation } from '../image-pipeline.js';

export const NS_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';
export const NS_WP = 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing';

/* --------------------------------------------------------------------------
 * DOM 小工具（与 Python 的 lxml 用法一一对应）
 * ------------------------------------------------------------------------ */

/** 直接子元素里指定 localName 的那些（对应 lxml 的 `findall(W+tag)`）。 */
function childrenNamed(element, localName) {
    if (!element) return [];
    return Array.from(element.children ?? []).filter((child) => child.localName === localName);
}

/** 第一个直接子元素（对应 `find(W+tag)`）。 */
function child(element, localName) {
    return childrenNamed(element, localName)[0] ?? null;
}

/** 全部后代（对应 `iter(W+tag)`）。 */
function descendants(element, namespace, localName) {
    if (!element) return [];
    return Array.from(element.getElementsByTagNameNS(namespace, localName));
}

/** 属性 → `{localName: value}`（对应 Python 的 `attr_map`）。 */
export function attrMap(element) {
    if (!element) return {};
    const map = {};
    for (const attribute of Array.from(element.attributes ?? [])) {
        map[attribute.localName] = attribute.value;
    }
    return map;
}

/** 取 `w:<name>` 属性；不存在返回 null（对应 Python 的 `val_of`）。 */
export function valOf(element, name = 'val') {
    if (!element) return null;
    return element.getAttributeNS(NS_W, name);
}

/** 段落/单元格里的全部文本（对应 `text_of`）。 */
export function textOf(element) {
    return descendants(element, NS_W, 't').map((node) => node.textContent ?? '').join('');
}

/* --------------------------------------------------------------------------
 * run 的属性集合
 * ------------------------------------------------------------------------ */

/**
 * Python 的 `repr()` 对 (bool, str|None, str|None) 的输出。
 *
 * 为什么要在 JS 里模拟它：Python 侧按 `key=repr` 排序，
 * 而**顺序会被写进冻结的指纹 JSON**，逐元素比较时顺序不同就是差异。
 * 我们的值只可能是布尔、数字串、字体名、None —— 都不含引号，所以单引号足够。
 */
function pyReprTuple([bold, size, eastAsia]) {
    const item = (value) => (value === null ? 'None' : `'${value}'`);
    return `(${bold ? 'True' : 'False'}, ${item(size)}, ${item(eastAsia)})`;
}

/**
 * run 的属性集合（去重后按 Python 的 repr 排序）。
 * 比较时**忽略 run 的切分方式** —— 样例把长条文按字界拆成多个 run，我们写一个 run，
 * 渲染完全相同，所以只比"出现过哪些属性组合"。
 */
export function runProps(paragraph) {
    const seen = new Map();
    // ⚠️ 只取**直接子元素**里的 run（对应 lxml 的 findall）：
    // 嵌在超链接/域里的 run 不参与，这一点必须与 Python 保持一致
    for (const run of childrenNamed(paragraph, 'r')) {
        const rpr = child(run, 'rPr');
        const tuple = rpr === null
            ? [false, null, null]
            : [
                child(rpr, 'b') !== null,
                valOf(child(rpr, 'sz')),
                (() => {
                    const fonts = child(rpr, 'rFonts');
                    return fonts === null ? null : fonts.getAttributeNS(NS_W, 'eastAsia');
                })(),
            ];
        seen.set(pyReprTuple(tuple), tuple);
    }
    return Array.from(seen.keys()).sort().map((key) => seen.get(key));
}

/* --------------------------------------------------------------------------
 * 段落 / 单元格 / 行 / 表格 / 分节
 * ------------------------------------------------------------------------ */

/** 段落里嵌入图片的显示尺寸（EMU 对）。**不比** `r:embed` —— 关系 id 两边分配方式不同。 */
export function paragraphImages(paragraph) {
    const found = [];
    for (const drawing of descendants(paragraph, NS_W, 'drawing')) {
        const extent = descendants(drawing, NS_WP, 'extent')[0] ?? null;
        if (!extent) continue;
        found.push([
            Number.parseInt(extent.getAttribute('cx') || '0', 10),
            Number.parseInt(extent.getAttribute('cy') || '0', 10),
        ]);
    }
    return found;
}

export function paragraphFingerprint(paragraph) {
    const ppr = child(paragraph, 'pPr');
    return {
        text: textOf(paragraph),
        jc: valOf(ppr ? child(ppr, 'jc') : null),
        spacing: attrMap(ppr ? child(ppr, 'spacing') : null),
        run_props: runProps(paragraph),
        images: paragraphImages(paragraph),
    };
}

export function cellFingerprint(tc) {
    const tcpr = child(tc, 'tcPr');
    const tcmar = tcpr ? child(tcpr, 'tcMar') : null;
    const vmerge = tcpr ? child(tcpr, 'vMerge') : null;
    return {
        tcW: tcpr ? attrMap(child(tcpr, 'tcW')) : {},
        gridSpan: tcpr ? valOf(child(tcpr, 'gridSpan')) : null,
        vMerge: vmerge ? (valOf(vmerge) || 'continue') : null,
        tcMar: tcmar
            ? Object.fromEntries(Array.from(tcmar.children)
                .map((edge) => [edge.localName, edge.getAttributeNS(NS_W, 'w')]))
            : null,
        vAlign: tcpr ? valOf(child(tcpr, 'vAlign')) : null,
        paragraphs: childrenNamed(tc, 'p').map(paragraphFingerprint),
    };
}

export function rowFingerprint(tr) {
    const trpr = child(tr, 'trPr');
    const height = trpr ? child(trpr, 'trHeight') : null;
    return {
        trHeight: height
            ? [height.getAttributeNS(NS_W, 'val'), height.getAttributeNS(NS_W, 'hRule')]
            : null,
        jc: trpr ? valOf(child(trpr, 'jc')) : null,
        cells: childrenNamed(tr, 'tc').map(cellFingerprint),
    };
}

export function tableFingerprint(tbl) {
    const tblpr = child(tbl, 'tblPr');
    const borders = tblpr ? child(tblpr, 'tblBorders') : null;
    const cellmar = tblpr ? child(tblpr, 'tblCellMar') : null;
    const grid = child(tbl, 'tblGrid');
    return {
        tblW: attrMap(tblpr ? child(tblpr, 'tblW') : null),
        jc: valOf(tblpr ? child(tblpr, 'jc') : null),
        tblLayout: attrMap(tblpr ? child(tblpr, 'tblLayout') : null),
        tblBorders: borders
            ? Object.fromEntries(Array.from(borders.children)
                .map((edge) => [edge.localName, attrMap(edge)]))
            : null,
        tblCellMar: cellmar
            ? Object.fromEntries(Array.from(cellmar.children)
                .map((edge) => [edge.localName, attrMap(edge)]))
            : null,
        tblLook: attrMap(tblpr ? child(tblpr, 'tblLook') : null),
        grid: grid
            ? childrenNamed(grid, 'gridCol')
                .map((col) => Number.parseInt(col.getAttributeNS(NS_W, 'w'), 10))
            : [],
        rows: childrenNamed(tbl, 'tr').map(rowFingerprint),
    };
}

export function sectionFingerprint(sectpr) {
    return {
        pgSz: attrMap(child(sectpr, 'pgSz')),
        pgMar: attrMap(child(sectpr, 'pgMar')),
        cols: attrMap(child(sectpr, 'cols')),
        docGrid: attrMap(child(sectpr, 'docGrid')),
    };
}

/* --------------------------------------------------------------------------
 * 媒体：像素尺寸多重集
 * ------------------------------------------------------------------------ */

/**
 * 文档里嵌入图片的像素尺寸（按 EXIF 摆正，排序后按多重集比较）。
 *
 * 这一项才抓得住"显示尺寸对、但嵌的是另一张图"。
 * 按多重集比较，所以 `image1.jpg` / `image2.jpg` 这种部件编号差异不会造成假差异。
 *
 * @param {Array<{name: string, bytes: Uint8Array}>} media
 */
export function mediaSizes(media = []) {
    const sizes = [];
    for (const entry of media) {
        const size = parseImageSize(entry.bytes);
        if (!size) continue;                       // 认不出的部件：Python 会抛错，这里跳过
        const orientation = size.type === 'jpeg'
            ? (parseJpegOrientation(entry.bytes) ?? 1)
            : 1;
        sizes.push(orientedDimensions(size.width, size.height, orientation));
    }
    return sizes.sort((a, b) => (a[0] - b[0]) || (a[1] - b[1]));
}

/* --------------------------------------------------------------------------
 * 整份文档
 * ------------------------------------------------------------------------ */

/**
 * 计算整份文档的指纹。
 *
 * @param {object} input
 *   documentXml   `word/document.xml` 的文本
 *   media         `[{name, bytes}]`，来自 docx 的 `word/media/*`（可省略 → 空）
 * @param {object} options
 *   DOMParserImpl XML 解析器构造函数（浏览器原生 / Node 里注入 jsdom 的）
 * @returns {{children: Array, tables: Array, media: Array}}
 */
export function fingerprintDocument(input, options = {}) {
    const ParserImpl = options.DOMParserImpl ?? globalThis.DOMParser;
    if (typeof ParserImpl !== 'function') {
        throw new Error('缺少 XML 解析器：请传入 options.DOMParserImpl（Node 里用 jsdom 的 DOMParser）');
    }
    const document = new ParserImpl().parseFromString(input.documentXml, 'application/xml');
    const parseError = document.getElementsByTagName('parsererror')[0];
    if (parseError) throw new Error(`document.xml 解析失败：${parseError.textContent.slice(0, 120)}`);

    const body = document.getElementsByTagNameNS(NS_W, 'body')[0];
    if (!body) throw new Error('document.xml 里没有 w:body');

    const children = [];
    const tables = [];
    for (const node of Array.from(body.children)) {
        if (node.localName === 'p') {
            children.push({ type: 'p', ...paragraphFingerprint(node) });
        } else if (node.localName === 'tbl') {
            children.push({ type: 'tbl', index: tables.length });
            tables.push(tableFingerprint(node));
        } else if (node.localName === 'sectPr') {
            children.push({ type: 'sectPr', ...sectionFingerprint(node) });
        }
    }
    return { children, tables, media: mediaSizes(input.media ?? []) };
}

/* --------------------------------------------------------------------------
 * 差异
 * ------------------------------------------------------------------------ */

/** 递归比较两个指纹，返回 `[{path, expected, actual}]`（对应 Python 的 `diff`）。 */
export function diff(expected, actual, path = '', found = null) {
    const problems = found ?? [];
    const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);

    if (isObject(expected) && isObject(actual)) {
        const keys = Array.from(new Set([...Object.keys(expected), ...Object.keys(actual)])).sort();
        for (const key of keys) {
            diff(expected[key], actual[key], `${path}.${key}`, problems);
        }
    } else if (Array.isArray(expected) && Array.isArray(actual)) {
        if (expected.length !== actual.length) {
            problems.push({ path: `${path}.length`, expected: expected.length, actual: actual.length });
        }
        for (let index = 0; index < Math.min(expected.length, actual.length); index += 1) {
            diff(expected[index], actual[index], `${path}[${index}]`, problems);
        }
    } else if (!sameValue(expected, actual)) {
        problems.push({ path, expected, actual });
    }
    return problems;
}

/** 严格相等（`null`/`undefined` 都按"没有"处理，与 Python 的 None 对齐）。 */
function sameValue(one, two) {
    if (one === two) return true;
    if ((one === null || one === undefined) && (two === null || two === undefined)) return true;
    return false;
}

/** 「前 N 条 + 其余多少条」的短摘要，供 CLI 与错误页显示。 */
export function summarizeDiffs(problems, limit = 8) {
    const lines = problems.slice(0, limit).map((item) => (
        `${item.path}  期望=${short(item.expected)}  实际=${short(item.actual)}`));
    if (problems.length > limit) lines.push(`…（其余 ${problems.length - limit} 处略）`);
    return lines;
}

function short(value) {
    const text = JSON.stringify(value);
    return text === undefined ? 'undefined' : (text.length > 40 ? `${text.slice(0, 40)}…` : text);
}
