/* 备份与恢复（`app/import-export.js`）：导出 zip → 只看不写 → 覆盖导入。
 *
 * **这个测试文件是补出来的**，起因是一个真机 bug：
 * `inspectBackup()` 曾经写成 `zip.files.filter(...)`，而 JSZip 的 `zip.files` 是
 * **对象**不是数组 → `TypeError: zip.files.filter is not a function`。
 * 界面在导入前必须先调它，于是「导入备份」这条唯一的救命通道 100% 失败。
 * 而它之所以能在 200+ 个测试与 16 条闸门下活着，是因为**备份导入当时一条测试都没有** ——
 * 跟 M5 里 `boot()` 没被测到是同一类漏洞：**没写测试的功能，等于没验过**。
 *
 * 所以这里锁五件事：
 *  1. 往返：导出 → 只看不写（条数/图片对账）→ 导入空库 → 数据一条不少；
 *  2. 覆盖语义：导入会清空并替换，而不是追加；
 *  3. 图片：zip 里少的图要计入 `missingImages`，多出来的要计入 `orphanImages`；
 *  4. 坏备份要被拦住（不是 zip / 缺 backup.json / 格式不对 / 版本更新）；
 *  5. 导出不带缩略图（派生值），导入时靠原图重建。
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import JSZip from 'jszip';

import { STORE } from '../app/db.js';
import {
    BACKUP_FORMAT, BackupError, backupFilename, exportBackup, importBackup, inspectBackup,
} from '../app/import-export.js';
import { freshDb, makeDefect, makeProject, makeRecord } from './helpers.mjs';

/** 一份 1×1 的 PNG（真字节，用来验证"原图随备份走、缩略图重建"）。 */
const PNG_1PX = Uint8Array.from([
    0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
    0xde, 0x00, 0x00, 0x00, 0x0c, 0x49, 0x44, 0x41, 0x54, 0x08, 0xd7, 0x63, 0xf8, 0xcf, 0xc0, 0x00,
    0x00, 0x03, 0x01, 0x01, 0x00, 0x18, 0xdd, 0x8d, 0xb0, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4e,
    0x44, 0xae, 0x42, 0x60, 0x82,
]);

/** 假的图像编解码器：Node 里没有 canvas，缩略图重建走替身（同 `ui.test.mjs` 的思路）。 */
const FAKE_CODEC = {
    decode: async () => ({ source: {}, width: 1, height: 1, orientation: 1 }),
    createCanvas: () => ({
        getContext: () => ({
            save() {}, restore() {}, setTransform() {}, fillRect() {}, fillStyle: '', drawImage() {},
        }),
        convertToBlob: async () => new Blob([PNG_1PX], { type: 'image/jpeg' }),
    }),
};

/** 一张图片记录（`images` store 的主键就是 key）。 */
function imageRecord(id = 'abc123_隐患照片.png') {
    return {
        id, blob: new Blob([PNG_1PX], { type: 'image/png' }),
        thumb: null, width: 1, height: 1, bytes: PNG_1PX.length, mime: 'image/png',
        created_at: '2026-09-20 10:24:00',
    };
}

/** 导出一份备份并转成 JSZip 能直接吃的字节。 */
async function exportBytes(db) {
    const backup = await exportBackup(db);
    return { bytes: new Uint8Array(await backup.blob.arrayBuffer()), filename: backup.filename };
}

/* --------------------------------------------------------------------------
 * 1. 往返
 * ------------------------------------------------------------------------ */

test('备份文件名：幕墙检测备份_日期_时间.zip', () => {
    assert.equal(backupFilename(new Date(2026, 8, 25, 10, 30)),
        '幕墙检测备份_20260925_1030.zip');
});

test('导出 → 只看不写 → 导入空库：项目/记录/读数/报告一条不少', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db, { project_no: 'BK-1', house_name: '备份楼' });
    await makeRecord(db, projectId);
    await makeDefect(db, { project_id: String(projectId) });

    const { bytes } = await exportBytes(db);

    /* 只看不写：条数对得上，且不写库 */
    const info = await inspectBackup(bytes);                 // ← 这里以前会抛 TypeError
    assert.equal(info.counts.projects, 1);
    assert.equal(info.counts.records, 1);
    assert.equal(info.counts.readings, 1);
    assert.equal(info.counts.defects, 1);
    assert.equal(info.counts.images, 0);
    assert.deepEqual(info.missingImages, []);
    assert.deepEqual(info.orphanImages, []);
    assert.match(info.exportedAt, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);

    /* 导入到另一个空库 */
    const target = await freshDb();
    const result = await importBackup(target, bytes);
    assert.equal(result.imported.projects, 1);
    assert.equal(result.imported.records, 1);
    assert.equal(result.imported.readings, 1);
    assert.equal(result.imported.defects, 1);
    assert.equal(result.imageFailed, 0);

    const rows = await target.read([STORE.projects], (ctx) => ctx.getAll(STORE.projects));
    assert.equal(rows.length, 1);
    assert.equal(rows[0].house_name, '备份楼');
    const defects = await target.read([STORE.defects], (ctx) => ctx.getAll(STORE.defects));
    assert.equal(defects[0].defect_type, '密封胶开裂');

    db.close();
    target.close();
});

test('导入是**覆盖**而不是追加：目标库里原有的数据会被清掉', async () => {
    const source = await freshDb();
    await makeProject(source, { project_no: 'SRC-1', house_name: '来源楼' });
    const { bytes } = await exportBytes(source);

    const target = await freshDb();
    await makeProject(target, { project_no: 'OLD-1', house_name: '旧楼' });
    await makeProject(target, { project_no: 'OLD-2', house_name: '旧楼2' });

    await importBackup(target, bytes);
    const rows = await target.read([STORE.projects], (ctx) => ctx.getAll(STORE.projects));
    assert.equal(rows.length, 1, '旧数据应被清空');
    assert.equal(rows[0].project_no, 'SRC-1');

    source.close();
    target.close();
});

/* --------------------------------------------------------------------------
 * 2. 图片：随包走、缩略图重建、缺失与孤儿要报出来
 * ------------------------------------------------------------------------ */

test('图片：原图进备份，缩略图不进；导入时用原图重建缩略图', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db, { project_no: 'IMG-BK', house_name: '图片备份楼' });
    await makeDefect(db, { project_id: String(projectId) }, imageRecord());

    const { bytes } = await exportBytes(db);
    const zip = await JSZip.loadAsync(bytes);
    const names = Object.keys(zip.files);
    assert.ok(names.some((name) => name.startsWith('images/') && !name.endsWith('/')),
        '备份里应有原图文件');
    const backupJson = JSON.parse(await zip.file('backup.json').async('string'));
    assert.equal(Object.prototype.hasOwnProperty.call(backupJson.tables.images[0], 'thumb'), false,
        '缩略图是派生值，不该进备份');

    const target = await freshDb();
    const result = await importBackup(target, bytes, { pipeline: FAKE_CODEC });
    assert.equal(result.imported.images, 1);
    const images = await target.read([STORE.images], (ctx) => ctx.getAll(STORE.images));
    assert.equal(images.length, 1);
    assert.ok(images[0].blob, '原图应恢复');
    assert.ok(images[0].thumb, '缩略图应从原图重建出来');

    db.close();
    target.close();
});

test('对账：zip 里缺图 → missingImages；多出未登记的图 → orphanImages', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db, { project_no: 'AUDIT', house_name: '对账楼' });
    await makeDefect(db, { project_id: String(projectId) }, imageRecord('keep_保留.png'));

    const { bytes } = await exportBytes(db);
    const zip = await JSZip.loadAsync(bytes);
    // ① 删掉登记在册的那张 ② 塞一张没登记的图（模拟手工改过的备份）
    for (const name of Object.keys(zip.files)) {
        if (name.startsWith('images/') && !name.endsWith('/')) delete zip.files[name];
    }
    zip.file('images/intruder_多余.png', PNG_1PX);
    const tampered = new Uint8Array(await zip.generateAsync({ type: 'uint8array' }));

    const info = await inspectBackup(tampered);
    assert.deepEqual(info.missingImages, ['keep_保留.png']);
    assert.deepEqual(info.orphanImages, ['intruder_多余.png']);
    assert.equal(info.imageFiles, 1);

    // 导入时缺图不该让整体失败：报告保留、图片缺失（走降级）
    const target = await freshDb();
    const result = await importBackup(target, tampered, { pipeline: FAKE_CODEC });
    assert.equal(result.imported.defects, 1);
    assert.equal(result.imageFailed, 1);

    db.close();
    target.close();
});

test('图片字节坏了：只丢这张的缩略图，原图与数据都保留', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db, { project_no: 'BAD-IMG', house_name: '坏图楼' });
    await makeDefect(db, { project_id: String(projectId) }, imageRecord('bad_坏图.png'));

    const { bytes } = await exportBytes(db);
    const zip = await JSZip.loadAsync(bytes);
    for (const name of Object.keys(zip.files)) {
        if (name.startsWith('images/') && !name.endsWith('/')) zip.file(name, new Uint8Array([1, 2, 3]));
    }
    const tampered = new Uint8Array(await zip.generateAsync({ type: 'uint8array' }));

    // 编解码器遇到坏字节会抛错 → 缩略图重建失败，但原图仍入库
    const brokenCodec = { decode: async () => { throw new Error('坏图'); } };
    const target = await freshDb();
    const result = await importBackup(target, tampered, { pipeline: brokenCodec });
    assert.equal(result.imported.images, 1);
    const images = await target.read([STORE.images], (ctx) => ctx.getAll(STORE.images));
    assert.equal(images[0].thumb, null, '缩略图重建失败时留空');
    assert.ok(images[0].blob, '原图仍在（后续可"重建全部缩略图"）');

    db.close();
    target.close();
});

/* --------------------------------------------------------------------------
 * 3. 坏备份要被拦住（而不是把库清空一半）
 * ------------------------------------------------------------------------ */

test('坏备份：不是 zip / 缺 backup.json / 格式不对 / 版本更新 —— 四种都被拦住', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db, { project_no: 'NEG', house_name: '负例楼' });
    await makeDefect(db, { project_id: String(projectId) });

    await assert.rejects(() => inspectBackup(new Uint8Array([1, 2, 3, 4])),
        (error) => error instanceof BackupError && /不是\s*一个有效的 zip/.test(error.message));

    const noJson = new JSZip();
    noJson.file('readme.txt', 'oops');
    const noJsonBytes = new Uint8Array(await noJson.generateAsync({ type: 'uint8array' }));
    await assert.rejects(() => inspectBackup(noJsonBytes),
        (error) => error instanceof BackupError && /缺少 backup\.json/.test(error.message));

    const wrongFormat = new JSZip();
    wrongFormat.file('backup.json', JSON.stringify({ format: 'something-else', version: 1 }));
    const wrongFormatBytes = new Uint8Array(await wrongFormat.generateAsync({ type: 'uint8array' }));
    await assert.rejects(() => inspectBackup(wrongFormatBytes),
        (error) => error instanceof BackupError && /不是本工具的备份文件/.test(error.message));

    const future = new JSZip();
    future.file('backup.json', JSON.stringify({
        format: BACKUP_FORMAT, version: 99, tables: { projects: [] },
    }));
    const futureBytes = new Uint8Array(await future.generateAsync({ type: 'uint8array' }));
    await assert.rejects(() => inspectBackup(futureBytes),
        (error) => error instanceof BackupError && /比当前程序/.test(error.message));

    // 关键：坏文件进来之后，**库里什么都没变**（不会先清空再报错）
    const rows = await db.read([STORE.defects], (ctx) => ctx.getAll(STORE.defects));
    assert.equal(rows.length, 1);
    db.close();
});

test('导入失败不会留在半截状态：坏 zip 直接抛错，库里数据不动', async () => {
    const db = await freshDb();
    const projectId = await makeProject(db, { project_no: 'ROLLBACK', house_name: '回滚楼' });
    await makeDefect(db, { project_id: String(projectId) });

    await assert.rejects(() => importBackup(db, new Uint8Array([9, 9, 9])),
        (error) => error instanceof BackupError);

    const projects = await db.read([STORE.projects], (ctx) => ctx.getAll(STORE.projects));
    const defects = await db.read([STORE.defects], (ctx) => ctx.getAll(STORE.defects));
    assert.equal(projects.length, 1);
    assert.equal(defects.length, 1);
    db.close();
});
