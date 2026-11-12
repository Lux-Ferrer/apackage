/* 软键盘（真机）：把底部固定操作条抬到键盘之上。
 *
 * 问题（安卓真机实测）
 * --------------------
 * 表单页的底部操作条是 `position: fixed; bottom: 0` —— 它跟着**布局视口**走。
 * 而软键盘弹起时，浏览器只会缩小**视觉视口**（`visualViewport`），布局视口不变
 * （实测：`innerHeight` 774 一直不变，`visualViewport.height` 从 774 掉到 ~430）。
 * 结果：`保存 / 取消` 被键盘整个盖住，用户必须先收起键盘才能点保存 ——
 * 现场录入时要反复收起键盘，体验很差。
 *
 * 做法
 * ----
 * 监听 `visualViewport` 的 resize/scroll，把"键盘占掉的高度"写成 CSS 变量
 * `--keyboard-inset`，`styles/m5.css` 里让 `.action-bar` 往上平移这么多：
 *
 *     .action-bar { transform: translateY(calc(-1 * var(--keyboard-inset, 0px))); }
 *
 * 两条纪律：
 *  1. **没有 `visualViewport` 就什么也不做**（很老的浏览器、以及 jsdom）——
 *     不能因为问不到键盘高度就把操作条挪走；
 *  2. 只在 inset 明显大于 0 时才加 `body.keyboard-open`，避免地址栏收缩那几十像素
 *     也被当成键盘（那会让操作条莫名其妙地跳一下）。
 */

/**
 * 计算键盘占掉的高度（CSS px）。
 *
 * @param {number} innerHeight 布局视口高度
 * @param {{height: number, offsetTop?: number}|null} visualViewport 视觉视口
 * @returns {number} 0 表示没有键盘（或浏览器不提供视觉视口）
 */
export function keyboardInset(innerHeight, visualViewport) {
    if (!visualViewport || typeof visualViewport.height !== 'number') return 0;
    const visible = visualViewport.height + (visualViewport.offsetTop ?? 0);
    if (!Number.isFinite(innerHeight) || !Number.isFinite(visible)) return 0;
    return Math.max(0, Math.round(innerHeight - visible));
}

/** inset 超过这个值才认为"键盘真的弹起来了"（地址栏收缩通常只有几十像素）。 */
export const KEYBOARD_THRESHOLD = 80;

/**
 * 开始跟踪键盘高度。返回一个"停止跟踪"的函数（测试与热重载用）。
 */
export function trackKeyboardInset({ window: win = globalThis.window, document: doc = globalThis.document } = {}) {
    const viewport = win?.visualViewport;
    const root = doc?.documentElement;
    if (!viewport || !root) return () => {};

    const apply = () => {
        const inset = keyboardInset(win.innerHeight, viewport);
        root.style.setProperty('--keyboard-inset', `${inset}px`);
        doc.body?.classList.toggle('keyboard-open', inset > KEYBOARD_THRESHOLD);
    };

    viewport.addEventListener('resize', apply);
    viewport.addEventListener('scroll', apply);
    apply();
    return () => {
        viewport.removeEventListener('resize', apply);
        viewport.removeEventListener('scroll', apply);
    };
}
