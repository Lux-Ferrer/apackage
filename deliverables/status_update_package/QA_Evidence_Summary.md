# QA Evidence Summary — Curtain Wall Inspection Report Tool v1.0.1

## At a glance

| Layer | Size | Result |
| --- | --- | --- |
| Python unit / integration (reference implementation) | **348 tests** | all green |
| Front-end Node tests (data layer, engine, images, backup, keyboard) | **239 tests** | all green |
| Layout-fidelity gates (`python tools/verify_all.py`, 16 steps) | **3 independent gates + 7 injected-defect controls** | **0 differences** vs the frozen baseline, 7/7 injections caught |
| Desktop real-browser E2E (Playwright, 375×812) | **21 cases** | all green, zero console errors |
| Android real-browser regression (MuMu + MAA taps + CDP) | **14 assertions** | all green, zero console errors |
| Defects found and fixed during delivery | **9** (3 × P0) | each has a regression test + a positive control |

Re-run everything with:

```powershell
python tools/verify_all.py     # 16 gates: 348 Python + 239 front-end tests
npm run test:e2e               # 21 desktop E2E cases against the delivered zip
npm run test:android           # 14 assertions on a real Android browser
```

Release package: `mcc-inspection-tool-v1.0.1.zip` — 53 files / 465 KB /
sha256 `245f5c92…` / offline cache version `e904c3b9321a`.

---

## Appendix — the original tables (Chinese, from the acceptance report, sections 4 and 5)

### 4. 质量证据（四层测试 + 三道闸门）

| 层级 | 规模 | 覆盖 | 结果 |
| --- | --- | --- | --- |
| Python 单元 / 集成 | **348 项** | 参考实现（Flask）全链路、版式规格、案例数据 | 全绿 |
| 前端 Node 测试 | **239 项** | 数据层、引擎、附页、图片管线、配额、路由、指纹、备份导入导出、平台假设、**软键盘 inset** | 全绿 |
| 版式闸门 | **16 条**（`tools/verify_all.py` 一条命令） | A 复刻冻结基线（含附页）/ B 对齐真实客户报告 / C 无 Python 自检 / 敏感性 7 项下毒 | **全部 0 差异** |
| 桌面真实浏览器 E2E | **21 项**（Playwright + 本机 Edge，375×812） | 主流程、移动端布局、边界负载、离线、图片管线、鲁棒性、数据安全 | 全绿 |
| 安卓模拟器回归 | **14 项断言**（MuMu + MAA 坐标点击 + CDP） | 主流程、真实相机、真实 `<dialog>`、备份导入、个人信息、PWA 安装、真软键盘 | 全绿，零控制台错误 |

关键量化结果（实测，非估算）：

| 场景 | 数据 |
| --- | --- |
| 含 20 份附页导出 | 0.93s，docx 59KB，20 张图全部嵌到 ≤1600px |
| 连续导出 ×3 | 0.82 / 0.89 / 0.87s（无退化、产物一致） |
| 40 条记录纯报告 | 0.12s，表格 42 行 |
| 主线程长任务 | 最长 50ms（无"以为死机"的卡顿） |
| 内存 | 20 次导出后 JS 堆 5→47MB；30 次页面切换 +3MB（无泄漏迹象） |
| 离线 | 缓存 44 个文件齐全；断网刷新可用；**断网仍能导出 Word** |
| 产物正确性 | 导出的 `.docx` 用 python-docx 打开、内嵌图用 Pillow 读像素；备份 zip 的 counts / 图片逐项核对 |

---


### 5. 交付过程中发现并修复的缺陷（9 个，全部有回归测试）

| # | 级别 | 问题 | 怎么发现的 | 修法与防线 |
| --- | --- | --- | --- | --- |
| 1 | P0 | **「导入备份」100% 失败**（`zip.files.filter is not a function`）—— 客户唯一的救命通道 | 桌面 E2E「备份 → 清除 → 导入」跑不通 | 改成 `Object.entries(zip.files)`；补 `import_export.test.mjs`（8 项）+ E2E + 安卓复核；阳性对照可复现原错 |
| 2 | P0 | 打开页面即崩（`Cannot read properties of undefined (reading 'read')`） | 真机（客户） | `boot()` 改"先开库再构造"，`ctx` 一律从 `app` 现取；新增 `boot.test.mjs`（含阳性对照） |
| 3 | P0 | 导出必崩（`nodebuffer is not supported by this platform`） | 真机（客户） | 改用 `Packer.toArrayBuffer`；新增 `platform.test.mjs`（无 Buffer 环境 + vendor 构建）；闸门 A 仍 0 差异 |
| 4 | P1 | 点检测记录「编辑」直接崩（`reading '0'`） | 真机（客户） | `getReadings()` 原始行要过 `faceView()`；新增 `record_edit.test.mjs` |
| 5 | P1 | 表单页底部 Tab 压住保存按钮（`[hidden]` 被作者样式压过） | 真机（客户） | 全局 `[hidden]{display:none!important}`；`mobile_render.test.mjs` 锁规则存在性 |
| 6 | P1 | 底部 Tab 图标空白（SVG 建在 HTML 命名空间） | 真机（客户） | `createElementNS`；测试断言 namespaceURI |
| 7 | P1 | 交付包会混进 `web/e2e/` 测试脚本（62 vs 53 个文件） | 打包自检 | 打包脚本排除 `e2e`，并加"测试资产进包即拒绝产出"的硬断言 |
| 8 | P2 | 操作条「取消」只有 28×22px，误触就丢整张表单 | 桌面 E2E（触控尺寸用例） | 44×44 触控区（`m5.css`） |
| 9 | P2 | **软键盘弹起时「保存」被键盘挡住**（真机实测：`innerHeight` 不变、只有 `visualViewport` 变矮） | 安卓模拟器 + 真实输入法 | `ui/viewport.js` 把键盘高度写进 `--keyboard-inset`，操作条 `bottom` 跟着抬高；`keyboard_inset.test.mjs`（5 项）+ 模拟器实测：键盘 296px → 操作条底部 478 = 键盘上沿 |

> **教训（可引用）**：前 3 个 P0 的共同点是"**测试环境比真实环境宽容**"——
> jsdom 没有 canvas / 没有 `<dialog>.showModal` / 没有真浏览器；
> 而"导出有覆盖、导入没覆盖"让人误以为备份整体可用。
> 现在的防线是：**把交付包本身当被测对象，在桌面浏览器和安卓浏览器各跑一遍完整链路。**

---

