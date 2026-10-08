/* 项目：列表 / 新建 / 编辑 / 详情。
 *
 * 标记结构对应 `webapp/templates/projects/*.html`，一处一处照搬（class 名保持一致，
 * 因为 CSS 是同一份 —— 见 tools/export_web_assets.py 生成 web/styles/app.css）。
 * 不同的是**数据来源**：Jinja 从服务端上下文取，这里从 `repo/projects.js` 取。
 */

import { CONFIG } from '../config.js';
import { pathFor } from '../router.js';
import * as defects from '../repo/defects.js';
import * as measurements from '../repo/measurements.js';
import * as projects from '../repo/projects.js';
import { badge, definitions, h, link } from '../ui/dom.js';
import { confirmDialog, flash } from '../ui/dialog.js';
import { backLink, card, formRow, input, pageHead } from './layout.js';

/* --------------------------------------------------------------------------
 * 列表
 * ------------------------------------------------------------------------ */

export async function index(ctx) {
    const rows = await projects.listWithCounts(ctx.db);
    const newButton = h('a.btn', { href: pathFor('projects.new'), text: '+ 新建项目' });

    const body = rows.length
        ? h('ul.report-list.project-list', null, rows.map((project) => card_(ctx, project)))
        : [
            h('p.hint', { text: '还没有项目。' }),
            h('p', null, h('a.btn', { href: pathFor('projects.new'), text: '新建第一个项目' })),
        ];

    return { nodes: [card([pageHead('项目', newButton), body])] };
}

function card_(ctx, project) {
    const detailHref = pathFor('projects.detail', { id: project.id });
    return h('li.report-card', null, [
        h('div.report-body', null, [
            h('div.report-title', null, [
                h('a.link.strong', { href: detailHref, text: project.house_name }),
                badge(project.project_no, 'todo'),
            ]),
            h('p.report-meta.muted', {
                text: `${project.house_address || '地点未填'}${project.test_date ? ` · ${project.test_date}` : ''}`,
            }),
            h('p.report-meta.muted', {
                text: `立柱 ${project.column_count} · 横梁 ${project.beam_count}`,
            }),
        ]),
        h('div.report-actions', null, [
            link(detailHref, '详情'),
            link(pathFor('projects.edit', { id: project.id }), '编辑'),
            deleteButton(ctx, project, { className: 'link danger-link', label: '删除' }),
        ]),
    ]);
}

/** 删除按钮：**先弹应用内确认（文案写明影响面），确认后才真的删**。 */
function deleteButton(ctx, project, { className, label }) {
    const button = h('button', { type: 'button', class: className, text: label });
    button.addEventListener('click', async () => {
        const impact = await projects.deleteImpact(ctx.db, project.id);
        const ok = await confirmDialog({
            message: projects.buildDeleteMessage(project, impact),
            okText: '确认删除',
        });
        if (!ok) return;
        // 先删记录、再删项目、缺陷报告解绑 —— 全在一个事务里（repo 层保证）
        const removed = await projects.remove(ctx.db, project.id);
        flash(`已删除项目「${project.house_name}」，同时删除 ${removed.records} 条检测记录`);
        ctx.navigate(pathFor('projects.index'), { replace: true });
    });
    return button;
}

/* --------------------------------------------------------------------------
 * 新建 / 编辑
 * ------------------------------------------------------------------------ */

export async function form(ctx, { editing }) {
    const project = editing ? await projects.get(ctx.db, ctx.params.id) : null;
    if (editing && !project) return notFound('项目不存在');

    const formId = 'project-form';
    const values = project ?? {};

    const fields = [
        ['project_no', '项目编号', { required: true, maxlength: 50, placeholder: '如：JCZG' }],
        ['house_name', '房屋名称', { required: true, maxlength: 100, placeholder: '如：金骐智谷' }],
        ['house_address', '房屋地点', { maxlength: 200, placeholder: '如：深圳市南山区' }],
        ['client_org', '委托单位', { maxlength: 100, placeholder: '如：中冶' }],
        ['test_date', '检测日期', { type: 'date' }],
    ];

    const form = h('form', { id: formId, novalidate: true },
        h('div.form-table', null, fields.map(([name, label, extra]) => formRow({
            label,
            forId: name,
            required: extra.required,
            control: input({ name, value: values[name] ?? '', ...extra }),
        }))));

    const cancelHref = editing
        ? pathFor('projects.detail', { id: project.id })
        : pathFor('projects.index');

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        clearErrors(form);
        const payload = collect(form, fields.map(([name]) => name));
        const { data, errors } = projects.parseForm(payload);
        if (Object.keys(errors).length) return showErrors(form, errors);

        try {
            if (editing) {
                await projects.update(ctx.db, project.id, data);
                flash('项目已更新');
                ctx.navigate(pathFor('projects.detail', { id: project.id }));
            } else {
                const created = await projects.create(ctx.db, data);
                flash('项目已创建');
                ctx.navigate(pathFor('projects.detail', { id: created.id ?? created }));
            }
        } catch (error) {
            // 唯一约束（项目编号重复）在数据层翻译成 IntegrityError
            showErrors(form, { project_no: error.message });
        }
    });

    return {
        nodes: [
            card([
                ...pageHead(editing ? '编辑项目' : '新建项目', backLink(cancelHref, '返回')),
                form,
            ], 'form-card'),
            h('div.action-bar', null, [
                h('span.action-spacer'),
                link(cancelHref, '取消'),
                h('button', { type: 'submit', form: formId, text: '保存' }),
            ]),
        ],
        chrome: 'form',
    };
}

/* --------------------------------------------------------------------------
 * 详情
 * ------------------------------------------------------------------------ */

export async function detail(ctx) {
    const project = await projects.get(ctx.db, ctx.params.id);
    if (!project) return notFound('项目不存在');

    const [groups, defectCount, related] = await Promise.all([
        measurements.groupedByTemplate(ctx.db, project.id),
        defects.countForProject(ctx.db, project.id),
        defects.listForProject(ctx.db, project.id),
    ]);
    const countsText = measurements.describeCounts(Object.fromEntries(
        groups.map((group) => [group.template_type, group.count])));

    return {
        nodes: [
            card([
                h('p.back-link', null, link(pathFor('projects.index'), '← 返回项目列表')),
                ...pageHead(`${project.house_name} `, h('div.head-actions', null, [
                    ...exportButtons(ctx, project, defectCount),
                    h('a.btn.ghost.small', { href: pathFor('projects.edit', { id: project.id }), text: '编辑项目' }),
                    deleteButton(ctx, project, { className: 'btn danger small', label: '删除项目' }),
                ]), { subtitle: null }),
                definitions([
                    ['项目编号', project.project_no],
                    ['房屋名称', project.house_name],
                    ['房屋地点', project.house_address || '—'],
                    ['委托单位', project.client_org || '—'],
                    ['检测日期', project.test_date || '—'],
                ]),
            ]),
            card([
                ...pageHead(h('span', { text: `检测记录 ` }), h('a.btn.small', {
                    href: pathFor('records.choose', { id: project.id }), text: '+ 添加检测记录',
                }), { level: 2 }),
                h('p.hint', { text: countsText }),
                groups.map((group) => recordGroup(ctx, group, project)),
            ]),
            card([
                h('h2', null, [h('span', { text: '关联缺陷报告 ' }),
                    h('span.muted', { text: `（${defectCount} 份）` })]),
                defectCount ? [
                    h('div.table-scroll', null, h('table.grid', null, [
                        h('thead', null, h('tr', null, [
                            h('th', { text: '缺陷类型' }), h('th', { text: '隐患等级' }),
                            h('th', { text: '工程部位' }), h('th', { text: '提交时间' }),
                            h('th.right', { text: '操作' }),
                        ])),
                        h('tbody', null, related.map((row) => h('tr', null, [
                            h('td', null, [row.defect_type, row.image_path
                                ? h('span.clip', { title: '附页含隐患图片', text: '📎' }) : null]),
                            h('td', null, badge(row.risk_level, CONFIG.RISK_BADGE_CLASSES[row.risk_level])),
                            h('td', { text: row.project_part }),
                            h('td.muted', { text: defects.formatReportTime(row.created_at) }),
                            h('td.right.nowrap', null, link(pathFor('reports.detail', { id: row.id }), '查看')),
                        ]))),
                    ])),
                    h('p.hint', { text: `导出时选择「附加 ${defectCount} 份并导出」，这些报告会作为附页追加在正文之后（每份独立成页）。` }),
                ] : h('p.hint', null, [
                    '暂无关联报告。在',
                    link(pathFor('reports.new'), '缺陷检测填报'),
                    '里选择「绑定项目」即可关联。',
                ]),
            ]),
        ],
    };
}

/** 导出按钮组：有关联报告时二选一（需求 4.1），没有时只有一个「导出 Word」。 */
function exportButtons(ctx, project, defectCount) {
    const buttons = [];
    const make = (label, withAttachments, className) => {
        const button = h('button', { type: 'button', class: className, text: label });
        button.addEventListener('click', async () => {
            button.disabled = true;
            const original = label;
            button.textContent = '生成中…';
            try {
                // 动态 import：docx 库有 1.3MB，不该拖慢首屏（只有点导出时才需要它）
                const { exportProject } = await import('../export.js');
                const result = await exportProject(ctx.db, project.id, {
                    withAttachments,
                    baseDocxBytes: await ctx.baseDocxBytes(),
                    pipeline: ctx.pipeline,          // 测试注入的编解码器（浏览器里是 undefined）
                    onProgress: (stage) => { button.textContent = `${stage}…`; },
                });
                flash(`已导出 ${result.filename}（${result.recordCount} 条记录`
                    + `${result.attachmentCount ? ` + ${result.attachmentCount} 份附页` : ''}）`);
            } catch (error) {
                flash(`导出失败：${error.message}`, 'error');
            } finally {
                button.disabled = false;
                button.textContent = original;
            }
        });
        return button;
    };

    if (defectCount) {
        buttons.push(make(`附加 ${defectCount} 份并导出`, true, 'btn small'));
        buttons.push(make('仅导出检测报告', false, 'btn ghost small'));
    } else {
        buttons.push(make('导出 Word', false, 'btn small'));
    }
    return buttons;
}

/** 一个模板分组（立柱 / 横梁）：每条记录一个可展开的 `<details>`。 */
function recordGroup(ctx, group, project) {
    const rows = group.records.map((item) => h('details.record', {
        id: `record-${item.record.id}`,
    }, [
        h('summary', null, [
            h('span.rec-title', { text: `${item.record.floor} · 构件 ${item.record.member_position}` }),
            h('span.rec-meta', {
                text: `${item.record.size_result || '尺寸未填'} · ${item.faces.length} 个面`
                    + `（${item.faces.map((face) => face.face).join('/')}）`,
            }),
        ]),
        h('div.record-body', null, [
            h('div.record-actions-bar', null, [
                link(pathFor('records.edit', { id: item.record.id }), '编辑'),
                deleteRecordButton(ctx, item.record, project),
            ]),
            h('div.table-scroll', null, h('table.data-table', null, [
                h('thead', null, h('tr', null, [
                    h('th.col-face', { text: '检测面' }),
                    ...Array.from({ length: CONFIG.THICKNESS_VALUE_COUNT }, (_v, index) => h('th', { text: index + 1 })),
                    h('th.col-min', { text: '最小值' }),
                ])),
                h('tbody', null, item.faces.length
                    ? item.faces.map((face) => h('tr', null, [
                        h('td.col-face', { text: face.face }),
                        ...face.readings_text.map((value) => h('td', { text: value || '—' })),
                        h('td.col-min', { text: face.min_text || '—' }),
                    ]))
                    : h('tr', null, h('td.muted', {
                        colspan: CONFIG.THICKNESS_VALUE_COUNT + 2,
                        text: '这条记录还没有检测面数据',
                    }))),
            ])),
            h('p.requirement', null, [
                h('span.label', { text: `${group.requirement_label}：` }),
                item.record.requirement_text || '无',
            ]),
        ]),
    ]));

    return h('section.record-group', null, [
        h('h3.group-title', null, [
            group.short_name,
            h('span.muted', { text: `（${group.title}，${group.count} 条）` }),
        ]),
        group.records.length ? rows : h('p.hint', { text: `还没有${group.short_name}记录。` }),
    ]);
}

function deleteRecordButton(ctx, record, project) {
    const button = h('button', { type: 'button', class: 'link danger-link', text: '删除' });
    button.addEventListener('click', async () => {
        const ok = await confirmDialog({
            message: `确认删除这条检测记录（${record.floor} · 构件 ${record.member_position}）？此操作不可恢复。`,
            okText: '确认删除',
        });
        if (!ok) return;
        await measurements.deleteRecord(ctx.db, record.id);
        flash('检测记录已删除');
        ctx.refresh();
    });
    return button;
}

/* --------------------------------------------------------------------------
 * 404
 * ------------------------------------------------------------------------ */

export function notFound(message) {
    return {
        nodes: [card([
            h('h1', { text: '没有这个页面' }),
            h('p.sub', { text: message }),
            h('p', null, link(pathFor('projects.index'), '← 回到项目列表')),
        ])],
        status: 404,
    };
}

/* --------------------------------------------------------------------------
 * 表单错误显示（与 Flask 的"服务端校验失败回填"同语义：标红 + 就地提示）
 * ------------------------------------------------------------------------ */

function showErrors(form, errors) {
    for (const [name, message] of Object.entries(errors)) {
        const field = form.querySelector(`[name="${name}"]`);
        if (!field) continue;
        field.classList.add('input-error');
        const holder = field.closest('.form-control') ?? field.parentNode;
        let box = holder.querySelector('.field-error');
        if (!box) {
            box = h('p.field-error');
            holder.appendChild(box);
        }
        box.textContent = message;
    }
    const first = form.querySelector('.input-error');
    if (first) first.focus();
    return errors;
}

function clearErrors(form) {
    form.querySelectorAll('.input-error').forEach((element) => element.classList.remove('input-error'));
    form.querySelectorAll('.field-error').forEach((element) => element.remove());
}

function collect(form, names) {
    const data = {};
    for (const name of names) {
        const field = form.querySelector(`[name="${name}"]`);
        data[name] = field ? field.value : '';
    }
    return data;
}
