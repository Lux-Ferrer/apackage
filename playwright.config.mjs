/* 真实浏览器端到端测试（Playwright）。
 *
 * 为什么必须有这一层
 * ------------------
 * 前面 226 个 Node 测试跑在 jsdom 上，而 jsdom **没有** canvas、`<dialog>.showModal`、
 * Service Worker、真实的 IndexedDB 实现、真实的层叠顺序。M5 的四个真机 bug 里，
 * 三个都是"jsdom 比浏览器宽容"造成的（见 `docs/management/M5-设计.md` §9）。
 * 这一层用**真浏览器**（本机已装的 Edge / Chrome，不下载额外浏览器）跑一遍交付包，
 * 把"只有真环境才暴露"的问题挡在客户之前。
 *
 * 被测试的对象是**交付包本身**：`web/e2e/serve-release.mjs` 把 `dist/*.zip` 解开，
 * 再用包里自带的那份 `serve_static.py` 起服务。所以这里验的是"客户拿到的东西"，
 * 不是"仓库里的源码目录"。
 *
 * 移动端视口：375×812（iPhone X/11 Pro 的逻辑分辨率，DPR 3，触摸）。这是客户
 * 现场最可能用的形态；桌面端的结构性变化（≥960px）另有断言（见 02-layout）。
 */
import { defineConfig } from '@playwright/test';

const PORT = Number(process.env.E2E_PORT ?? 8123);
/** 用本机已装的浏览器：`msedge`（默认，Windows 自带）或 `chrome`。 */
const CHANNEL = process.env.E2E_CHANNEL ?? 'msedge';

export default defineConfig({
    testDir: './web/e2e',
    testMatch: '**/*.spec.mjs',
    /* 负载用例（20 份报告 + 图片现压 + 导出）在慢机器上会接近 2 分钟 */
    timeout: 300_000,
    expect: { timeout: 20_000 },
    /* 串行：负载用例会吃满 CPU，并发只会让耗时数字失真 */
    fullyParallel: false,
    workers: 1,
    retries: 0,
    reporter: [
        ['list'],
        ['json', { outputFile: '_work/e2e/results.json' }],
        ['html', { outputFolder: '_work/e2e/html', open: 'never' }],
    ],
    use: {
        baseURL: `http://127.0.0.1:${PORT}`,
        channel: CHANNEL,
        headless: true,
        viewport: { width: 375, height: 812 },
        deviceScaleFactor: 3,
        isMobile: true,
        hasTouch: true,
        locale: 'zh-CN',
        timezoneId: 'Asia/Shanghai',
        acceptDownloads: true,
        serviceWorkers: 'allow',
        screenshot: 'only-on-failure',
        trace: 'retain-on-failure',
    },
    webServer: {
        command: `node web/e2e/serve-release.mjs --port ${PORT}`,
        url: `http://127.0.0.1:${PORT}/`,
        /* ⚠️ 必须是 false：`true` 时如果端口上还挂着一个**上一轮**的服务，
         * 测试会安静地跑在"旧的解包副本"上 —— 我因此白跑过两轮（改了 CSS/代码却测的是旧包）。
         * 让它直接报"端口已占用"，比悄悄测错对象好得多。 */
        reuseExistingServer: false,
        timeout: 180_000,
        stdout: 'pipe',
        stderr: 'pipe',
    },
    globalSetup: './web/e2e/global-setup.mjs',
});
