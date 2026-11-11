/* 报告管理：列表（含等级筛选）/ 详情 / 缺陷填报。
 *
 * 对应 `webapp/templates/reports/*.html` 与 `webapp/templates/defects/form.html`。
 *
 * 一处与 Flask 版**本质不同、必须讲清楚**的地方：缩略图与大图。
 *   Flask：`<img src="/reports/1/thumbnail">` —— 服务端请求时现压，靠 HTTP 缓存兜重复解码；
 *   M5   ：缩略图**已经在 IndexedDB 里**（`images.thumb`，设计文档 3.4 的那次有意偏离），
 *          这里只是 `URL.createObjectURL(thumb)`。**用过的 objectURL 必须 revoke** ——
 *          一张 20MB 的原图 URL 不释放，翻十几条报告就能把手机内存吃满。
 */

import { CONFIG } from '../config.js';
import { profileLabel } from '../product.js';
import { pathFor } from '../router.js';
import * as defects from '../repo/defects.js';
import * as images from '../repo/images.js';
import * as profileRepo from '../repo/profile.js';
import * as projects from '../repo/projects.js';
import { badge, h, infoTable, link } from '../ui/dom.js';
import { confirmDialog, flash } from '../ui/dialog.js';
import { createObjectURL } from '../ui/objecturl.js';
import { actionBar, backLink, card, formRow, input, pageHead, select, textarea, thumbnail } from './layout.js';
import { notFound } from './projects.js';

/* --------------------------------------------------------------------------
 * 列表（顶部统计同时是筛选控件）
 * ------------------------------------------------------------------------ */

export async function index(ctx) {
    const level = ctx.query.level ?? null;
    const known = level && CONFIG.RISK_LEVELS.includes(level) ? level : null;
    const warning = level && !known ? `未知的筛选值「${level}」，已显示全部报告。` : null;

    const [rows, stats] = await Promise.all([
        defects.listReports(ctx.db, known),
        defects.stats(ctx.db),
    ]);
    const projectsById = new Map((await projects.listOptions(ctx.db)).map((item) => [item.id, item]));

    const statsNav = h('nav.stats', { 'aria-label': '按隐患等级筛选' }, [
        h('a.stat', { class: !known ? 'active' : null, href: pathFor('reports.index') }, [
            h('span.stat-value', { text: String(stats.total) }), h('span.stat-label', { text: '全部' }),
        ]),
        ...CONFIG.RISK_LEVELS.map((name) => {
            const key = CONFIG.RISK_BADGE_CLASSES[name];
            return h('a.stat', {
                class: `${key}${known === name ? ' active' : ''}`,
                href: pathFor('reports.index', {}, { level: name }),
            }, [
                h('span.stat-value', { text: String(stats[key]) }), h('span.stat-label', { text: name }),
            ]);
        }),
    ]);

    let body;
    if (rows.length) {
        // 缩略图需要先取出来做 objectURL：一次性并发取，渲染完不再持有 record
        const cards = await Promise.all(rows.map(async (row) => {
            let url = null;
            if (row.image_path) {
                const record = await images.get(ctx.db, row.image_path);
                if (record?.thumb) url = createObjectURL(record.thumb);
            }
            return reportCard(ctx, row, projectsById.get(row.project_id), url);
        }));
        body = h('ul.report-list', null, cards);
    } else if (known) {
        body = h('p.hint', null, [
            `没有「${known}」等级的报告。`, link(pathFor('reports.index'), '查看全部'),
        ]);
    } else {
        body = [
            h('p.hint', { text: '还没有报告。' }),
            h('p', null, h('a.btn', { href: pathFor('reports.new'), text: '填写第一份缺陷报告' })),
        ];
    }

    return {
        nodes: [card([
            ...pageHead('报告管理', h('a.btn', { href: pathFor('reports.new'), text: '+ 新建报告' })),
            statsNav,
            warning ? h('p.hint.warn', { text: warning }) : null,
            body,
        ])],
    };
}

function reportCard(ctx, row, project, thumbUrl) {
    const href = pathFor('reports.detail', { id: row.id });
    const label = project ? `${project.project_no} - ${project.house_name}` : null;

    const button = h('button.link.danger-link', { type: 'button', text: '删除' });
    button.addEventListener('click', () => removeReport(ctx, row));

    return h('li.report-card', null, [
        thumbnail(thumbUrl, { href, alt: `查看报告 #${row.id}` }),
        h('div.report-body', null, [
            h('div.report-title', null, [
                h('a.link.strong', { href, text: row.defect_type }),
                badge(row.risk_level, CONFIG.RISK_BADGE_CLASSES[row.risk_level]),
            ]),
            h('p.report-meta', { text: row.project_part }),
            label ? h('p.report-meta.muted', { text: label }) : null,
            h('p.report-meta.muted', { text: defects.formatReportTime(row.created_at) }),
        ]),
        h('div.report-actions', null, [link(href, '详情'), button]),
    ]);
}

async function removeReport(ctx, row) {
    const project = row.project_id ? await projects.get(ctx.db, row.project_id) : null;
    const ok = await confirmDialog({
        message: `确认删除报告 #${row.id}（${row.defect_type}）？隐患图片会一并删除，此操作不可恢复。`
            + (project ? `项目「${project.house_name}」的关联会同时解除。` : ''),
        okText: '确认删除',
    });
    if (!ok) return;
    await defects.remove(ctx.db, row.id);
    flash(`已删除报告 #${row.id}`);
    ctx.refresh();
}

/* --------------------------------------------------------------------------
 * 详情
 * ------------------------------------------------------------------------ */

export async function detail(ctx) {
    const report = await defects.get(ctx.db, ctx.params.id);
    if (!report) return notFound('报告不存在');

    const project = report.project_id ? await projects.get(ctx.db, report.project_id) : null;
    const image = report.image_path ? await images.get(ctx.db, report.image_path) : null;
    const originalName = images.originalNameFromPath(report.image_path);
    const photoUrl = image?.blob ? createObjectURL(image.blob) : null;

    let photo;
    if (photoUrl) {
        photo = h('figure.photo', null, [
            h('a', { href: photoUrl, target: '_blank', rel: 'noopener' },
                h('img', { src: photoUrl, alt: `${report.defect_type} 隐患图片` })),
            h('figcaption.hint', {
                text: `${originalName} · 点击看原图；附在项目导出里的是导出时现压的副本`,
            }),
        ]);
    } else {
        photo = h('p.photo-missing', {
            text: report.image_path
                ? '图片文件缺失（记录里有图片，但库里已找不到原图）'
                : '这份报告没有隐患图片',
        });
    }

    const rows = [
        ['缺陷类型', report.defect_type],
        ['工程部位', report.project_part],
        ['隐患等级', badge(report.risk_level, CONFIG.RISK_BADGE_CLASSES[report.risk_level])],
        ['整改方案', h('span.pre', { text: report.rectification_plan })],
        report.related_standards ? ['相关规范', h('span.pre', { text: report.related_standards })] : null,
        report.extra_advice ? ['补充建议', h('span.pre', { text: report.extra_advice })] : null,
        ['报告人', `${report.reporter_name}（${report.reporter_department}）`],
        ['提交时间', defects.formatReportTime(report.created_at)],
        ['绑定项目', project
            ? h('span', null, [
                link(pathFor('projects.detail', { id: project.id }), `${project.project_no} - ${project.house_name}`),
                h('span.hint', { text: '（导出该项目报告时会作为附页追加）' }),
            ])
            : h('span.muted', { text: '未绑定项目' })],
    ];

    const deleteButton = h('button.btn.danger', { type: 'button', text: '删除报告' });
    deleteButton.addEventListener('click', async () => {
        const ok = await confirmDialog({
            message: `确认删除报告 #${report.id}（${report.defect_type}）？隐患图片会一并删除，此操作不可恢复。`
                + (project ? `项目「${project.house_name}」的关联会同时解除。` : ''),
            okText: '确认删除',
        });
        if (!ok) return;
        await defects.remove(ctx.db, report.id);
        flash(`已删除报告 #${report.id}`);
        ctx.navigate(pathFor('reports.index'));
    });

    return {
        nodes: [card([
            ...pageHead(`缺陷报告 #${report.id}`, backLink(pathFor('reports.index'), '返回报告管理')),
            photo,
            infoTable(rows),
            h('div.actions', null, [
                deleteButton,
                link(pathFor('reports.new'), '再填写一条'),
                link(project ? pathFor('projects.detail', { id: project.id }) : pathFor('projects.index'),
                    '去项目里导出报告'),
            ]),
        ])],
    };
}

/* --------------------------------------------------------------------------
 * 缺陷填报
 * ------------------------------------------------------------------------ */

export async function form(ctx) {
    const projectOptions = await projects.listOptions(ctx.db);
    const profile = await profileRepo.read(ctx.db);
    const maxImageMb = Math.floor(CONFIG.MAX_IMAGE_BYTES / (1024 * 1024));

    const imageInput = h('input', {
        type: 'file', id: 'image', name: 'image', accept: 'image/*', capture: 'environment',
        dataset: { maxBytes: String(CONFIG.MAX_IMAGE_BYTES) },
    });
    const imagePreview = h('div.image-preview', { id: 'image-preview', hidden: true },
        h('img', { id: 'image-preview-img', alt: '隐患图片预览' }));

    const defectTypeSelect = select({
        name: 'defect_type', id: 'defect_type',
        options: CONFIG.DEFECT_TYPES.map((item, index) => ({ value: item, label: item, selected: index === 0 })),
    });
    const customInput = h('input.hidden-row', {
        type: 'text', id: 'custom_defect_type', name: 'custom_defect_type',
        maxlength: 100, placeholder: '请输入自定义缺陷类型', value: '',
    });
    const toggleCustom = () => {
        const isCustom = defectTypeSelect.value === CONFIG.CUSTOM_DEFECT_OPTION;
        customInput.classList.toggle('hidden-row', !isCustom);
        if (isCustom) customInput.focus();
    };
    defectTypeSelect.addEventListener('change', toggleCustom);

    const formId = 'defect-form';
    const form = h('form', { id: formId, novalidate: true }, [
        h('h2.form-section', { text: '隐患信息' }),
        h('div.field', null, [
            h('label', { for: 'image' }, ['隐患图片', h('span.required', { text: ' *' })]),
            imageInput,
            h('p.hint', {
                text: `拍照或从相册选择；不超过 ${maxImageMb}MB，支持 `
                    + `${CONFIG.ALLOWED_IMAGE_EXTENSIONS.map((item) => item.replace('.', '')).join('、')}`,
            }),
            h('p.field-error', { id: 'image-error', hidden: true }),
            imagePreview,
        ]),
        h('div.form-table', null, [
            formRow({ label: '缺陷类型', forId: 'defect_type', required: true, control: [defectTypeSelect, customInput] }),
            formRow({
                label: '工程部位', forId: 'project_part', required: true,
                control: h('input', {
                    type: 'text', id: 'project_part', name: 'project_part', required: true,
                    maxlength: 200, placeholder: '如：东立面三层 1# 立柱', value: '',
                }),
            }),
            formRow({
                label: '隐患等级', required: true,
                control: h('div.segmented', null, CONFIG.RISK_LEVELS.map((level) => h('label', null, [
                    h('input', {
                        type: 'radio', name: 'risk_level', value: level,
                        checked: level === CONFIG.DEFAULT_RISK_LEVEL || null,
                    }),
                    level,
                ]))),
            }),
        ]),
        h('h2.form-section', { text: '处理建议' }),
        h('div.field', null, [
            h('label', { for: 'rectification_plan' }, ['整改方案', h('span.required', { text: ' *' })]),
            textarea({ name: 'rectification_plan', rows: 5, placeholder: '填写整改措施……', required: true }),
        ]),
        h('div.field', null, [
            h('label', { for: 'related_standards', text: '相关规范' }),
            textarea({ name: 'related_standards', rows: 3, placeholder: '违反的标准条款（标准名称 + 条款号）' }),
            h('p.hint', { text: '选填；每行一条' }),
        ]),
        h('div.field', null, [
            h('label', { for: 'extra_advice', text: '补充建议' }),
            textarea({ name: 'extra_advice', rows: 3, placeholder: '人工补充说明（选填）' }),
        ]),
        h('h2.form-section', { text: '归属' }),
        h('div.form-table', null, [
            formRow({
                label: '绑定项目', forId: 'project_id',
                control: [
                    select({
                        name: 'project_id', id: 'project_id',
                        options: [{ value: '', label: '不绑定' }, ...projectOptions.map((project) => ({
                            value: String(project.id),
                            label: `${project.project_no} - ${project.house_name}`,
                        }))],
                    }),
                    h('p.hint', { text: '绑定后，该报告可作为附页随项目报告一并导出' }),
                ],
            }),
            formRow({
                label: '报告人',
                control: h('p.readonly-value', { text: profileLabel(profile) }),
                hint: '取自「我的 → 个人信息配置」，在那一页修改',
            }),
        ]),
    ]);

    attachImagePreview(form, imageInput);

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const status = await saveDefect(ctx, form, imageInput);
        if (status) flash(status, 'error');
    });

    return {
        chrome: 'form',
        nodes: [
            card([
                ...pageHead('缺陷检测填报', backLink(pathFor('reports.index'), '报告管理')),
                h('p.sub', { text: '拍照取证 + 填写结论；数据存在本机 IndexedDB，可随项目报告输出附页' }),
                form,
            ], 'form-card'),
            actionBar({ cancelHref: pathFor('reports.index'), cancelLabel: '取消', submitLabel: '提交保存', formId }),
        ],
    };
}

/** 隐患图片的就地校验与预览（移植 `defects_form.js` 的语义）。 */
function attachImagePreview(root, input) {
    const preview = root.querySelector('#image-preview');
    const previewImage = root.querySelector('#image-preview-img');
    const errorBox = root.querySelector('#image-error');
    const maxBytes = parseInt(input.dataset.maxBytes, 10) || 0;
    let objectUrl = null;

    const showError = (message) => {
        errorBox.textContent = message || '';
        errorBox.hidden = !message;
        input.classList.toggle('input-error', Boolean(message));
    };

    input.addEventListener('change', () => {
        const file = input.files && input.files[0];
        if (objectUrl) {
            URL.revokeObjectURL(objectUrl);
            objectUrl = null;
        }
        preview.hidden = true;
        previewImage.removeAttribute('src');
        if (!file) return showError('');

        // 元数据级校验（大小/扩展名）走数据层同一个函数，避免两套规则
        const error = images.validateFile(file);
        if (error) {
            showError(error);
            input.value = '';                    // 清空，避免"看起来选上了"
            return;
        }
        showError('');
        objectUrl = URL.createObjectURL(file);
        previewImage.src = objectUrl;
        preview.hidden = false;
    });
}

/** 保存一份缺陷报告：字段校验 → 现算缩略图 → 报告 + 图片**同一事务**写入。 */
async function saveDefect(ctx, form, imageInput) {
    form.querySelectorAll('.field-error').forEach((element) => {
        if (element.id !== 'image-error') element.remove();
    });
    form.querySelectorAll('.input-error').forEach((element) => element.classList.remove('input-error'));

    const payload = readDefectForm(form);
    const { data, errors } = await defects.parseForm(ctx.db, payload);

    const file = imageInput.files && imageInput.files[0];
    if (!file && !errors.image) errors.image = '请上传隐患图片（拍照或从相册选择）';
    if (file) {
        const imageError = images.validateFile(file);
        if (imageError) errors.image = imageError;
    }

    if (Object.keys(errors).length) {
        showDefectErrors(form, errors);
        // 图片错误固定显示在预览区（那里是用户刚操作过的地方）
        if (errors.image) {
            const box = form.querySelector('#image-error');
            box.textContent = errors.image;
            box.hidden = false;
            imageInput.classList.add('input-error');
        }
        return '有必填项没填或图片不合规，已标出问题所在';
    }

    try {
        // ⚠️ 图片解码与缩略图必须在**开事务之前**做完（IndexedDB 事务纪律第 3 条）。
        // `pipeline` 是注入点：浏览器里留空走 canvas 默认实现；jsdom 测试里塞假编解码器
        // （Node/jsdom 都没有 canvas —— 见 web/tests/ui.test.mjs）。
        const record = await images.prepareUpload(ctx.db, file, { pipeline: ctx.pipeline });
        const id = await defects.create(ctx.db, data, record);
        flash(`报告 #${id} 已保存${data.project_id ? '，并绑定到项目' : ''}`);
        ctx.navigate(pathFor('reports.detail', { id }));
    } catch (error) {
        if (error.name === 'QuotaError') {
            return `空间不足，无法保存这张图片：${error.message}`;
        }
        if (error.name === 'ImageError') return error.message;
        return `保存失败：${error.message}`;
    }
    return null;
}

function readDefectForm(form) {
    const data = {
        defect_type: form.querySelector('[name="defect_type"]').value,
        custom_defect_type: form.querySelector('[name="custom_defect_type"]').value,
        project_part: form.querySelector('[name="project_part"]').value,
        rectification_plan: form.querySelector('[name="rectification_plan"]').value,
        related_standards: form.querySelector('[name="related_standards"]').value,
        extra_advice: form.querySelector('[name="extra_advice"]').value,
        project_id: form.querySelector('[name="project_id"]').value,
    };
    const checked = form.querySelector('[name="risk_level"]:checked');
    data.risk_level = checked ? checked.value : CONFIG.DEFAULT_RISK_LEVEL;
    return data;
}

function showDefectErrors(form, errors) {
    for (const [name, message] of Object.entries(errors)) {
        if (name === 'image') continue;                 // 图片单独处理（上面）
        const field = form.querySelector(`[name="${name}"]`);
        if (!field) continue;
        field.classList.add('input-error');
        const holder = field.closest('.form-control') ?? field.closest('.field') ?? field.parentNode;
        let box = holder.querySelector('.field-error');
        if (!box) {
            box = h('p.field-error');
            holder.appendChild(box);
        }
        box.textContent = message;
    }
    const first = form.querySelector('.input-error');
    if (first) first.focus();
}
