/* 厚度读数计算：每个检测面 5 个读数 → 最小值。
 *
 * 与 `webapp/services/thickness.py` 一一对应。**最小值是派生值，不落库** ——
 * 展示与导出时现算，保证单一数据来源（这条原则在 M5 里不变）。
 */

/** 现场未测的点，表单/导入可能出现的空占位符（与 Python 的 _EMPTY_TOKENS 一致）。 */
export const EMPTY_TOKENS = new Set(['', '-', '/', '—', '－', 'null', 'none']);

export const VALUE_DIGITS = 2;

/**
 * 原始读数 → number 或 null（未填）；无法识别时抛错。
 *
 * 与 Python 的差异：Python 用异常表达"非法"，这里同样抛错（校验流程要用），
 * 另提供不抛错的 `readingState()` / `countReadings()` 给视图模型用。
 */
export function normalizeValue(raw) {
    if (raw === null || raw === undefined) return null;
    if (typeof raw === 'boolean') throw new Error(`厚度读数无法识别：${raw}`);
    if (typeof raw === 'number') {
        if (Number.isNaN(raw)) return null;
        return raw;
    }
    const text = String(raw).trim();
    if (EMPTY_TOKENS.has(text.toLowerCase())) return null;
    // 只接受完整数字（Python 的 float() 会拒掉 "1abc"，JS 的 Number() 也会 → NaN）
    const value = Number(text);
    if (!Number.isFinite(value)) throw new Error(`厚度读数无法识别：${raw}`);
    return value;
}

/** 一个检测面 5 个读数的最小值；全部未填返回 null。无法识别的值会抛错。 */
export function faceMin(values) {
    const numbers = [];
    for (const raw of values ?? []) {
        const value = normalizeValue(raw);
        if (value !== null) numbers.push(value);
    }
    return numbers.length ? Math.min(...numbers) : null;
}

/** 数值 → 定点小数字符串（默认两位）；null → 空串。 */
export function formatMm(value, digits = VALUE_DIGITS) {
    if (value === null || value === undefined) return '';
    return Number(value).toFixed(digits);
}

/** 一个检测面的最小值文本（直接用于表格"最小值"列）。 */
export function faceMinText(values, digits = VALUE_DIGITS) {
    return formatMm(faceMin(values), digits);
}

/**
 * 容错版最小值文本：**跳过**非法文本，只按有效读数算。
 *
 * 表单回填时用户可能留着非数字文本，那时要显示"其余有效值的最小值"并让警告灯提示，
 * 而不是抛异常把页面打空。校验流程仍旧走 `normalizeValue`（严格）。
 */
export function faceMinTextOfValid(values, digits = VALUE_DIGITS) {
    const numbers = [];
    for (const raw of values ?? []) {
        let value;
        try {
            value = normalizeValue(raw);
        } catch {
            continue;
        }
        if (value !== null) numbers.push(value);
    }
    return formatMm(numbers.length ? Math.min(...numbers) : null, digits);
}

/** 从 thickness_readings 行取出 value_1..value_5。 */
export function readingsOfRow(row) {
    return [1, 2, 3, 4, 5].map((i) => row[`value_${i}`]);
}

/* --------------------------------------------------------------------------
 * 读数状态（供表单视图模型用）—— 见 UI 设计 2.4/2.5：
 * 有效个数 → 三态着色（还剩多少活）；非法个数 → 警告灯（能不能保存）
 * ------------------------------------------------------------------------ */

/** 一个读数的状态：'empty' | 'valid' | 'invalid'。 */
export function readingState(raw) {
    try {
        return normalizeValue(raw) === null ? 'empty' : 'valid';
    } catch {
        return 'invalid';
    }
}

/** 返回 [有效个数, 非法个数]；空值不计入任何一边。 */
export function countReadings(values) {
    let valid = 0;
    let invalid = 0;
    for (const raw of values ?? []) {
        const state = readingState(raw);
        if (state === 'valid') valid += 1;
        else if (state === 'invalid') invalid += 1;
    }
    return [valid, invalid];
}
