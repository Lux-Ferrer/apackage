/* 我的 / 数据管理 / 关于。
 *
 * `#/me` 对应 `webapp/templates/me/index.html`；`#/me/data` 是 M5 **新增**的一页 ——
 * 纯前端版把"数据在哪、会不会丢"变成了用户必须知道的事（Flask 版数据在服务端的文件里，
 * 用户不用操心；这一版数据在浏览器的 IndexedDB 里，系统可能清理它）。
 * 这一页因此不是"锦上添花"，而是把 M5-3 的配额/持久化/备份能力交到用户手上的入口。
 *
 * 关于页对应 `webapp/templates/about.html`，模块进度改成 M1~M5 的实际情况。
 */

import { CONFIG } from '../config.js';
import { pathFor } from '../router.js';
import * as defects from '../repo/defects.js';
import * as images from '../repo/images.js';
import * as measurements from '../repo/measurements.js';
import * as projects from '../repo/projects.js';
import { describeStorage, formatBytes, requestPersistence, shellVersion } from '../storage.js';
import { STORE } from '../db.js';
import { badge, h, infoTable, link } from '../ui/dom.js';
import { confirmDialog, flash } from '../ui/dialog.js';
import { card, pageHead } from './layout.js';

/* --------------------------------------------------------------------------
 * 我的
 * ------------------------------------------------------------------------ */

export async function index(ctx) {
    const reporter = CONFIG.DEFAULT_REPORTER;
    const overview = await counts(ctx.db);

    return {
        nodes: [
            card([
                h('h1', { text: '我的' }),
                h('div.profile', null, [
                    h('div.profile-avatar', { 'aria-hidden': 'true', text: reporter.name.slice(0, 1) }),
                    h('div.profile-body', null, [
                        h('p.profile-name', { text: reporter.name }),
                        h('p.report-meta.muted', {
                            text: `${reporter.department}${reporter.department_code ? `（${reporter.department_code}）` : ''}`,
                        }),
                        reporter.employee_no ? h('p.report-meta.muted', { text: `工号 ${reporter.employee_no}` }) : null,
                    ]),
                ]),
                h('p.hint', { text: '登录功能未纳入本期范围，报告人取默认配置（config.DEFAULT_REPORTER）。' }),
            ]),
            card([
                h('h2', { text: '数据概览' }),
                h('nav.stats', { 'aria-label': '数据概览' }, [
                    stat(pathFor('projects.index'), overview.projects, '项目'),
                    stat(pathFor('projects.index'), overview.records, '检测记录'),
                    stat(pathFor('reports.index'), overview.reports, '报告'),
                ]),
            ]),
            card([
                h('h2', { text: '数据管理' }),
                h('p.hint', {
                    text: '这一版把数据存在浏览器里（IndexedDB），所以「导出备份」是你保住数据的唯一手段。'
                        + '进入数据管理可以看到已用空间、申请持久化授权、导入/导出备份，以及清除全部报告。',
                }),
                h('p', null, h('a.btn', { href: pathFor('me.data'), text: '进入数据管理 →' })),
            ]),
            card([
                h('h2', { text: '应用信息' }),
                infoTable([
                    ['名称', CONFIG.APP_INFO.name],
                    ['版本', CONFIG.APP_INFO.version],
                    ['出品', CONFIG.APP_INFO.org],
                ]),
                h('p', null, link(pathFor('pages.about'), '模块进度与范围说明 →')),
            ]),
        ],
    };
}

function stat(href, value, label) {
    return h('a.stat', { href }, [
        h('span.stat-value', { text: String(value) }),
        h('span.stat-label', { text: label }),
    ]);
}

async function counts(db) {
    const [projectRows, recordCount_, reportStats] = await Promise.all([
        projects.listWithCounts(db), recordCount(db), defects.stats(db),
    ]);
    return { projects: projectRows.length, records: recordCount_, reports: reportStats.total };
}

/** 检测记录总数（数据层没有现成的计数导出，这里直接数一下）。 */
async function recordCount(db) {
    return db.read([STORE.records], (ctx) => ctx.count(STORE.records));
}

/* --------------------------------------------------------------------------
 * 数据管理（M5 新增）
 * ------------------------------------------------------------------------ */

export async function data(ctx) {
    const storage = await describeStorage({ storage: ctx.storage });
    const [projectRows, recordCount_, reportStats, imageKeys] = await Promise.all([
        projects.listWithCounts(ctx.db), recordCount(ctx.db), defects.stats(ctx.db), images.allKeys(ctx.db),
    ]);

    const persistButton = h('button.btn.ghost', { type: 'button', text: '申请持久化授权' });    const persistStatus = h('p.hint');
    const renderPersist = (result) => {
        persistStatus.textContent = result.reason;
        persistStatus.className = result.persisted ? 'hint' : 'hint warn';
    };
    persistStatus.textContent = storage.lines.at(-1) ?? '';
    persistStatus.className = storage.status.persisted ? 'hint' : 'hint warn';
    persistButton.addEventListener('click', async () => {
        persistButton.disabled = true;
        renderPersist(await requestPersistence(ctx.storage));
        persistButton.disabled = false;
        ctx.refresh();
    });

    const exportButton = h('button.btn', { type: 'button', text: '导出备份（.zip）' });
    exportButton.addEventListener('click', async () => {
        exportButton.disabled = true;
        exportButton.textContent = '打包中…';
        try {
            const { exportBackup } = await import('../import-export.js');
            const { downloadBlob } = await import('../export.js');
            const backup = await exportBackup(ctx.db);
            downloadBlob(backup.blob, backup.filename);
            flash(`已导出备份 ${backup.filename}（${formatBytes(backup.blob.size)}`
                + `${backup.missingImages.length ? `，另有 ${backup.missingImages.length} 张图片缺失未包含` : ''}）`);
            if (backup.missingImages.length) {
                flash(`有 ${backup.missingImages.length} 张隐患图片的原图已不在库里，备份未包含它们`, 'error');
            }
        } catch (error) {
            flash(`导出备份失败：${error.message}`, 'error');
        } finally {
            exportButton.disabled = false;
            exportButton.textContent = '导出备份（.zip）';
        }
    });

    const importInput = h('input', {
        type: 'file', id: 'backup-file', name: 'backup', accept: '.zip,application/zip',
    });
    const importButton = h('button.btn.danger', { type: 'button', text: '导入备份（覆盖全部数据）' });
    importButton.addEventListener('click', async () => {
        const file = importInput.files && importInput.files[0];
        if (!file) {
            flash('先选择一个备份文件（.zip）', 'error');
            return;
        }
        try {
            const { inspectBackup, importBackup } = await import('../import-export.js');
            const info = await inspectBackup(file);
            const ok = await confirmDialog({
                message: `导入会用备份内容**覆盖当前全部数据**（当前有 ${projectRows.length} 个项目、`
                    + `${recordCount_} 条检测记录、${reportStats.total} 份报告）。`
                    + `备份导出时间：${info.exportedAt}，含 ${info.counts.projects} 个项目、`
                    + `${info.counts.records} 条检测记录、${info.counts.defects} 份报告、`
                    + `${info.imageFiles} 张图片。`
                    + '此操作不可恢复 —— 建议先导出一份当前备份。',
                okText: '确认覆盖导入',
                title: '覆盖全部数据？',
            });
            if (!ok) return;
            importButton.disabled = true;
            importButton.textContent = '导入中…';
            const result = await importBackup(ctx.db, file, { pipeline: ctx.pipeline });
            flash(`已导入：${result.imported.projects} 个项目 / ${result.imported.records} 条记录 / `
                + `${result.imported.defects} 份报告 / ${result.imported.images} 张图片`
                + `${result.imageFailed ? `（${result.imageFailed} 张图片在备份里缺失）` : ''}`);
            ctx.refresh();
        } catch (error) {
            flash(`导入失败：${error.message}`, 'error');
        } finally {
            importButton.disabled = false;
            importButton.textContent = '导入备份（覆盖全部数据）';
        }
    });

    const rebuildButton = h('button.btn.ghost', { type: 'button', text: '重建全部缩略图' });
    rebuildButton.addEventListener('click', async () => {
        rebuildButton.disabled = true;
        rebuildButton.textContent = '重建中…';
        try {
            const result = await images.rebuildThumbnails(ctx.db, { pipeline: ctx.pipeline });
            flash(`缩略图已重建：${result.rebuilt} 张成功`
                + `${result.failed ? `，${result.failed} 张失败（原图可能损坏）` : ''}`);
        } catch (error) {
            flash(`重建失败：${error.message}`, 'error');
        } finally {
            rebuildButton.disabled = false;
            rebuildButton.textContent = '重建全部缩略图';
        }
    });

    /**
     * 清除全部报告（需求 3.7c；UI 设计第 9 节决策 1 = 做）。
     *
     * 这是一页里唯一**不可恢复**的操作，所以三条纪律一条不少：
     * 二次确认写明份数与"图片一并删除" → 数据层先删库（同一事务）→ 回执写明实际删了几份。
     */
    const clearButton = h('button.btn.danger', { type: 'button', text: '清除全部报告' });
    clearButton.addEventListener('click', async () => {
        if (!reportStats.total) {
            flash('没有可清除的报告');
            return;
        }
        const ok = await confirmDialog({
            message: `确认清除全部 ${reportStats.total} 份缺陷报告？隐患图片会一并删除，`
                + '报告与项目的关联同时消失，此操作不可恢复。',
            okText: '确认清除',
        });
        if (!ok) return;
        const removed = await defects.deleteAll(ctx.db);
        flash(`已清除全部报告：${removed.reports} 份（含 ${removed.images} 张隐患图片）`);
        ctx.refresh();
    });

    const overview = [
        ['项目', `${projectRows.length} 个`],
        ['检测记录', `${recordCount_} 条`],
        ['缺陷报告', `${reportStats.total} 份（高 ${reportStats.high} / 中 ${reportStats.medium} / 低 ${reportStats.low}）`],
        ['隐患图片', `${imageKeys.length} 张`],
        ['已用空间', storage.status.supported
            ? `${formatBytes(storage.status.usage)} / ${formatBytes(storage.status.quota)}（${(storage.status.ratio * 100).toFixed(1)}%）`
            : '当前浏览器不提供容量信息'],
    ];

    return {
        nodes: [
            card([
                ...pageHead('数据管理', link(pathFor('me.index'), '← 返回我的')),
                h('p.hint', {
                    text: '数据存在这台设备的浏览器里（IndexedDB），不会上传到任何服务器。'
                        + '换手机、清浏览器数据、或系统自动清理都会导致数据丢失 —— 请定期导出备份。',
                }),
                infoTable(overview),
            ]),
            card([
                h('h2', { text: '持久化授权' }),
                h('p.hint', {
                    text: 'iOS Safari 对**未获持久化授权**的站点有约 7 天的闲置清理策略。'
                        + '现场记录、回办公室导出这种用法一定要把授权拿到手。',
                }),
                persistStatus,
                persistButton,
            ]),
            card([
                h('h2', { text: '导出备份' }),
                h('p.hint', {
                    text: '把所有项目、检测记录、缺陷报告与**原图**打包成一个 zip。'
                        + '缩略图不在备份里 —— 它是可从原图重新生成的派生值，导入时会自动重建。',
                }),
                exportButton,
            ]),
            card([
                h('h2', { text: '导入备份' }),
                h('p.hint', {
                    text: '导入会**覆盖当前全部数据**（备份是完整快照，不做合并）。导入前会让你确认一次要覆盖的内容。',
                }),
                h('div.field', null, [
                    h('label', { for: 'backup-file', text: '备份文件' }),
                    importInput,
                ]),
                importButton,
            ]),
            card([
                h('h2', { text: '维护' }),
                h('p.hint', { text: '缩略图参数调整过、或从没有缩略图的备份恢复之后，可以在这里批量重建。' }),
                rebuildButton,
            ]),
            card([
                h('h2', { text: '清除全部报告' }),
                reportStats.total
                    ? h('p.hint', {
                        text: `清除全部 ${reportStats.total} 份缺陷报告；隐患图片会一并删除。`
                            + '此操作**不可恢复**，建议先导出一份备份。',
                    })
                    : h('p.hint', { text: '没有可清除的报告。' }),
                h('div.danger-zone', null, clearButton),
            ]),
        ],
    };
}

/* --------------------------------------------------------------------------
 * 关于（模块进度）
 * ------------------------------------------------------------------------ */

const MODULES = [
    ['项目管理与检测记录', '可用（M1）', 'projects.index', true],
    ['项目级 Word 导出', '可用（M2）', 'projects.index', true],
    ['缺陷填报与附页', '可用（M3）', 'reports.index', true],
    ['报告管理', '可用（M4）', 'reports.index', true],
    ['移动端界面', '可用（UI）', 'projects.index', true],
    ['纯前端版（IndexedDB + docx JS）', '进行中（M5）', 'me.data', true],
    ['登录 / 统计 / 速记', '范围外', null, false],
];

export async function about(ctx) {
    const offlineVersion = await shellVersion();
    return {
        nodes: [
            card([
                h('h1', { text: '模块进度' }),
                h('p.sub', { text: 'M1 项目管理与检测记录 · M2 项目级 Word 导出 · M3 缺陷附页 · M4 报告管理 · UI 移动端 · M5 纯前端版' }),
                h('table.grid', null, [
                    h('thead', null, h('tr', null, [h('th', { text: '模块' }), h('th', { text: '状态' }), h('th')])),
                    h('tbody', null, MODULES.map(([name, status, routeName, ready]) => h('tr', null, [
                        h('td', { text: name }),
                        h('td', null, badge(status, ready ? 'ok' : 'todo')),
                        h('td.right', null, ready && routeName
                            ? h('a.btn.small', { href: pathFor(routeName), text: '进入' })
                            : h('span.muted', { text: '—' })),
                    ]))),
                ]),
            ]),
            card([
                h('h2', { text: '使用顺序' }),
                h('ol.plain', null, [
                    '在「项目」里新建一个项目（项目编号 + 房屋名称必填）；',
                    '进入项目详情，点「添加检测记录」，选择立柱或横梁模板；',
                    '填写楼层、构件位置，展开每个检测面录入 5 个厚度读数（最小值自动计算）；',
                    '在「报告」里填写缺陷报告，可绑定到项目；',
                    '回项目详情导出 Word，需要时把关联报告作为附页一并输出。',
                ].map((line) => h('li', { text: line }))),
            ]),
            card([
                h('h2', { text: '本期不做（已确认范围外）' }),
                h('p.sub', { text: '膜厚检测 · 玻璃面板尺寸及厚度检测 · 速记 · 统计 · 登录 · 结构安全评定' }),
            ]),
            card([
                h('h2', { text: '运行方式' }),
                h('p.hint', {
                    text: '这是一个纯静态页面：用任意静态服务器指向 web/ 目录即可（例如 '
                        + 'python -m http.server 8080 --directory web）。用 file:// 直接打开不行 —— '
                        + 'IndexedDB 与 ES modules 都会受限。',
                }),
                h('p.hint', {
                    text: '装过一次之后可以离线使用（浏览器缓存了应用壳）；iOS 上请用'
                        + '「添加到主屏幕」，并在「我的 → 数据管理」里申请持久化授权。',
                }),
                h('table.grid', null, h('tbody', null, [
                    ['名称', CONFIG.APP_INFO.name],
                    ['English', CONFIG.APP_INFO.name_en],
                    ['版本', CONFIG.APP_INFO.version],
                    ['出品', CONFIG.APP_INFO.org],
                    ['需求方', CONFIG.APP_INFO.client],
                    // 离线缓存的版本号：改过任何一个被缓存的文件它就会变，
                    // 出"怎么还是旧页面"这类问题时，第一眼就能对比出来
                    ['离线缓存版本', offlineVersion ?? '（还没有离线缓存）'],
                ].map(([label, value]) => h('tr', null, [h('th', { text: label }), h('td', { text: value })])))),
            ]),
        ],
    };
}
