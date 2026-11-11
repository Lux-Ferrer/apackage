/* Service Worker：把应用壳缓存成**离线可用**。
 *
 * 三条设计决定，都是踩过坑之后才这么写的：
 *
 * 1. **缓存清单是算出来的**（`assets/shell.js`，由构建脚本生成）。
 *    SW 最常见的失败是"漏了一个文件"：在线一切正常，一断网就白屏，且现场很难复现。
 *    清单里带**内容指纹版本号** —— 改了任何一个被缓存的文件，装的就是新 SW，旧缓存被清掉。
 *
 * 2. **不自动 skipWaiting**。装了新版本立刻接管，会让正在填表的用户页面在脚下被换掉。
 *    新版本先 `waiting`，页面通过 `postMessage({type:'SKIP_WAITING'})` 决定何时切。
 *
 * 3. **不缓存图片，也不缓存导出产物**。隐患图片走 IndexedDB（不是 URL）；
 *    导出的 .docx 是内存里生成的 Blob，根本不经过网络。
 *    这里只处理"应用壳"——少一点缓存，就少一份"离线看到的是旧文件"的困惑。
 *
 * 本文件是 **module worker**（注册时 `type: 'module'`），因此可以直接 import 生成好的清单。
 */

import { SHELL_ASSETS, SHELL_VERSION } from './assets/shell.js';

const CACHE_NAME = `curtain-wall-shell-${SHELL_VERSION}`;

/** 把相对路径变成绝对 URL（相对 SW 自己的位置，也就是 web/ 根目录）。 */
const absolute = (relative) => new URL(relative, self.location.href).href;

self.addEventListener('install', (event) => {
    event.waitUntil((async () => {
        const cache = await caches.open(CACHE_NAME);
        // `reload` 绕过 HTTP 缓存：装 SW 的时候要拿到**真的**最新文件，
        // 否则会把浏览器里过期的副本固化进离线缓存（这个坑很难查）。
        await cache.addAll(SHELL_ASSETS.map((relative) => new Request(absolute(relative), {
            cache: 'reload',
        })));
        // 注意：这里**不**调用 skipWaiting()，理由见文件头第 2 条
    })());
});

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        // 清掉旧版本的壳缓存（只清我们自己的前缀，别碰别人的）
        const names = await caches.keys();
        await Promise.all(names
            .filter((name) => name.startsWith('curtain-wall-shell-') && name !== CACHE_NAME)
            .map((name) => caches.delete(name)));
        await self.clients.claim();
    })());
});

self.addEventListener('message', (event) => {
    if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
    if (event.data?.type === 'VERSION') event.source?.postMessage({ type: 'VERSION', version: SHELL_VERSION });
});

self.addEventListener('fetch', (event) => {
    const request = event.request;
    if (request.method !== 'GET') return;                       // 写操作交给网络
    const url = new URL(request.url);
    if (url.origin !== self.location.origin) return;             // 跨域不插手
    if (request.headers.has('range')) return;                    // 分段请求（大文件下载）直接放行

    // 导航请求：先给缓存里的 index.html（离线也能打开应用），没有再走网络
    if (request.mode === 'navigate') {
        event.respondWith((async () => {
            const cache = await caches.open(CACHE_NAME);
            const cached = await cache.match(absolute('index.html'));
            if (cached) return cached;
            try {
                return await fetch(request);
            } catch {
                // 真的什么都没有时给一句人话，而不是浏览器的恐龙页
                return new Response(
                    '<!doctype html><meta charset="utf-8"><title>离线</title>'
                    + '<p style="font:16px/1.6 system-ui;padding:24px">'
                    + '本机还没有缓存好这个应用。请先联网打开一次，之后即可离线使用。</p>',
                    { status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8' } },
                );
            }
        })());
        return;
    }

    // 其余同源 GET：缓存优先（壳是"内容指纹"版本化的，命中的必然是最新那份）
    event.respondWith((async () => {
        const cache = await caches.open(CACHE_NAME);
        const cached = await cache.match(request, { ignoreSearch: true });
        if (cached) return cached;
        return fetch(request);
    })());
});
