/* 存储配额与持久化：策略判定、文案、以及"问不到就放行"的降级。
 *
 * 这一层全是策略，没有像素也没有 IO，所以注入假 `navigator.storage` 即可完整覆盖。
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
    QUOTA_BLOCK_RATIO, QUOTA_WARN_RATIO, checkUploadQuota, describeStorage, formatBytes,
    isPersisted, quotaStatus, requestPersistence,
} from '../app/storage.js';

const MB = 1024 * 1024;

/** 假 storage：usage / quota 给定，persist 结果给定。 */
function fakeStorage({ usage, quota, persisted = false, unsupported = false, persistThrows = false } = {}) {
    if (unsupported) return { persisted: async () => null };
    return {
        estimate: async () => ({ usage, quota }),
        persisted: async () => persisted,
        persist: async () => {
            if (persistThrows) throw new Error('拒绝');
            return true;
        },
    };
}

test('formatBytes：人类可读，非法值给占位符', () => {
    assert.equal(formatBytes(0), '0 B');
    assert.equal(formatBytes(512), '512 B');
    assert.equal(formatBytes(2048), '2.0 KB');
    assert.equal(formatBytes(5 * MB), '5.0 MB');
    assert.equal(formatBytes(200 * MB), '200 MB');
    assert.equal(formatBytes(3 * 1024 * MB), '3.0 GB');
    assert.equal(formatBytes(undefined), '—');
    assert.equal(formatBytes(-1), '—');
});

test('quotaStatus：算得出已用/可用/比例', async () => {
    const status = await quotaStatus(fakeStorage({ usage: 50 * MB, quota: 100 * MB, persisted: true }));
    assert.equal(status.supported, true);
    assert.equal(status.usage, 50 * MB);
    assert.equal(status.free, 50 * MB);
    assert.equal(status.ratio, 0.5);
    assert.equal(status.persisted, true);
});

test('quotaStatus：浏览器不提供估算 → supported=false，不假装 0/0 是"满了"', async () => {
    const status = await quotaStatus(fakeStorage({ unsupported: true }));
    assert.equal(status.supported, false);
    assert.equal(status.quota, 0);
    assert.equal(status.persisted, null);
});

test('quotaStatus：estimate 抛错也要安全降级（隐私模式）', async () => {
    const status = await quotaStatus({
        estimate: async () => { throw new Error('不可用'); },
        persisted: async () => null,
    });
    assert.equal(status.supported, false);
    assert.equal(status.ratio, 0);
});

test('checkUploadQuota：充足 → ok 放行', async () => {
    const result = await checkUploadQuota(20 * MB, {
        storage: fakeStorage({ usage: 10 * MB, quota: 1000 * MB }),
    });
    assert.equal(result.allowed, true);
    assert.equal(result.level, 'ok');
});

test('checkUploadQuota：超过警告线 → warn，但**仍然放行**', async () => {
    const usage = Math.round(1000 * MB * (QUOTA_WARN_RATIO + 0.01));
    const result = await checkUploadQuota(20 * MB, {
        storage: fakeStorage({ usage, quota: 1000 * MB }),
    });
    assert.equal(result.allowed, true, '警告不该挡住现场记录');
    assert.equal(result.level, 'warn');
    assert.match(result.message, /建议尽快导出备份/);
});

test('checkUploadQuota：超过拦截线 → block，并提示先备份再清理', async () => {
    const usage = Math.round(1000 * MB * (QUOTA_BLOCK_RATIO + 0.001));
    const result = await checkUploadQuota(20 * MB, {
        storage: fakeStorage({ usage, quota: 1000 * MB }),
    });
    assert.equal(result.allowed, false);
    assert.equal(result.level, 'block');
    assert.match(result.message, /导出备份/);
});

test('checkUploadQuota：剩余空间放不下这一张 → block（比例还很低也拦）', async () => {
    const result = await checkUploadQuota(20 * MB, {
        storage: fakeStorage({ usage: 990 * MB, quota: 1000 * MB, persisted: true }),
    });
    assert.equal(result.allowed, false);
    assert.match(result.message, /剩余空间不足/);
});

test('checkUploadQuota：问不到容量 → 放行但标 unknown（不能因为问不到就不让记录）', async () => {
    const result = await checkUploadQuota(20 * MB, { storage: fakeStorage({ unsupported: true }) });
    assert.equal(result.allowed, true);
    assert.equal(result.level, 'unknown');
    assert.match(result.message, /不提供容量信息/);
});

test('isPersisted：拿不到 API 返回 null（未知不能当成已授权）', async () => {
    assert.equal(await isPersisted(null), null);
    assert.equal(await isPersisted({}), null);
    assert.equal(await isPersisted({ persisted: async () => { throw new Error('x'); } }), null);
    assert.equal(await isPersisted(fakeStorage({ persisted: true })), true);
});

test('requestPersistence：不支持时说清 Safari 的"添加到主屏幕"路径', async () => {
    const result = await requestPersistence({});
    assert.equal(result.supported, false);
    assert.equal(result.persisted, null);
    assert.match(result.reason, /添加到主屏幕/);
});

test('requestPersistence：申请失败也要给可读原因（不抛到 UI）', async () => {
    const result = await requestPersistence(fakeStorage({ persistThrows: true }));
    assert.equal(result.supported, true);
    assert.equal(result.persisted, null);
    assert.match(result.reason, /申请持久化失败/);
});

test('describeStorage：未获持久化时必须出现"系统可能清理数据"的警告', async () => {
    const { lines, status } = await describeStorage({
        storage: fakeStorage({ usage: 5 * MB, quota: 100 * MB, persisted: false }),
    });
    assert.equal(status.supported, true);
    assert.match(lines[0], /已存储 5\.0 MB \/ 100 MB/);
    assert.match(lines[1], /未获持久化授权/);
    assert.match(lines[1], /7 天/);
});

test('describeStorage：已获持久化时不吓唬用户', async () => {
    const { lines } = await describeStorage({
        storage: fakeStorage({ usage: 5 * MB, quota: 100 * MB, persisted: true }),
    });
    assert.match(lines[1], /不会自动清理/);
    assert.ok(!lines.some((line) => line.includes('⚠️')));
});
