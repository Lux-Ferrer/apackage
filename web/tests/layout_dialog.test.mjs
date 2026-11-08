/* "只有真机会踩"的第二批：断点/控件层面的问题。
 *
 * 与 mobile_render.test.mjs 同源（那批是 hidden 与 SVG 命名空间），这批是：
 *
 * 1. **桌面端表单页**：≥960px 时 `app.css` 把正文留白收回到 32px（因为没有底部 Tab 了），
 *    但表单页仍有一条 56px 的固定操作条 → 最后一个输入框/页脚被压住。
 *    移动端看不出来（那时留白本来就是 68px），所以这也是"某个断点才炸"的一类。
 *    修法：`main.js` 在 body 上挂 `has-action-bar`，`m5.css` 在 ≥960px 补回留白。
 *
 * 2. **确认弹窗被连点两次**：真机上双击"删除"很常见，而 `showModal()` 对已打开的 dialog
 *    会**同步抛** InvalidStateError，外层没有地方接 → 一次未捕获错误（按钮看起来没反应）。
 *    jsdom 没有 showModal，测试一律走 confirm() 降级，所以这条分支天然测不到 ——
 *    这里用"给 dialog 装一个假 showModal"的方式把真实分支逼出来。
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { JSDOM } from 'jsdom';

/* --------------------------------------------------------------------------
 * 1. 桌面端留白：规则存在 + 类名切换
 * ------------------------------------------------------------------------ */

test('m5.css 在 ≥960px 给带操作条的页面补回正文留白', () => {
    const stripCssComments = (text) => text.replace(/\/\*[\s\S]*?\*\//g, '');
    const css = stripCssComments(readFileSync(new URL('../styles/m5.css', import.meta.url), 'utf8'));

    const desktop = /@media\s*\(min-width:\s*960px\)\s*\{([\s\S]*)\}/.exec(css);
    assert.ok(desktop, 'm5.css 里应有 ≥960px 的媒体查询');
    const body = desktop[1];
    assert.match(body, /body\.has-action-bar\s+main\.wrap/, '正文留白要按"有操作条"补回');
    assert.match(body, /body\.has-action-bar\s+\.foot/, '页脚也要补，否则被操作条盖住');

    // 同时确认 app.css 确实在 960px 收回了留白（否则这条规则就是多余的 —— 也要知道）
    const appCss = stripCssComments(readFileSync(new URL('../styles/app.css', import.meta.url), 'utf8'));
    assert.match(appCss, /main\.wrap,\s*\.foot\s*\{\s*padding-bottom:\s*32px/, 'app.css 在桌面收回了留白');
});

test('main.js：渲染时按"表单壳/浏览壳"切换 body 上的 has-action-bar', () => {
    const source = readFileSync(new URL('../app/main.js', import.meta.url), 'utf8');
    assert.match(source, /classList\.toggle\('has-action-bar'/,
        '渲染时要维护 body 上的 has-action-bar（m5.css 的桌面留白靠它）');
    assert.match(source, /tabbar\.hidden = isForm/, '底部 Tab 的显隐也要跟着同一个判断走');
});

/* --------------------------------------------------------------------------
 * 2. 确认弹窗：连点两次不能抛
 * ------------------------------------------------------------------------ */

test('确认弹窗：已打开时再弹一次会被忽略，不会抛 InvalidStateError', async () => {
    const dom = new JSDOM(`<!doctype html><body>
        <dialog id="confirm-dialog" class="dialog">
          <form method="dialog">
            <h2 id="confirm-title">请确认</h2>
            <p id="confirm-message"></p>
            <button value="cancel">取消</button>
            <button value="confirm" id="confirm-ok">确认</button>
          </form>
        </dialog>
    </body>`, { url: 'http://localhost:8080/' });
    const { window } = dom;

    // 装一个"像浏览器"的 showModal：打开已打开的 dialog 就抛 InvalidStateError（真实行为）
    // 同时**计数**：不数调用次数就测不出"重复弹窗"—— `dialog.open` 守卫与
    // `try/catch` 兜底都会让第二次调用返回 false，两种情况从返回值上看不出区别。
    const proto = window.HTMLDialogElement.prototype;
    let showModalCalls = 0;
    delete proto.showModal;
    proto.showModal = function showModal() {
        showModalCalls += 1;
        if (this.open) throw new window.DOMException('already open', 'InvalidStateError');
        this.setAttribute('open', '');
    };
    proto.close = function close(value) {
        if (value !== undefined) this.returnValue = value;
        this.removeAttribute('open');
        this.dispatchEvent(new window.Event('close'));
    };

    for (const key of ['window', 'document', 'Node', 'Element', 'HTMLElement', 'Event']) {
        Object.defineProperty(globalThis, key, {
            value: window[key], configurable: true, writable: true,
        });
    }

    const { confirmDialog } = await import('../app/ui/dialog.js');
    const dialog = window.document.getElementById('confirm-dialog');

    // 第一次：正常打开，等待用户点"确认"
    const first = confirmDialog({ message: '删除？', okText: '确认删除' });
    assert.equal(dialog.hasAttribute('open'), true, '第一次应该真的打开');

    // 第二次（模拟双击）：必须立刻拿到 false，且**不能再打开一次**
    const second = await confirmDialog({ message: '删除？', okText: '确认删除' });
    assert.equal(second, false, '重复弹窗直接忽略（返回 false，调用方当作"没确认"）');
    // 真正的不变量：弹窗没有被叠第二次。否则会出现两个 close 监听、
    // 而且第二次调用把 returnValue 清成 ''，用户点的"确认"就丢了。
    assert.equal(showModalCalls, 1, '重复点击不该再次调用 showModal（否则弹窗被叠开）');

    // 用户点"确认" → 第一次的 promise 解析为 true
    dialog.close('confirm');
    assert.equal(await first, true);

    // 关掉之后可以再次正常弹出（不是一次性的）
    const third = confirmDialog({ message: '再删一次？' });
    assert.equal(dialog.hasAttribute('open'), true, '关闭后应能再次打开');
    assert.equal(showModalCalls, 2, '关闭后重新打开会正常再调一次 showModal');
    dialog.close('cancel');
    assert.equal(await third, false);
});
