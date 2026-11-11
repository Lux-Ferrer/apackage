/* hash 路由（M5 设计 §7 决策 4）。
 *
 * 为什么是 hash 而不是 History API
 * --------------------------------
 * 静态托管下 `#/projects/1` 不需要服务器把未知路径 fallback 到 index.html ——
 * 用 `python -m http.server` 就能跑，也能直接丢进任意静态空间。
 * History API 要配 404 fallback，而"本工具能放在任何地方跑"是这一版的目标之一。
 *
 * 本模块**只有纯函数**（不碰 DOM、不监听事件）：`main.js` 负责监听 `hashchange` 与渲染。
 * 这样路由表可以脱离浏览器单独测试 —— 路由错配是"页面打不开"类 bug 的主要来源。
 */

import { PRODUCT } from './product.js';

/**
 * 路由表。字段含义：
 *   name     路由名（`pathFor()` 用它生成链接）
 *   pattern  路径模板，`:` 开头是参数
 *   tab      底部/顶部导航该高亮哪个 Tab（对应 Flask 的 `active_tab` 推导，见 UI 设计 1.2）
 *   chrome   `'tabbar'`（浏览类页面，显示底部 Tab）或 `'form'`（表单类页面，改用底部操作条）
 *   title    页面标题（写进 document.title，与 Flask 侧的 `{% block title %}` 对应）
 */
export const ROUTES = Object.freeze([
    { name: 'projects.index', pattern: '/projects', tab: 'projects', chrome: 'tabbar', title: '项目' },
    { name: 'projects.new', pattern: '/projects/new', tab: 'projects', chrome: 'form', title: '新建项目' },
    { name: 'projects.detail', pattern: '/projects/:id', tab: 'projects', chrome: 'tabbar' },
    { name: 'projects.edit', pattern: '/projects/:id/edit', tab: 'projects', chrome: 'form', title: '编辑项目' },
    { name: 'records.choose', pattern: '/projects/:id/records/new', tab: 'projects', chrome: 'form', title: '选择检测记录模板' },
    { name: 'records.new', pattern: '/projects/:id/records/new/:template', tab: 'projects', chrome: 'form', title: '新增检测记录' },
    { name: 'records.edit', pattern: '/records/:id/edit', tab: 'projects', chrome: 'form', title: '编辑检测记录' },
    { name: 'reports.index', pattern: '/reports', tab: 'reports', chrome: 'tabbar', title: '报告管理' },
    { name: 'reports.new', pattern: '/reports/new', tab: 'reports', chrome: 'form', title: '缺陷检测填报' },
    { name: 'reports.detail', pattern: '/reports/:id', tab: 'reports', chrome: 'tabbar', title: '缺陷报告' },
    { name: 'me.index', pattern: '/me', tab: 'me', chrome: 'tabbar', title: '我的' },
    { name: 'me.profile', pattern: '/me/profile', tab: 'me', chrome: 'form', title: '个人信息配置' },
    { name: 'me.data', pattern: '/me/data', tab: 'me', chrome: 'tabbar', title: '数据管理' },
    { name: 'pages.about', pattern: '/about', tab: 'me', chrome: 'tabbar', title: '关于' },
]);

/** 导航项（与 Flask 侧 `_nav.html` 一一对应：一个定义、两处渲染）。 */
export const NAV_ITEMS = Object.freeze([
    { key: 'projects', label: '项目', href: '#/projects' },
    { key: 'reports', label: '报告', href: '#/reports' },
    { key: 'me', label: '我的', href: '#/me' },
]);

/** 落地路径：与 Flask 的 `GET / → /projects/` 一致（UI 设计 1.4）。 */
export const DEFAULT_PATH = '/projects';

/** 把 `location.hash` 拆成 `{path, query}`。 */
export function parseLocation(hash) {
    let raw = String(hash ?? '');
    if (raw.startsWith('#')) raw = raw.slice(1);
    if (!raw.startsWith('/')) raw = `/${raw}`;

    const [pathPart, queryPart] = raw.split('?');
    const path = normalizePath(pathPart);
    const query = {};
    if (queryPart) {
        for (const pair of queryPart.split('&')) {
            if (!pair) continue;
            const [key, value = ''] = pair.split('=');
            query[decodeURIComponent(key)] = decodeURIComponent(value.replace(/\+/g, ' '));
        }
    }
    return { path, query };
}

/** 去掉重复斜杠与结尾斜杠（`/projects/` 与 `/projects` 是同一个页面）。 */
export function normalizePath(path) {
    const cleaned = String(path ?? '').replace(/\/{2,}/g, '/');
    if (cleaned.length > 1 && cleaned.endsWith('/')) return cleaned.slice(0, -1);
    return cleaned || '/';
}

/**
 * 把路径匹配到路由。
 *
 * @returns {{name: string, params: object, route: object}|null} 匹配不到返回 null（→ 404 页）
 */
export function matchPath(path) {
    const normalized = normalizePath(path);
    const segments = normalized.split('/').filter(Boolean);

    for (const route of ROUTES) {
        const patternSegments = route.pattern.split('/').filter(Boolean);
        if (patternSegments.length !== segments.length) continue;

        const params = {};
        let matched = true;
        for (let index = 0; index < patternSegments.length; index += 1) {
            const pattern = patternSegments[index];
            if (pattern.startsWith(':')) {
                params[pattern.slice(1)] = decodeURIComponent(segments[index]);
            } else if (pattern !== segments[index]) {
                matched = false;
                break;
            }
        }
        if (matched) return { name: route.name, params, route };
    }
    return null;
}

/** 由路由名 + 参数生成 `#/...` 链接（视图里一律用它，不手拼字符串）。 */
export function pathFor(name, params = {}, query = null) {
    const route = ROUTES.find((item) => item.name === name);
    if (!route) throw new Error(`未知路由：${name}`);
    const path = route.pattern.replace(/:(\w+)/g, (_whole, key) => {
        if (params[key] === undefined || params[key] === null) {
            throw new Error(`路由 ${name} 缺少参数 ${key}`);
        }
        return encodeURIComponent(params[key]);
    });
    const search = query
        ? Object.entries(query)
            .filter(([, value]) => value !== null && value !== undefined && value !== '')
            .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
            .join('&')
        : '';
    return `#${path}${search ? `?${search}` : ''}`;
}

/** 该路由高亮哪个 Tab（`records.*` 归「项目」，`reports/defects` 归「报告」）。 */
export function activeTab(routeName) {
    const route = ROUTES.find((item) => item.name === routeName);
    return route ? route.tab : 'projects';
}

/** 该路由用哪种"外壳"：底部 Tab 还是表单页的底部操作条。 */
export function chromeFor(routeName) {
    const route = ROUTES.find((item) => item.name === routeName);
    return route ? route.chrome : 'tabbar';
}

/** 页面标题（`<title>` 与顶栏用）。产品名来自 `product.js`，改版时只改那一处。 */
export function titleFor(routeName, extra = null) {
    const route = ROUTES.find((item) => item.name === routeName);
    const base = extra || (route ? route.title : '');
    return base ? `${base} - ${PRODUCT.name}` : PRODUCT.name;
}

/**
 * 当前路由信息（含参数）。
 *
 * @param {string} hash 传入是为了可测；浏览器里传 `location.hash`
 */
export function resolve(hash) {
    const { path, query } = parseLocation(hash);
    const matched = matchPath(path);
    if (!matched) return { name: null, params: {}, query, path, route: null };
    return { ...matched, query, path };
}
