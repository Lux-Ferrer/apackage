/* 尺寸结果与条文的文本规则。
 *
 * 与 `webapp/services/measurements.py` 的 normalize_size_result / resolve_requirement /
 * requirement_index_of / normalize_clause 一一对应。纯函数，无 IO。
 */

import { CONFIG } from './config.js';

export const SIZE_SEPARATORS = ['x', 'X', '*', '＊'];
export const SIZE_MULTIPLY = '×';

/** 两个数字之间只有空白 → 视作乘号（`63 164` → `63×164`）。 */
const TWO_NUMBERS = /^(\d+(?:\.\d+)?)[\s\u3000]+(\d+(?:\.\d+)?)$/;

/**
 * 规范化尺寸结果。
 *
 * - `x` / `X` / `*` / `＊` 统一成 `×`（`63x164` → `63×164`）；
 * - **两个数字之间只有空白**时把空白视作乘号（`63 164` → `63×164`）——
 *   这一条是 Python 侧的一个真 bug 修复：早期版本会把 `63 164` 粘成 `63164`；
 * - 其余空白去掉，因此 `12 + 75` 保留为 `12+75`（需求报告里的写法）。
 */
export function normalizeSizeResult(raw) {
    let text = clean(raw);
    if (!text) return null;

    for (const separator of SIZE_SEPARATORS) {
        text = text.split(separator).join(SIZE_MULTIPLY);
    }

    const pairs = TWO_NUMBERS.exec(text);
    if (pairs) return `${pairs[1]}${SIZE_MULTIPLY}${pairs[2]}`;

    return text.replace(/[ \u3000]/g, '') || null;
}

/** 下拉序号 → 条文文案（存快照）；空或越界返回 null（导出时显示「无」）。 */
export function resolveRequirement(indexRaw, templateType) {
    const options = CONFIG.REQUIREMENT_OPTIONS[templateType] ?? [];
    const text = clean(indexRaw);
    if (!text) return null;
    if (!/^-?\d+$/.test(text)) return null;
    const index = Number.parseInt(text, 10);
    return (index >= 0 && index < options.length) ? options[index] : null;
}

/** 反向匹配：编辑时用已存文案找回下拉选中项；匹配不到返回 null。 */
export function requirementIndexOf(requirementText, templateType) {
    const options = CONFIG.REQUIREMENT_OPTIONS[templateType] ?? [];
    const index = options.indexOf(requirementText);
    return index === -1 ? null : index;
}

/** 条文标点的全角 → 半角（只用于比较与追溯，不参与存储）。 */
const CLAUSE_PUNCTUATION = { '，': ',', '。': '.', '；': ';', '：': ':', '（': '(', '）': ')' };

/** 条文归一化：去空白、全角标点转半角、去首尾标点。 */
export function normalizeClause(text) {
    if (text === null || text === undefined) return '';
    let cleaned = String(text).replace(/\s+/g, '');
    for (const [full, half] of Object.entries(CLAUSE_PUNCTUATION)) {
        cleaned = cleaned.split(full).join(half);
    }
    return cleaned.replace(/^[.;,、]+|[.;,、]+$/g, '');
}

/** 显示文本：空值 → 「无」（对应 config.EMPTY_TEXT）。 */
export function displayText(value) {
    return clean(value) || CONFIG.EMPTY_TEXT;
}

/** 去空白；null/undefined → 空串（对应 Python 的 _clean）。 */
export function clean(value) {
    return value === null || value === undefined ? '' : String(value).trim();
}
