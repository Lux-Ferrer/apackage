/* 软键盘遮挡：把底部操作条抬到键盘之上的那点计算。
 *
 * 这一条来自**真机实测**（安卓模拟器 + 真实输入法）：
 *   键盘弹起时 `window.innerHeight` 不变（774），只有 `visualViewport.height` 掉到约 430，
 *   于是 `position: fixed; bottom: 0` 的「保存 / 取消」被键盘整个盖住。
 *
 * jsdom 里没有 `visualViewport`（它的视口是常量），所以这里的单元测试锁的是**纯函数**
 * 与"有没有把 CSS 变量写对"；真实键盘下的效果由
 * `web/e2e/android-remote.mjs` 的键盘用例在模拟器里验（那条用例会量
 * `--keyboard-inset` 与操作条的实际位置）。
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { KEYBOARD_THRESHOLD, keyboardInset, trackKeyboardInset } from '../app/ui/viewport.js';

test('键盘高度：没有 visualViewport（老浏览器 / jsdom）→ 0', () => {
    assert.equal(keyboardInset(774, null), 0);
    assert.equal(keyboardInset(774, undefined), 0);
    assert.equal(keyboardInset(774, {}), 0);
});

test('键盘高度：没有键盘时是 0，弹起后等于被占掉的高度', () => {
    assert.equal(keyboardInset(774, { height: 774, offsetTop: 0 }), 0);
    assert.equal(keyboardInset(774, { height: 430, offsetTop: 0 }), 344);
    // 视觉视口被滚下去时，offsetTop 也要算进来
    assert.equal(keyboardInset(774, { height: 430, offsetTop: 20 }), 324);
    // 异常值不产生负数
    assert.equal(keyboardInset(774, { height: 900 }), 0);
    assert.equal(keyboardInset(Number.NaN, { height: 430 }), 0);
});

test('跟踪器：把 inset 写进 --keyboard-inset，并按阈值加 body.keyboard-open', () => {
    const listeners = new Map();
    const properties = new Map();
    const classes = new Set();
    const viewport = {
        height: 774,
        offsetTop: 0,
        addEventListener: (type, handler) => listeners.set(type, handler),
        removeEventListener: (type) => listeners.delete(type),
    };
    const win = { innerHeight: 774, visualViewport: viewport };
    const doc = {
        documentElement: { style: { setProperty: (name, value) => properties.set(name, value) } },
        body: {
            classList: {
                toggle: (name, enabled) => { if (enabled) classes.add(name); else classes.delete(name); },
            },
        },
    };

    const stop = trackKeyboardInset({ window: win, document: doc });

    // 初始：没有键盘
    assert.equal(properties.get('--keyboard-inset'), '0px');
    assert.equal(classes.has('keyboard-open'), false);
    assert.equal(typeof listeners.get('resize'), 'function', '应监听 visualViewport 的 resize');

    // 键盘弹起：innerHeight 不变，视觉视口变矮
    viewport.height = 430;
    listeners.get('resize')();
    assert.equal(properties.get('--keyboard-inset'), '344px');
    assert.equal(classes.has('keyboard-open'), true);

    // 键盘收起
    viewport.height = 774;
    listeners.get('resize')();
    assert.equal(properties.get('--keyboard-inset'), '0px');
    assert.equal(classes.has('keyboard-open'), false);

    // 只有"地址栏收缩"级别的高度变化，不该让操作条跳
    viewport.height = 774 - KEYBOARD_THRESHOLD + 10;
    listeners.get('resize')();
    assert.equal(classes.has('keyboard-open'), false, '小变化不该被当成键盘');
    assert.equal(properties.get('--keyboard-inset'), `${KEYBOARD_THRESHOLD - 10}px`);

    stop();
    assert.equal(listeners.size, 0, '停止后应把监听摘掉');
});

test('跟踪器：浏览器没有 visualViewport 时是空操作，不抛错', () => {
    const stop = trackKeyboardInset({ window: {}, document: {} });
    assert.equal(typeof stop, 'function');
    stop();
});

test('CSS：操作条确实按 --keyboard-inset 抬高，且键盘打开时给正文让出位置', async () => {
    const { readFileSync } = await import('node:fs');
    const css = readFileSync(new URL('../styles/m5.css', import.meta.url), 'utf8');
    assert.match(css, /\.action-bar\s*\{[^}]*bottom:\s*var\(--keyboard-inset/,
        'm5.css 里应让 .action-bar 的 bottom 跟着 --keyboard-inset 走');
    assert.doesNotMatch(css, /\.action-bar\s*\{[^}]*transform:[^}]*--keyboard-inset/,
        '不要用 transform 抬它：会给固定元素建新层叠上下文，安卓上实测点击命中会错位');
    assert.match(css, /body\.keyboard-open main\.wrap\s*\{[^}]*padding-bottom:[^}]*--keyboard-inset/,
        '键盘打开时应给正文补足留白，否则操作条会盖住表单末尾');
});
