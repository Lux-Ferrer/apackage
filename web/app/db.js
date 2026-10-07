/* IndexedDB 数据层：连接、建库、事务纪律。
 *
 * 这是**唯一允许打开事务**的模块。业务代码一律走 `withTransaction()` ——
 * 理由见下（"await 陷阱"），它是本项目 M5 迁移里最容易踩的一个坑。
 *
 * 与 SQLite 的对应关系（`webapp/schema.sql`）
 * ------------------------------------------
 *   projects             → store `projects`            + unique 索引 project_no
 *   measurement_records  → store `measurement_records` + 复合索引 [project_id, template_type, sort_order]
 *   thickness_readings   → store `thickness_readings`  + 复合 **unique** 索引 [record_id, face]
 *   defects              → store `defects`             + project_id / risk_level / created_at
 *   （原来是 uploads/ 目录）→ store `images`
 *   schema 版本           → store `meta`
 *
 * **IndexedDB 没有的东西**（都要在这里或 repo 层手工补）：
 *   - 外键与级联：`ON DELETE CASCADE` / `ON DELETE SET NULL` 全部手写，且必须**同一事务**；
 *   - CHECK 约束：`template_type IN (column,beam)` 与 `risk_level IN (高,中,低)` 只能在代码里校验；
 *   - NOT NULL / 默认值：由 repo 层保证。
 */

export const DB_NAME = 'curtain_wall';
export const DB_VERSION = 1;

export const STORE = Object.freeze({
    projects: 'projects',
    records: 'measurement_records',
    readings: 'thickness_readings',
    defects: 'defects',
    images: 'images',
    meta: 'meta',
});

/** 必须存在的 store：缺任何一个都说明库结构不对（对应 Python 的旧库检测）。 */
const REQUIRED_STORES = Object.freeze([
    STORE.projects, STORE.records, STORE.readings, STORE.defects, STORE.images, STORE.meta,
]);

/** 对应 sqlite3.IntegrityError：唯一约束冲突。 */
export class IntegrityError extends Error {
    constructor(message) {
        super(message);
        this.name = 'IntegrityError';
    }
}

/** 对应 Python 侧的 LookupError：记录不存在。 */
export class LookupError extends Error {
    constructor(message) {
        super(message);
        this.name = 'LookupError';
    }
}

/** 库结构不对（对应 Python 的"旧版 PoC 数据库"拒绝逻辑）。 */
export class SchemaError extends Error {
    constructor(message) {
        super(message);
        this.name = 'SchemaError';
    }
}

/**
 * 把 IDBRequest 包成 Promise。
 *
 * ⚠️ 这个 Promise 只能在 `withTransaction()` 内部 await —— 它 resolve 于微任务，
 * 事务仍然活跃（IndexedDB 只在"没有挂起请求 + 微任务清空"时提交）。
 */
export function request(idbRequest) {
    return new Promise((resolve, reject) => {
        idbRequest.onsuccess = () => resolve(idbRequest.result);
        idbRequest.onerror = () => reject(idbRequest.error);
    });
}

/** 等待事务真正结束（提交或回滚）。 */
function transactionDone(tx) {
    return new Promise((resolve, reject) => {
        tx.oncomplete = () => resolve();
        tx.onabort = () => reject(tx.error ?? new Error('事务被中止'));
        tx.onerror = () => reject(tx.error ?? new Error('事务出错'));
    });
}

const asArray = (value) => Array.from(value ?? []);

/* --------------------------------------------------------------------------
 * 请求级小工具（全部在事务内使用）
 * ------------------------------------------------------------------------ */
export const req = {
    get: (store, key) => request(store.get(key)),
    getAll: async (store, query) => asArray(await request(
        query === undefined ? store.getAll() : store.getAll(query))),
    put: (store, value) => request(store.put(value)),
    add: (store, value) => request(store.add(value)),
    delete: (store, key) => request(store.delete(key)),
    count: (store, query) => request(
        query === undefined ? store.count() : store.count(query)),
    clear: (store) => request(store.clear()),
};

/** 从索引读全部键。 */
async function indexKeys(index, query) {
    const keys = [];
    const source = (query === undefined)
        ? index.openKeyCursor()
        : (query instanceof IDBKeyRange ? index.openKeyCursor(query)
            : index.openKeyCursor(IDBKeyRange.only(query)));
    await new Promise((resolve, reject) => {
        source.onsuccess = () => {
            const cursor = source.result;
            if (!cursor) {
                resolve();
                return;
            }
            keys.push(cursor.primaryKey);
            cursor.continue();
        };
        source.onerror = () => reject(source.error);
    });
    return keys;
}

/** 按索引逐个删除（用于手写级联）。 */
async function deleteByIndex(index, query) {
    const keys = await indexKeys(index, query);
    const store = index.objectStore;
    for (const key of keys) {
        await req.delete(store, key);
    }
    return keys.length;
}

/** 按索引计数（`IDBIndex.count`）—— 报告统计与项目关联计数都走它。 */
async function countByIndex(index, query) {
    return request(query === undefined ? index.count() : index.count(query));
}

/** 按索引取记录（走游标，避免 getAll 对复合索引的参数差异）。 */
async function allByIndex(index, query) {
    const rows = [];
    const source = index.openCursor(
        query instanceof IDBKeyRange ? query : IDBKeyRange.only(query));
    await new Promise((resolve, reject) => {
        source.onsuccess = () => {
            const cursor = source.result;
            if (!cursor) {
                resolve();
                return;
            }
            rows.push(cursor.value);
            cursor.continue();
        };
        source.onerror = () => reject(source.error);
    });
    return rows;
}

/* --------------------------------------------------------------------------
 * 建库
 * ------------------------------------------------------------------------ */
function upgrade(idb, oldVersion, _newVersion, tx) {
    if (oldVersion < 1) {
        const projects = idb.createObjectStore(STORE.projects, { keyPath: 'id', autoIncrement: true });
        projects.createIndex('project_no', 'project_no', { unique: true });

        const records = idb.createObjectStore(STORE.records, { keyPath: 'id', autoIncrement: true });
        records.createIndex('project_id', 'project_id');
        records.createIndex('project_template_order', ['project_id', 'template_type', 'sort_order']);

        const readings = idb.createObjectStore(STORE.readings, { keyPath: 'id', autoIncrement: true });
        readings.createIndex('record_id', 'record_id');
        readings.createIndex('record_face', ['record_id', 'face'], { unique: true });

        const defects = idb.createObjectStore(STORE.defects, { keyPath: 'id', autoIncrement: true });
        defects.createIndex('project_id', 'project_id');
        defects.createIndex('risk_level', 'risk_level');
        defects.createIndex('created_at', 'created_at');

        idb.createObjectStore(STORE.images, { keyPath: 'id' });
        idb.createObjectStore(STORE.meta, { keyPath: 'key' });
    }
    // 将来升版本时在这里按 oldVersion 分支追加迁移（对应 schema.sql 的幂等建表 + 迁移脚本）
    tx.objectStore(STORE.meta).put({ key: 'schemaVersion', value: DB_VERSION });
}

/* --------------------------------------------------------------------------
 * 连接
 * ------------------------------------------------------------------------ */
export class Database {
    constructor(idb, name) {
        this.idb = idb;
        this.name = name;
        this._closed = false;
    }

    /**
     * 打开（必要时建库）。
     *
     * @param {{name?: string, version?: number, factory?: IDBFactory}} [options]
     *        `factory` 可注入（测试用 fake-indexeddb）。
     */
    static async open(options = {}) {
        const name = options.name ?? DB_NAME;
        const version = options.version ?? DB_VERSION;
        const factory = options.factory ?? globalThis.indexedDB;
        if (!factory) {
            throw new SchemaError('当前环境没有 IndexedDB（浏览器里请用 https 或 localhost 打开）');
        }

        const idb = await new Promise((resolve, reject) => {
            const openRequest = factory.open(name, version);
            openRequest.onupgradeneeded = (event) => {
                try {
                    upgrade(openRequest.result, event.oldVersion, event.newVersion, openRequest.transaction);
                } catch (error) {
                    openRequest.transaction.abort();
                    reject(error);
                }
            };
            openRequest.onsuccess = () => resolve(openRequest.result);
            openRequest.onerror = () => reject(openRequest.error);
            openRequest.onblocked = () => reject(new SchemaError(
                '数据库被另一个标签页占用，请关闭其它页面后重试'));
        });

        const db = new Database(idb, name);
        db.assertSchema();
        return db;
    }

    /**
     * 结构自检：缺 store 就明确报错，而不是留下一堆看不懂的空查询。
     *
     * 对应 Python 侧 `_reject_legacy_schema()` —— 那里的场景是"没重建的 PoC 旧库"，
     * 这里对应"用旧版本建的库 / 结构被外部改过"。
     */
    assertSchema() {
        const missing = REQUIRED_STORES.filter((name) => !this.idb.objectStoreNames.contains(name));
        if (missing.length) {
            throw new SchemaError(
                `数据库结构不完整（缺少 ${missing.join('、')}）。`
                + '若这是早期版本建的库，请先导出备份，再重建数据库后导入。');
        }
        return true;
    }

    close() {
        if (!this._closed) {
            this.idb.close();
            this._closed = true;
        }
    }

    /**
     * 在事务里执行 `fn`。**业务代码只能用这个入口开事务。**
     *
     * 纪律（踩过一次会很难查）：
     *  1. 事务内**只** await 由 `request()` 包装的 IDB 请求 —— 它 resolve 于微任务，
     *     事务仍活跃；
     *  2. 不要在事务里 await `fetch` / `setTimeout` / 用户交互 / 大对象的 `structuredClone`：
     *     IndexedDB 在"没有挂起请求 + 微任务清空"时会**自动提交**事务，之后再写就会抛
     *     `TransactionInactiveError`；
     *  3. 需要先算好的东西（如图片压缩）**在开事务之前**算完；
     *  4. `fn` 抛错 → 事务 `abort()`（整体回滚）并原样抛出。
     *
     * @param {string[]} storeNames
     * @param {'readonly'|'readwrite'} mode
     * @param {(ctx: object) => Promise<any>|any} fn
     */
    async withTransaction(storeNames, mode, fn) {
        if (this._closed) throw new SchemaError('数据库连接已关闭');
        if (typeof mode === 'function') {
            fn = mode;
            mode = 'readonly';
        }
        const names = Array.isArray(storeNames) ? storeNames : [storeNames];
        const tx = this.idb.transaction(names, mode);
        const ctx = {
            tx,
            store: (name) => tx.objectStore(name),
            index: (storeName, indexName) => tx.objectStore(storeName).index(indexName),
            req,
            allByIndex,
            countByIndex,
            indexKeys,
            deleteByIndex,
            /** 事务内按主键自增插入，返回新 id。 */
            insert: async (storeName, value) => request(tx.objectStore(storeName).add(value)),
            get: async (storeName, key) => request(tx.objectStore(storeName).get(key)),
            getAll: async (storeName, query) => asArray(await request(
                query === undefined ? tx.objectStore(storeName).getAll()
                    : tx.objectStore(storeName).getAll(query))),
            put: async (storeName, value) => request(tx.objectStore(storeName).put(value)),
            delete: async (storeName, key) => request(tx.objectStore(storeName).delete(key)),
            count: async (storeName, query) => request(
                query === undefined ? tx.objectStore(storeName).count()
                    : tx.objectStore(storeName).count(query)),
            clear: async (storeName) => request(tx.objectStore(storeName).clear()),
        };

        let result;
        try {
            result = await fn(ctx);
        } catch (error) {
            try {
                tx.abort();
            } catch { /* 事务可能已经结束 */ }
            throw error;
        }
        await transactionDone(tx);
        return result;
    }

    /** 只读事务的语法糖。 */
    read(storeNames, fn) {
        return this.withTransaction(storeNames, 'readonly', fn);
    }

    /** 读写事务的语法糖。 */
    write(storeNames, fn) {
        return this.withTransaction(storeNames, 'readwrite', fn);
    }

    async meta(key) {
        const row = await this.read([STORE.meta], (ctx) => ctx.get(STORE.meta, key));
        return row ? row.value : undefined;
    }
}

/** 把 IndexedDB 的约束错误翻译成领域错误（与 sqlite3.IntegrityError 对应）。 */
export function translateConstraintError(error, message) {
    if (error && error.name === 'ConstraintError') {
        return new IntegrityError(message ?? '违反唯一约束');
    }
    return error;
}

export default Database;
