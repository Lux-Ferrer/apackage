/* 交付版自检（release 分支）：
 *
 *  1. **产品身份**只有一处定义（`app/product.js`）——版本号写死在两个地方迟早会对不上；
 *  2. **个人信息配置**（报告人 / 部门）落在 IndexedDB 的 `meta` 表里，没配过就是出厂默认值；
 *  3. **开发/课程痕迹不许漏进交付版**：页面文案、console.log、本地开发路径。
 *
 * 第 3 条为什么值得写成测试：这一版是把课程项目的产物交给客户内网部署，
 * "我的 → 关于"里曾经有一张 M0~M5 的模块进度表、报告人写死成开发者名字、
 * 首页 `<noscript>` 里还留着"参考实现请运行 python app.py"。
 * 这些东西不影响功能，所以单元测试不会红 —— 只能靠一条专门盯着它们的断言。
 *
 * 页面级（渲染后）的检查在 `ui.test.mjs` 里：那里有 jsdom，能看到用户真正看到的东西。
 */
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

import { DEFAULT_PROFILE, PRODUCT, PROFILE_LIMITS, profileLabel, versionLabel } from '../app/product.js';
import { chromeFor, pathFor, resolve as resolveRoute, titleFor } from '../app/router.js';
import { STORE } from '../app/db.js';
import * as profile from '../app/repo/profile.js';
import { freshDb } from './helpers.mjs';

const WEB_DIR = fileURLToPath(new URL('..', import.meta.url));
const READ = (relative) => readFileSync(resolve(WEB_DIR, relative), 'utf8');
const APP_DIR = resolve(WEB_DIR, 'app');

/** 递归收集源码文件（顺序稳定，报错信息可复现）。 */
function walk(directory, suffix = '.js') {
    const files = [];
    for (const entry of readdirSync(directory, { withFileTypes: true })
        .sort((left, right) => (left.name < right.name ? -1 : 1))) {
        const full = join(directory, entry.name);
        if (entry.isDirectory()) files.push(...walk(full, suffix));
        else if (entry.name.endsWith(suffix)) files.push(full);
    }
    return files;
}

/* --------------------------------------------------------------------------
 * 1. 产品身份
 * ------------------------------------------------------------------------ */

test('产品身份：名称 / 版本 / 出品方齐全，版本号是 x.y.z', () => {
    assert.match(PRODUCT.version, /^\d+\.\d+\.\d+$/, '版本号应是 x.y.z（不带 v 前缀）');
    assert.equal(versionLabel(), `v${PRODUCT.version}`, '界面统一用 versionLabel() 加 v 前缀');
    assert.ok(PRODUCT.name.length > 3, '产品名称不能为空');
    assert.ok(PRODUCT.vendor.length > 3, '出品方不能为空');
    // 「建筑幕墙检测报告工具」是客户认得的名字，改了这里要同步交付包文件名与说明文档
    assert.match(PRODUCT.name, /幕墙/);
});

test('版本号只有 product.js 一处：HTML / manifest 里不写死版本', () => {
    for (const relative of ['index.html', 'manifest.webmanifest']) {
        const text = READ(relative);
        assert.doesNotMatch(text, new RegExp(PRODUCT.version.replace(/\./g, '\\.')),
            `${relative} 里写死了版本号 —— 版本只该出现在 app/product.js`);
    }
});

test('页面标题用产品名（不写死，也不含开发期字样）', () => {
    assert.match(titleFor('me.index'), new RegExp(PRODUCT.name));
    assert.match(titleFor('projects.index', '项目'), new RegExp(PRODUCT.name));
    assert.doesNotMatch(titleFor('me.index'), /M\d|Capstone|NYU/);
});

/* --------------------------------------------------------------------------
 * 2. 个人信息配置（报告人 / 部门）
 * ------------------------------------------------------------------------ */

test('个人信息：没配过 → 出厂默认值（检测员 / 检测部）', async () => {
    const db = await freshDb();
    const current = await profile.read(db);
    assert.deepEqual(current, { ...DEFAULT_PROFILE });
    assert.equal(DEFAULT_PROFILE.reporter_name, '检测员');
    assert.equal(DEFAULT_PROFILE.reporter_department, '检测部');
    db.close();
});

test('个人信息：保存后读回、去空白、只占 meta 一行', async () => {
    const db = await freshDb();
    const saved = await profile.save(db, {
        reporter_name: '  张三  ', reporter_department: ' 幕墙检测部 ',
    });
    assert.deepEqual(saved, { reporter_name: '张三', reporter_department: '幕墙检测部' });

    const current = await profile.read(db);
    assert.deepEqual(current, { reporter_name: '张三', reporter_department: '幕墙检测部' });

    const rows = await db.read([STORE.meta], (ctx) => ctx.getAll(STORE.meta));
    const profileRows = rows.filter((row) => row.key === profile.PROFILE_KEY);
    assert.equal(profileRows.length, 1, '个人信息只该有一行（重复保存不该累积）');
    assert.match(profileRows[0].value.updated_at, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);

    // 再存一次是覆盖，不是新增
    await profile.save(db, { reporter_name: '李四', reporter_department: '检测部' });
    const again = await db.read([STORE.meta], (ctx) => ctx.getAll(STORE.meta));
    assert.equal(again.filter((row) => row.key === profile.PROFILE_KEY).length, 1);
    db.close();
});

test('个人信息：空值与超长被拦下（就地报错，不写库）', () => {
    const blank = profile.parseForm({ reporter_name: '  ', reporter_department: '' });
    assert.equal(blank.errors.reporter_name, '报告人姓名不能为空');
    assert.equal(blank.errors.reporter_department, '部门不能为空');

    const tooLong = profile.parseForm({
        reporter_name: '姓'.repeat(PROFILE_LIMITS.reporter_name + 1),
        reporter_department: '部'.repeat(PROFILE_LIMITS.reporter_department + 1),
    });
    assert.match(tooLong.errors.reporter_name, /不能超过/);
    assert.match(tooLong.errors.reporter_department, /不能超过/);

    const ok = profile.parseForm({ reporter_name: '张三', reporter_department: '检测部' });
    assert.deepEqual(ok.errors, {});
    assert.deepEqual(ok.data, { reporter_name: '张三', reporter_department: '检测部' });
});

test('个人信息：写坏的 meta 也不会让界面出现空白署名', async () => {
    assert.deepEqual(profile.normalize(null), { ...DEFAULT_PROFILE });
    assert.deepEqual(profile.normalize({ reporter_name: '', reporter_department: null }),
        { ...DEFAULT_PROFILE });
    assert.deepEqual(profile.normalize({ reporter_name: '  张三  ' }),
        { reporter_name: '张三', reporter_department: DEFAULT_PROFILE.reporter_department });
});

test('报告人显示格式：「姓名（部门）」', () => {
    assert.equal(profileLabel({ reporter_name: '张三', reporter_department: '检测部' }), '张三（检测部）');
    assert.equal(profileLabel({}), `${DEFAULT_PROFILE.reporter_name}（${DEFAULT_PROFILE.reporter_department}）`);
});

test('个人信息配置页：路由 / 外壳 / 路径都对', () => {
    const route = resolveRoute('#/me/profile');
    assert.equal(route.name, 'me.profile');
    assert.equal(pathFor('me.profile'), '#/me/profile');
    assert.equal(chromeFor('me.profile'), 'form', '表单页要隐藏底部 Tab、改用固定操作条');
    assert.equal(resolveRoute('#/me/profile').route.tab, 'me', '底部导航仍高亮「我的」');
});

/* --------------------------------------------------------------------------
 * 3. 开发 / 课程痕迹不许漏进交付版
 * ------------------------------------------------------------------------ */

/** 交付版不该出现的字样（页面文案、注释都在扫描范围内）。 */
const DEV_TRACES = [
    [/模块进度/, '开发期的里程碑进度表'],
    [/Zeyu\s*Jin/i, '开发者的名字（报告人默认值）'],
    [/结构工程部/, '开发期写死的部门'],
    [/NYU|Capstone/i, '课程 / 学校信息'],
    [/\bM[0-5]\b(?![\d.])/, '开发期里程碑编号（M0~M5）'],
];

test('index.html 与 manifest 里没有开发/课程痕迹', () => {
    for (const relative of ['index.html', 'manifest.webmanifest']) {
        const text = READ(relative);
        for (const [pattern, why] of DEV_TRACES) {
            assert.doesNotMatch(text, pattern, `${relative} 里还有${why}：${pattern}`);
        }
        assert.doesNotMatch(text, /Flask|webapp\/|python\s+app\.py/,
            `${relative} 里还留着参考实现（Flask）的说明 —— 交付版不该让客户去跑它`);
    }
});

test('源码里没有 console.log / console.debug / debugger（留 error/warn 供现场排错）', () => {
    const files = [...walk(APP_DIR), resolve(WEB_DIR, 'sw.js')];
    const violations = [];
    for (const file of files) {
        READ_FILE(file).split('\n').forEach((line, index) => {
            // 注释里的示例不算：只在"真的调用"时报
            const code = line.replace(/\/\/.*$/, '');
            if (/console\.(log|debug)\s*\(/.test(code) || /\bdebugger\b/.test(code)) {
                violations.push(`${file.slice(WEB_DIR.length).replace(/\\/g, '/')}:${index + 1}  ${line.trim()}`);
            }
        });
    }
    assert.deepEqual(violations, [], `交付版不该带调试输出：\n${violations.join('\n')}`);
});

test('源码里没有本地开发路径 / 本机地址', () => {
    const files = [
        ...walk(APP_DIR),
        resolve(WEB_DIR, 'sw.js'),
        resolve(WEB_DIR, 'index.html'),
        resolve(WEB_DIR, 'manifest.webmanifest'),
    ];
    const banned = [
        [/[A-Za-z]:\\\\|[A-Za-z]:\\[^\\]/, 'Windows 绝对路径'],
        [/\/Users\/|\/home\/\w+\//, 'Unix 绝对路径'],
        [/localhost:\d+|127\.0\.0\.1/, '本机地址'],
        [/D:\\project/i, '开发机路径'],
    ];
    const violations = [];
    for (const file of files) {
        const text = READ_FILE(file);
        for (const [pattern, why] of banned) {
            if (pattern.test(text)) {
                violations.push(`${file.slice(WEB_DIR.length).replace(/\\/g, '/')}  ${why}（${pattern}）`);
            }
        }
    }
    assert.deepEqual(violations, [], `交付版不该带本地开发路径：\n${violations.join('\n')}`);
});

/* `readFileSync` 只在上面那几个 helper 里用到；单拎出来是为了错误信息好看。 */
function READ_FILE(path) {
    return readFileSync(path, 'utf8');
}
