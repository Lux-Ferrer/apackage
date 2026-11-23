/* DownloadSaver（写公共下载目录）分支的测试。
 * 单独一个文件，避免把 native_shell 里那几条（浏览器不变 / Filesystem 回退）搅在一起。
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { downloadBlob } from '../app/export.js';

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

const bytes = () => new Uint8Array([0x50, 0x4b, 0x03, 0x04]);
const fakeDoc = () => ({ body: {}, createElement: () => ({ click() {} }) });

test('原生壳：有 DownloadSaver 时优先写「下载/幕墙检测」，不再走 Filesystem + Share', async () => {
    const restoreReader = stubFileReader();
    const calls = { saveAndShare: [], writeFile: [], share: [] };
    const restore = stubCapacitor({
        isNativePlatform: () => true,
        Plugins: {
            DownloadSaver: {
                saveAndShare: async (payload) => {
                    calls.saveAndShare.push(payload);
                    return { saved: true, shared: false, displayPath: '下载/幕墙检测/报告.docx' };
                },
            },
            Filesystem: { writeFile: async (payload) => { calls.writeFile.push(payload); return { uri: 'file:///cache/x' }; } },
            Share: { share: async (payload) => { calls.share.push(payload); } },
        },
    });
    try {
        const result = downloadBlob(bytes(), '报告.docx', { document: fakeDoc() });
        assert.equal(result.native, true);
        const saved = await result.done;

        assert.equal(calls.saveAndShare.length, 1, '应当调用一次 DownloadSaver.saveAndShare');
        assert.equal(calls.writeFile.length, 0, '不该再往 App 缓存里写第二份');
        assert.equal(calls.share.length, 0, '分享由插件内部处理，JS 不再重复调 Share');

        const payload = calls.saveAndShare[0];
        assert.equal(payload.fileName, '报告.docx');
        assert.equal(payload.mime, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
        assert.equal(payload.data, Buffer.from(bytes()).toString('base64'));

        assert.equal(saved.via, 'downloads');
        assert.equal(saved.saved, true);
        assert.equal(saved.shared, false, '没有可分享应用时 shared=false（Toast 由原生弹）');
        assert.equal(saved.displayPath, '下载/幕墙检测/报告.docx');
    } finally {
        restore();
        restoreReader();
    }
});

test('原生壳：DownloadSaver 写下载目录失败 → 回退到缓存 + 分享，并记录原因', async () => {
    const restoreReader = stubFileReader();
    const calls = { writeFile: [], share: [] };
    const restore = stubCapacitor({
        isNativePlatform: () => true,
        Plugins: {
            DownloadSaver: {
                saveAndShare: async () => { throw new Error('系统拒绝了下载目录写入'); },
            },
            Filesystem: { writeFile: async (payload) => { calls.writeFile.push(payload); return { uri: 'file:///cache/ok' }; } },
            Share: { share: async (payload) => { calls.share.push(payload); } },
        },
    });
    try {
        const saved = await downloadBlob(bytes(), 'x.docx', { document: fakeDoc() }).done;

        assert.equal(saved.via, 'cache', '插件失败后应退回缓存路径');
        assert.match(saved.fallbackReason, /下载目录/);
        assert.equal(calls.writeFile.length, 1);
        assert.equal(calls.writeFile[0].directory, 'CACHE');
        assert.equal(calls.share.length, 1);
        assert.equal(calls.share[0].url, 'file:///cache/ok');
    } finally {
        restore();
        restoreReader();
    }
});

test('原生壳：DownloadSaver 失败且没有 Filesystem → done reject（不假装成功）', async () => {
    const restoreReader = stubFileReader();
    const restore = stubCapacitor({
        isNativePlatform: () => true,
        Plugins: {
            DownloadSaver: { saveAndShare: async () => { throw new Error('系统拒绝了下载目录写入'); } },
        },
    });
    try {
        const result = downloadBlob(bytes(), 'x.docx', { document: fakeDoc() });
        await assert.rejects(result.done, /DownloadSaver|Filesystem/);
    } finally {
        restore();
        restoreReader();
    }
});

test('原生壳：插件都没有 → 报错信息明确', async () => {
    const restoreReader = stubFileReader();
    const restore = stubCapacitor({ isNativePlatform: () => true, Plugins: {} });
    try {
        const result = downloadBlob(bytes(), 'x.docx', { document: fakeDoc() });
        await assert.rejects(result.done, /DownloadSaver|Filesystem/);
    } finally {
        restore();
        restoreReader();
    }
});
