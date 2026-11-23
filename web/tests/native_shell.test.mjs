/* 原生壳（Android APK / Capacitor）分支：只在壳里换行为，Web 端一个字节都不变。
 *
 * 这一条的背景是真机/WebView 的差异：
 *   Android WebView **不认** `<a download>`，也不处理 `blob:` 链接（DownloadListener 只接
 *   http/https）—— 导出 Word / 导出备份会静默失败（点了没反应、控制台也不报错）。
 *   所以在壳里改成 "Filesystem 写文件 + Share 拉起分享面板"。
 *
 * 这里锁三件事：
 *   1. 浏览器里（没有 `window.Capacitor`）行为与以前**完全一致**（Blob URL + a[download]）；
 *   2. 壳里走原生保存，且 `done` 能被 await（失败要能提示用户，不能吞）；
 *   3. 插件代理缺失时降级到 `nativePromise`，两者都没有就明确报错（而不是假装成功）。
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { downloadBlob, isNativeShell } from '../app/export.js';

/* ---------------- 测试替身 ---------------- */

/** 假 document：够 downloadBlob 用（createElement / appendChild / remove / click）。 */
function fakeDocument() {
    const created = [];
    const anchor = {
        href: '', download: '', rel: '', clicked: 0, removed: false,
        click() { this.clicked += 1; },
        remove() { this.removed = true; },
    };
    const doc = {
        body: { appendChild: () => anchor },
        createElement: (tag) => {
            created.push(tag);
            return anchor;
        },
    };
    return { doc, anchor, created };
}

/** 假 FileReader：把 Blob 的字节读成 data:URL（Node 的 Blob 有 arrayBuffer，没有 FileReader）。 */
function stubFileReader() {
    const original = globalThis.FileReader;
    globalThis.FileReader = class {
        readAsDataURL(blob) {
            blob.arrayBuffer().then((buffer) => {
                this.result = `data:${blob.type};base64,${Buffer.from(buffer).toString('base64')}`;
                this.onload?.();
            }).catch((error) => {
                this.error = error;
                this.onerror?.();
            });
        }
    };
    return () => {
        if (original === undefined) delete globalThis.FileReader;
        else globalThis.FileReader = original;
    };
}

function stubCapacitor(value) {
    const original = globalThis.Capacitor;
    globalThis.Capacitor = value;
    return () => {
        if (original === undefined) delete globalThis.Capacitor;
        else globalThis.Capacitor = original;
    };
}

const bytes = () => new Uint8Array([0x50, 0x4b, 0x03, 0x04]);   // "PK\x03\x04"，zip 头，够用

/* ---------------- 1. 浏览器里行为不变 ---------------- */

test('浏览器里：没有 window.Capacitor → 仍是 Blob URL + a[download]', () => {
    assert.equal(isNativeShell(), false);
    const { doc, anchor, created } = fakeDocument();
    assert.equal(typeof URL.createObjectURL, 'function', 'Node 18+ 应提供 createObjectURL');

    const result = downloadBlob(bytes(), '项目_检测报告.docx', { document: doc });

    assert.deepEqual(created, ['a'], '应当只创建一个 <a>');
    assert.match(result.url, /^blob:/, '返回的仍是 blob: URL');
    assert.equal(anchor.download, '项目_检测报告.docx');
    assert.equal(anchor.clicked, 1, '应当点一次');
    assert.equal(anchor.removed, true, '点完要摘掉节点');
    assert.equal(result.native, undefined, '浏览器里没有 native 标记');
    assert.equal(result.done, undefined, '浏览器里没有异步句柄（保持同步返回）');
});

test('浏览器里：Capacitor 存在但不是原生平台（网页版用 core 也是这种情形）→ 行为不变', () => {
    const restore = stubCapacitor({ isNativePlatform: () => false, Plugins: {} });
    try {
        const { doc, anchor } = fakeDocument();
        const result = downloadBlob(bytes(), 'a.docx', { document: doc });
        assert.match(result.url, /^blob:/);
        assert.equal(anchor.clicked, 1);
    } finally {
        restore();
    }
});

/* ---------------- 2. 壳里走原生保存 ---------------- */

test('原生壳：走 Filesystem.writeFile + Share，并且 done 可 await', async () => {
    const restoreReader = stubFileReader();
    const calls = { writeFile: [], share: [] };
    const restore = stubCapacitor({
        isNativePlatform: () => true,
        Plugins: {
            Filesystem: {
                writeFile: async (payload) => {
                    calls.writeFile.push(payload);
                    return { uri: `file:///data/cache/${payload.path}` };
                },
            },
            Share: {
                share: async (payload) => { calls.share.push(payload); },
            },
        },
    });
    try {
        const { doc, created } = fakeDocument();
        const result = downloadBlob(bytes(), '报告.docx', { document: doc });

        assert.equal(result.native, true, '应标记为原生保存');
        assert.equal(result.url, null, '壳里没有 blob URL');
        assert.equal(typeof result.done?.then, 'function', 'done 必须是 thenable');
        assert.deepEqual(created, [], '壳里不该创建 <a>（也不该点它）');

        await result.done;

        assert.equal(calls.writeFile.length, 1);
        const payload = calls.writeFile[0];
        assert.equal(payload.path, '报告.docx');
        assert.equal(payload.directory, 'CACHE', '写缓存目录才不需要存储权限');
        assert.equal(payload.recursive, true);
        assert.equal(payload.data, Buffer.from(bytes()).toString('base64'), '交给原生层的应是 base64');

        assert.equal(calls.share.length, 1);
        assert.equal(calls.share[0].url, 'file:///data/cache/报告.docx', '分享面板要拿到刚写出的文件');
    } finally {
        restore();
        restoreReader();
    }
});

test('原生壳：没有插件代理时用 nativePromise，且仍然先走 DownloadSaver', async () => {
    const restoreReader = stubFileReader();
    const calls = [];
    const restore = stubCapacitor({
        isNativePlatform: () => true,
        Plugins: {},                     // 没有代理
        nativePromise: async (plugin, method, payload) => {
            calls.push([plugin, method, payload]);
            return { saved: true, shared: true, displayPath: '下载/幕墙检测/x.zip' };
        },
    });
    try {
        const { doc } = fakeDocument();
        const result = downloadBlob(bytes(), 'x.zip', { document: doc });
        const saved = await result.done;

        // 桥接原语这条路径下，第一个被调用的应当是本地插件 DownloadSaver
        assert.deepEqual(calls.map(([plugin, method]) => `${plugin}.${method}`),
            ['DownloadSaver.saveAndShare']);
        assert.equal(countsKeyword(calls[0][2]), 1);
        assert.equal(saved.via, 'downloads');
        assert.equal(saved.shared, true);
    } finally {
        restore();
        restoreReader();
    }
});

function countsKeyword(payload) {
    return payload.mime ? 1 : 0;
}

test('原生壳：插件都没有 → done 明确 reject（不能假装保存成功）', async () => {
    const restoreReader = stubFileReader();
    const restore = stubCapacitor({ isNativePlatform: () => true, Plugins: {} });
    try {
        const { doc } = fakeDocument();
        const result = downloadBlob(bytes(), 'x.docx', { document: doc });
        await assert.rejects(result.done, /Filesystem/);
    } finally {
        restore();
        restoreReader();
    }
});

test('原生壳：用户取消分享不算失败（文件已经写好了）', async () => {
    const restoreReader = stubFileReader();
    const restore = stubCapacitor({
        isNativePlatform: () => true,
        Plugins: {
            Filesystem: { writeFile: async () => ({ uri: 'file:///cache/a' }) },
            Share: { share: async () => { throw new Error('Share canceled'); } },
        },
    });
    try {
        const { doc } = fakeDocument();
        const result = downloadBlob(bytes(), 'a.docx', { document: doc });
        await assert.doesNotReject(result.done);
    } finally {
        restore();
        restoreReader();
    }
});

/* ---------------- 3. Service Worker：壳里不注册 ---------------- */

test('壳里不注册 Service Worker（缓存会跨 APK 版本保留，导致"更新了还是旧界面"）', () => {
    const source = readFileSync(new URL('../app/main.js', import.meta.url), 'utf8');
    const body = source.slice(source.indexOf('async function registerServiceWorker'));
    const guard = body.slice(0, body.indexOf('navigator.serviceWorker.register'));
    assert.match(guard, /Capacitor\?\.isNativePlatform\?\.\(\)/,
        'registerServiceWorker 开头应判断原生壳并直接返回');
    assert.ok(guard.indexOf('isNativePlatform') < guard.indexOf('serviceWorker.register') ||
        guard.indexOf('isNativePlatform') >= 0, '判断要在注册之前');
});
