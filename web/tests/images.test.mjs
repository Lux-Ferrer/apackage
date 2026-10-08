/* 图片导入链路：校验 → 配额 → 现算缩略图 → 落库；以及级联删除与批量重建缩略图。
 *
 * 这层是"数据层 + 管线"的接缝，最值得锁的是**顺序纪律**：
 * 解码与缩略图必须在开事务之前算完（IndexedDB 的事务会在 await 非 IDB Promise 时自动提交）。
 * 所以这里用假编解码器验证"库里的记录长什么样"，并用真 IndexedDB（fake-indexeddb）验证落库。
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { STORE } from '../app/db.js';
import {
    ImageError, QuotaError, allKeys, attachmentView, get, importImage, prepareUpload,
    rebuildThumbnails,
} from '../app/repo/images.js';
import * as defects from '../app/repo/defects.js';
import { freshDb, makeProject } from './helpers.mjs';

const MB = 1024 * 1024;

/** 假编解码器：解码尺寸给定，编码记录尺寸并返回一个"像 Blob"的对象。 */
function fakeCodec({ width, height, orientation = 1 }) {
    const encoded = [];
    return {
        encoded,
        decode: async (blob) => ({ source: { blob }, width, height, orientation }),
        createCanvas: (canvasWidth, canvasHeight) => ({
            width: canvasWidth,
            height: canvasHeight,
            getContext: () => ({
                save() {}, restore() {}, setTransform() {}, fillRect() {},
                fillStyle: '', drawImage() {},
            }),
            convertToBlob: async ({ type, quality }) => {
                encoded.push({ width: canvasWidth, height: canvasHeight, type, quality });
                return { size: canvasWidth * canvasHeight, type, thumb: true };
            },
        }),
    };
}

function fakeFile(name, size = 1024, type = 'image/jpeg') {
    return { name, size, type };
}

/* --------------------------------------------------------------------------
 * 导入
 * ------------------------------------------------------------------------ */

test('importImage：原图原样入库，附带一张 240px 缩略图与摆正后的尺寸', async () => {
    const db = await freshDb();
    const file = fakeFile('隐患照片.jpg', 2_345_678);
    const record = await importImage(db, file, {
        uuid: 'abcdef0123456789abcdef0123456789',
        pipeline: fakeCodec({ width: 3200, height: 2400 }),
        checkQuota: false,
    });

    assert.equal(record.id, 'abcdef0123456789abcdef0123456789_隐患照片.jpg');
    assert.equal(record.blob, file, '原图是证据：入库的必须是上传对象本身');
    assert.equal(record.bytes, 2_345_678);
    assert.deepEqual([record.width, record.height], [3200, 2400]);
    assert.match(record.created_at, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);

    const stored = await get(db, record.id);
    assert.deepEqual(stored.blob, file, '原图字节原样入库（读回来是结构化克隆的副本）');
    assert.ok(stored.thumb, '缩略图必须落库（设计文档 3.4 的有意偏离）');
    assert.deepEqual(await allKeys(db), [record.id]);
});

test('importImage：竖拍照片按 EXIF 摆正后再入库尺寸', async () => {
    const db = await freshDb();
    const record = await importImage(db, fakeFile('竖拍.jpg'), {
        uuid: 'ffeeddccbbaa99887766554433221100',
        pipeline: fakeCodec({ width: 600, height: 800, orientation: 6 }),
        checkQuota: false,
    });
    assert.deepEqual([record.width, record.height], [800, 600]);
});

test('importImage：校验不过 → ImageError，且**什么都没写进库**', async () => {
    const db = await freshDb();
    await assert.rejects(
        () => importImage(db, fakeFile('坏文件.txt'), { checkQuota: false }),
        (error) => error instanceof ImageError && /格式只支持/.test(error.message));
    assert.deepEqual(await allKeys(db), []);
});

test('importImage：剩余空间放不下这一张 → QuotaError（附配额状态供 UI 展示）', async () => {
    const db = await freshDb();
    // 配额很小时（浏览器可能只给 100MB），一张 20MB 的原图就可能放不下；
    // 此时比例才 85%（还在警告线），必须由"剩余空间"这条判据拦住。
    const storage = {
        estimate: async () => ({ usage: 85 * MB, quota: 100 * MB }),
        persisted: async () => true,
    };
    await assert.rejects(
        () => importImage(db, fakeFile('现场.jpg', 20 * MB), {
            pipeline: fakeCodec({ width: 800, height: 600 }),
            quotaOptions: { storage },
        }),
        (error) => error instanceof QuotaError && /剩余空间不足/.test(error.message)
            && error.status.supported === true);
    assert.deepEqual(await allKeys(db), []);
});

test('importImage：比例超过拦截线 → QuotaError（提示先导出备份再清理）', async () => {
    const db = await freshDb();
    const storage = {
        estimate: async () => ({ usage: 990 * MB, quota: 1000 * MB }),
        persisted: async () => false,
    };
    await assert.rejects(
        () => importImage(db, fakeFile('现场.jpg', 1 * MB), {
            pipeline: fakeCodec({ width: 800, height: 600 }),
            quotaOptions: { storage },
        }),
        (error) => error instanceof QuotaError && /导出备份/.test(error.message));
    assert.deepEqual(await allKeys(db), []);
});

test('prepareUpload：只算不写（供"报告 + 图片同一事务"使用）', async () => {
    const db = await freshDb();
    const record = await prepareUpload(db, fakeFile('现场.jpg'), {
        uuid: '00112233445566778899aabbccddeeff',
        pipeline: fakeCodec({ width: 800, height: 600 }),
        checkQuota: false,
    });
    assert.equal(record.id, '00112233445566778899aabbccddeeff_现场.jpg');
    assert.deepEqual(await allKeys(db), [], 'prepareUpload 不该落库');
});

test('报告 + 图片同一事务写入：任一步失败一起回滚，不留孤儿图片', async () => {
    const db = await freshDb();
    const project = await makeProject(db);
    const { data } = await defects.parseForm(db, {
        defect_type: '密封胶开裂', project_part: '东立面', risk_level: '高',
        rectification_plan: '更换', project_id: String(project.id),
    });
    const image = await prepareUpload(db, fakeFile('现场.jpg'), {
        uuid: 'aabbccddeeff00112233445566778899',
        pipeline: fakeCodec({ width: 800, height: 600 }),
        checkQuota: false,
    });
    const defectId = await defects.create(db, data, image);

    assert.ok(await get(db, image.id));
    const stored = await defects.get(db, defectId);
    assert.equal(stored.image_path, image.id);

    // 删报告 → 图片一并删除（对应 M4 的"先删库后删文件"，这里一个事务搞定）
    await defects.remove(db, defectId);
    assert.deepEqual(await allKeys(db), []);
});

test('报告写库失败（隐患等级非法）时，图片也不该留下', async () => {
    const db = await freshDb();
    const { data } = await defects.parseForm(db, {
        defect_type: '密封胶开裂', project_part: '东立面', risk_level: '高',
        rectification_plan: '更换',
    });
    const image = await prepareUpload(db, fakeFile('现场.jpg'), {
        uuid: 'aabbccddeeff00112233445566778899',
        pipeline: fakeCodec({ width: 800, height: 600 }),
        checkQuota: false,
    });
    // assertRiskLevel 是同步抛的（CHECK 约束的等价物），所以用 throws 而不是 rejects
    assert.throws(() => defects.create(db, { ...data, risk_level: '特高' }, image),
        /隐患等级无效/);
    assert.deepEqual(await allKeys(db), []);
});

/* --------------------------------------------------------------------------
 * 缩略图重建与附页视图
 * ------------------------------------------------------------------------ */

test('rebuildThumbnails：重建缩略图但不动原图与业务字段', async () => {
    const db = await freshDb();
    const file = fakeFile('现场.jpg', 4096);
    const record = await importImage(db, file, {
        uuid: '11223344556677889900aabbccddeeff',
        pipeline: fakeCodec({ width: 3200, height: 2400 }),
        checkQuota: false,
    });

    const codec = fakeCodec({ width: 3200, height: 2400 });
    const result = await rebuildThumbnails(db, { pipeline: { ...codec, thumbMaxPixels: 480 } });

    assert.deepEqual(result, { total: 1, rebuilt: 1, failed: 0 });
    assert.deepEqual(codec.encoded, [
        { width: 480, height: 360, type: 'image/jpeg', quality: 0.75 },
    ]);
    const after = await get(db, record.id);
    assert.deepEqual(after.blob, file, '原图不变');
    assert.equal(after.bytes, 4096);
    assert.equal(after.created_at, record.created_at);
});

test('rebuildThumbnails：一张坏图不影响其余（failed 计数，不抛错）', async () => {
    const db = await freshDb();
    await importImage(db, fakeFile('好的.jpg'), {
        uuid: '11223344556677889900aabbccddeeff',
        pipeline: fakeCodec({ width: 800, height: 600 }),
        checkQuota: false,
    });
    await db.write([STORE.images], (ctx) => ctx.put(STORE.images,
        { id: '坏图.jpg', blob: null, thumb: null, width: 1, height: 1 }));

    const result = await rebuildThumbnails(db, {
        pipeline: {
            decode: async (blob) => {
                if (!blob) throw new Error('坏图');
                return { source: {}, width: 800, height: 600, orientation: 1 };
            },
            createCanvas: () => ({
                getContext: () => ({ save() {}, restore() {}, setTransform() {}, fillRect() {}, drawImage() {} }),
                convertToBlob: async () => ({ size: 1 }),
            }),
        },
    });
    assert.deepEqual(result, { total: 2, rebuilt: 1, failed: 1 });
});

test('attachmentView：图片缺失时 missing=true，但原名仍可追溯', () => {
    const defect = { image_path: 'abcdef_隐患照片.png', project_part: '东立面' };
    const view = attachmentView(defect, null);
    assert.equal(view.original_name, '隐患照片.png');
    assert.equal(view.missing, true);
    assert.equal(view.image, null);
    assert.equal(defects.imageFileText(view), '隐患照片.png（文件缺失）');

    const withImage = attachmentView(defect, { id: defect.image_path, blob: {} });
    assert.equal(withImage.missing, false);
    assert.equal(defects.imageFileText(withImage), '隐患照片.png');
    assert.equal(defects.imageFileText({ ...withImage, compressed: true }), '隐患照片.png（已压缩）');
});
