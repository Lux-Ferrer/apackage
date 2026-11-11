/* 检测记录：模板选择 / 新增 / 编辑。
 *
 * 标记与 `webapp/templates/records/*.html` 一致（class / name / id 全部照搬 ——
 * 这些是 UI 阶段冻结的契约，`ui/record-form.js` 与 CSS 都依赖它们）。
 *
 * 两处与 Flask 版**必须**保持一致、又最容易漏掉的语义：
 *  1. **模板类型不可切换**：编辑时页面上不出现任何切换控件（锁定的是数据，不是控件）；
 *  2. 「保留历史条文」哨兵 `__keep__`：数据层解析不出条文（它只认数字），
 *     要像 Flask 的 `routes/records.py` 那样**在解析之后**用已存文案覆盖回来。
 */

import { CONFIG } from '../config.js';
import { clean, requirementIndexOf } from '../clauses.js';
import { pathFor } from '../router.js';
import * as measurements from '../repo/measurements.js';
import * as projects from '../repo/projects.js';
import { h, link } from '../ui/dom.js';
import { flash } from '../ui/dialog.js';
import { applyFieldErrors, attachRecordForm, collectForm } from '../ui/record-form.js';
import { actionBar, backLink, card, formRow, pageHead, select } from './layout.js';
import { notFound } from './projects.js';

const KEEP_REQUIREMENT = '__keep__';       // 与 Flask 的 routes/records.py 同一个哨兵值

/* --------------------------------------------------------------------------
 * 模板选择
 * ------------------------------------------------------------------------ */

export async function choose(ctx) {
    const project = await projects.get(ctx.db, ctx.params.id);
    if (!project) return notFound('项目不存在');

    const choices = CONFIG.TEMPLATE_TYPES.map((templateType) => h('a.template-card', {
        href: pathFor('records.new', { id: project.id, template: templateType }),
    }, [
        h('h3', { text: CONFIG.TEMPLATE_NAMES[templateType] }),
        h('p.template-title', { text: CONFIG.TEMPLATE_TITLES[templateType] }),
        h('p.muted', { text: `建议检测面：${CONFIG.FACE_SUGGESTIONS[templateType].join('、')}` }),
        h('p.muted', { text: `截面尺寸要求条文：${CONFIG.REQUIREMENT_OPTIONS[templateType].length} 条` }),
        h('span.btn.small', { text: '选择' }),
    ]));

    return {
        chrome: 'form',
        nodes: [card([
            ...pageHead('选择检测记录模板',
                backLink(pathFor('projects.detail', { id: project.id }), '返回项目详情')),
            h('p.sub', { text: `项目：${project.house_name}（${project.project_no}）` }),
            h('div.template-choices', null, choices),
            h('p.hint', { text: '两类模板字段结构一致，仅名称与「截面尺寸要求」下拉选项不同；同一项目可混合录入。' }),
        ])],
    };
}

/* --------------------------------------------------------------------------
 * 新增 / 编辑
 * ------------------------------------------------------------------------ */

export async function form(ctx, { editing }) {
    // 一次读到位：原来这里读了两次（先取 template_type、再取 record），既浪费也容易走样
    const record = editing ? await measurements.getRecord(ctx.db, ctx.params.id) : null;
    const templateType = editing ? record?.template_type : ctx.params.template;
    if (!CONFIG.TEMPLATE_TYPES.includes(templateType)) {
        return notFound(editing ? '检测记录不存在' : `未知的模板类型：${templateType}`);
    }

    const project = await projects.get(ctx.db, editing ? record.project_id : ctx.params.id);
    if (!project) return notFound('项目不存在');

    // ⚠️ `getReadings()` 返回的是 **thickness_readings 的原始行**（字段是 `value_1..value_5`），
    // 而表单要的是已经格式化好的 `readings_text` —— 必须过一遍 `faceView()`。
    // 早先这里直接取 `row.readings_text`（undefined），于是 `readings[offset]` 立刻炸：
    // "Cannot read properties of undefined (reading '0')"（真机上点检测记录的「编辑」就崩溃）。
    const rows = editing
        ? (await measurements.getReadings(ctx.db, record.id)).map((raw) => {
            const view = measurements.faceView(raw);
            return { face: view.face, readings: view.readings_text };
        })
        : [{ face: '', readings: Array.from({ length: CONFIG.THICKNESS_VALUE_COUNT }, () => '') }];

    // 编辑时：能匹配到预置条文就选中它，匹配不到就走「历史条文」哨兵项（与 Flask 一致）
    let selected = null;
    let history = null;
    if (editing) {
        selected = requirementIndexOf(record.requirement_text, templateType);
        if (selected === null && clean(record.requirement_text)) history = record.requirement_text;
    }
    const selectedValue = selected !== null ? selected
        : (history ? KEEP_REQUIREMENT : '');

    const valueCount = CONFIG.THICKNESS_VALUE_COUNT;
    const faceMax = CONFIG.FACE_MAX_COUNT;

    const rowFactory = (index) => rowElement({ index, face: '', readings: [], valueCount, open: true, suggestions: CONFIG.FACE_SUGGESTIONS[templateType] });

    const list = h('ol.face-list', {
        id: 'face-list', dataset: { valueCount: String(valueCount), faceMax: String(faceMax) },
    }, rows.map((row, index) => rowElement({
        index, face: row.face, readings: row.readings, valueCount,
        open: editing ? false : index === 0,          // 新建：首行展开；编辑：全折叠（摘要行就是概览）
        suggestions: CONFIG.FACE_SUGGESTIONS[templateType],
    })));

    const requirementOptions = [
        { value: '', label: '（不填，报告中显示「无」）', selected: selectedValue === '' },
        ...CONFIG.REQUIREMENT_OPTIONS[templateType].map((label, index) => ({
            value: String(index), label, selected: selectedValue === index,
        })),
        ...(history ? [{
            value: KEEP_REQUIREMENT,
            label: `（历史条文，当前预置项中已无）${history}`,
            selected: selectedValue === KEEP_REQUIREMENT,
        }] : []),
    ];

    const formId = 'record-form';
    const form = h('form', { id: formId, novalidate: true }, [
        h('h2.section-title', { text: '构件信息' }),
        h('div.form-table', null, [
            formRow({
                label: '楼层', forId: 'floor', required: true,
                control: h('input', {
                    type: 'text', id: 'floor', name: 'floor', maxlength: 30,
                    autocomplete: 'off', placeholder: '如：六层', value: record?.floor ?? '',
                }),
            }),
            formRow({
                label: '构件位置', forId: 'member_position', required: true,
                control: h('input', {
                    type: 'text', id: 'member_position', name: 'member_position', maxlength: 30,
                    autocomplete: 'off', placeholder: '如：1', value: record?.member_position ?? '',
                }),
            }),
            formRow({
                label: '尺寸结果', forId: 'size_result',
                control: h('input', {
                    type: 'text', id: 'size_result', name: 'size_result', maxlength: 30,
                    autocomplete: 'off', placeholder: '如：63×164', value: record?.size_result ?? '',
                }),
                hint: '填 x 或 * 会自动转成 ×（如 63x164 → 63×164）',
            }),
            formRow({
                label: CONFIG.REQUIREMENT_LABELS[templateType], forId: 'requirement_index',
                block: true,
                control: [
                    select({ name: 'requirement_index', id: 'requirement_index', options: requirementOptions }),
                    // 条文很长，闭合态会被浏览器截断；把选中的全文显示在下方（JS 同步）
                    h('p.hint', { id: 'requirement-full', hidden: true }),
                ],
            }),
        ]),

        h('h2.section-title', null, [
            '厚度检测',
            h('span.muted', { text: `（每个检测面 ${valueCount} 个读数，最小值自动计算）` }),
        ]),
        list,
        h('div.table-actions', null, [
            h('button.btn.ghost.small', { type: 'button', id: 'add-face', text: '+ 添加检测面' }),
            h('span.hint', { id: 'face-hint', text: `最多 ${faceMax} 个检测面` }),
        ]),
        h('datalist', { id: 'face-suggestions' },
            CONFIG.FACE_SUGGESTIONS[templateType].map((value) => h('option', { value }))),
    ]);

    const cancelHref = pathFor('projects.detail', { id: project.id });
    const container = card([
        ...pageHead(editing ? '编辑检测记录' : '新增检测记录', backLink(cancelHref, '返回项目详情')),
        h('p.sub', { text: `项目：${project.house_name}（${project.project_no}）` }),
        h('div.template-badge', null, [
            h('span.label', { text: '模板' }),
            h('strong', { text: CONFIG.TEMPLATE_TITLES[templateType] }),
            editing ? h('span.muted', { text: '（模板类型不可切换）' }) : null,
        ]),
        form,
    ], 'form-card');

    // ⚠️ 交互层要能拿到 `#save-record`，而它在**操作条**里、不在卡片里（UI 设计 1.3）。
    // 所以这里把"卡片 + 操作条"包进一个 wrapper，并把 wrapper 当作 root 传进去 ——
    // 否则"禁用保存按钮"这条约定会静默失效（按钮根本不是 root 的后代）。
    const bar = actionBar({
        cancelHref, submitLabel: '保存', formId, statusId: 'form-status', submitId: 'save-record',
    });
    const root = h('div', null, [container, bar]);

    // 挂载交互（与 Flask 侧同一套 5 条约定）。
    // 注意：这里传入的是**尚未插进 document 的子树** —— record-form 只在自己的 root 里
    // 找元素、只注册事件，因此挂载顺序无关紧要（挂载后再 focus 才需要真实 DOM，
    // 而那只会发生在用户点「添加检测面」之后）。
    const attached = attachRecordForm(root, { valueCount, faceMax, rowFactory });

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        // 交互层已经拦截了非法读数；这里再挡一次（回车隐式提交也会走到这）
        if (attached && attached.scan() > 0) {
            attached.revealInvalid();
            return;
        }
        form.querySelectorAll('.field-error').forEach((element) => element.remove());
        form.querySelectorAll('.input-error').forEach((element) => element.classList.remove('input-error'));

        const payload = collectForm(form);
        const { data, errors } = measurements.parseRecordForm(payload, templateType);
        if (Object.keys(errors).length) {
            applyFieldErrors(root, errors);
            flash('有必填项或读数不合规，已标出问题所在', 'error');
            return;
        }
        // 「保留历史条文」：数据层只认数字，所以在这里覆盖回已存文案（同 Flask routes/records.py）
        if (payload.requirement_index === KEEP_REQUIREMENT && record) {
            data.requirement_text = record.requirement_text;
        }

        try {
            if (editing) await measurements.updateRecord(ctx.db, record.id, data);
            else await measurements.createRecord(ctx.db, project.id, templateType, data);
            flash(editing ? '检测记录已更新' : '检测记录已添加');
            // navigate 会触发一次渲染；**不要再调 refresh()** —— 那会并发两条渲染
            // （虽然 main.js 已经做了串行化，但没必要制造这种竞争）
            ctx.navigate(`#/projects/${project.id}`);
        } catch (error) {
            flash(`保存失败：${error.message}`, 'error');
        }
    });

    return {
        chrome: 'form',
        nodes: [root],
    };
}

/* --------------------------------------------------------------------------
 * 一行检测面（摘要行 + 下级编辑）
 *
 * 与 Flask 的 `records/form.html` 结构逐项对应。**摘要行是纯展示面**（不放输入框），
 * 所以不需要给 `<summary>` 加 preventDefault —— 这是选原生 `<details>` 换来的可靠性。
 * ------------------------------------------------------------------------ */

function rowElement({ index, face, readings, valueCount, open, suggestions }) {
    const values = Array.from({ length: valueCount }, (_v, offset) => readings[offset] ?? '');

    const summary = h('summary.face-summary', null, [
        h('span.face-dot.state-none', { 'aria-hidden': 'true' }),
        h('span.face-name', { text: face || '新检测面' }),
        h('span.face-count', { text: `0/${valueCount}` }),
        h('span.face-min', null, ['最小 ', h('b.min-value', { text: '—' })]),
        h('span.face-lamp', { hidden: true }, ['⚠ ', h('span.lamp-count', { text: '0' }), ' 格不是数字']),
    ]);

    const editor = h('div.face-editor', null, [
        h('label.face-field', null, [
            '检测面',
            h('input', {
                type: 'text', class: 'face-input', name: `face_${index}`,
                list: 'face-suggestions', maxlength: 10, autocomplete: 'off',
                value: face, placeholder: `如 ${suggestions[0]}`,
            }),
        ]),
        h('div.reading-grid', null, values.map((value, offset) => {
            const position = offset + 1;
            return h('label.reading-cell', null, [
                h('span.reading-label', { text: String(position) }),
                h('input', {
                    type: 'text', class: 'reading', name: `value_${index}_${position}`,
                    value, inputmode: 'decimal', autocomplete: 'off',
                    enterkeyhint: position === valueCount ? 'done' : 'next',
                    pattern: '-?(\\d+(\\.\\d*)?|\\.\\d+)',
                }),
                h('span.input-hint', { text: '请填数字' }),
            ]);
        })),
        h('div.face-editor-foot', null, [
            h('span.hint', { text: '最小值自动计算，不用手填' }),
            h('button.row-remove', { type: 'button', title: '删除这个检测面', text: '删除这个检测面' }),
        ]),
    ]);

    return h('li', null, h('details.face-row', {
        dataset: { index: String(index) }, open: open || null,
    }, [summary, editor]));
}
