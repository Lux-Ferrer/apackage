/* 应用内确认弹窗 + 顶部提示条（flash）。
 *
 * 移植自 Flask 侧的 `static/js/app.js`（`data-confirm` 语义）与 Jinja 的
 * `get_flashed_messages()`。换到纯前端之后两者的**载体变了**（不再是表单提交/重定向，
 * 而是"先弹窗，确认后再执行那个动作"），但**用户看到的东西必须一致**：
 * 同一个弹窗、同一句文案、同样要写清"会删掉几条"。
 *
 * 弹窗不可用时（`<dialog>` 不支持）退化为原生 `confirm()` —— 功能不受影响。
 */

import { byId, clear, h } from './dom.js';

/**
 * 弹一个确认框，返回用户是否确认。
 *
 * 用法：`if (!await confirmDialog({message, okText})) return;`
 * —— 比 Flask 的 `data-confirm` 少一层间接（那边是拦截 submit 再补一次 submit）。
 */
export function confirmDialog({ message, okText = '确认删除', title = '请确认' }) {
    const dialog = byId('confirm-dialog');
    if (!dialog || typeof dialog.showModal !== 'function') {
        return Promise.resolve(globalThis.confirm ? globalThis.confirm(message) : true);
    }
    byId('confirm-title').textContent = title;
    byId('confirm-message').textContent = message;
    byId('confirm-ok').textContent = okText;
    dialog.returnValue = '';                 // 清掉上次的返回值，防止 Esc 被当成"确认"

    return new Promise((resolve) => {
        const done = () => {
            dialog.removeEventListener('close', done);
            resolve(dialog.returnValue === 'confirm');
        };
        dialog.addEventListener('close', done);
        dialog.showModal();
    });
}

/** 提示条：`flash('已保存')` 或 `flash('保存失败', 'error')`。
 *
 * ⚠️ 提示必须**跨过一次渲染**：`flash()` 后面往往紧跟 `ctx.navigate()` / `ctx.refresh()`，
 * 而渲染会重建 DOM。如果渲染时把提示清空，用户就永远看不到"已保存"这类回执
 * （这正是第一版的行为，属于真 bug）。所以这里用一个小队列：
 * `flash()` 入队并渲染，`renderFlashes()` 在每次渲染后重放仍未过期的条目。
 */
const FLASH_TTL = 3500;
let pending = [];

/** 入队一条提示并立刻渲染。 */
export function flash(message, kind = 'ok') {
    const entry = { message, kind, at: Date.now() };
    pending.push(entry);
    renderFlashes();
    const timer = globalThis.setTimeout(() => {
        pending = pending.filter((item) => item !== entry);
        renderFlashes();
    }, FLASH_TTL);
    // Node 里 `setTimeout` 会拖住进程退出（测试跑完还要多等 3.5 秒）；浏览器里没有 unref，
    // 这一行自然被跳过。
    if (typeof timer?.unref === 'function') timer.unref();
    return entry;
}

/** 把未过期的提示重绘到 `#flashes`（每次路由渲染后调用）。 */
export function renderFlashes() {
    const box = byId('flashes');
    if (!box) return 0;
    const now = Date.now();
    pending = pending.filter((item) => now - item.at < FLASH_TTL);
    clear(box);
    for (const item of pending) {
        box.appendChild(h('div.flash', {
            class: item.kind === 'error' ? 'flash-error' : null,
            text: item.message,
        }));
    }
    box.hidden = pending.length === 0;
    return pending.length;
}

/** 清空全部提示（测试与"强制清屏"用）。 */
export function clearFlashes() {
    pending = [];
    renderFlashes();
}
