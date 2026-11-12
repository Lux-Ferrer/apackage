# 建筑幕墙检测报告生成工具

Existing Curtain Wall Inspection Data Recording and Report Generation Tool —— NYU MS in Management and Systems 毕业项目（Capstone）。

面向幕墙检测工程师的本地 Web 工具：录入立柱 / 横梁截面尺寸检测数据与缺陷检测记录，一键导出与客户模板排版一致的 Word 检测报告。

> ### 一条贯穿本项目的结论
>
> **闸门绿了，先问"这个属性到底有没有被比"。相等有两种来源：两边真的对，或者这个属性根本没进比对。
> 后者更危险，因为它伪装成前者。**
>
> 出处是 M5-3 的实测：把缺陷附页接进 JS 引擎时发现，段落指纹里原本**完全没有图片** ——
> 一张图漏嵌、嵌错文件、显示尺寸算错、EXIF 方向没摆正，对拍闸门都会照样报"全部一致"。
> 补法与验证见 `docs/management/M5-设计.md` 4.6、`deliverables/m5-gate-a-diff.md`，
> 可执行的判据是 `python tools/verify_gate_sensitivity.py`（阴性对照 + 7 项下毒）。
>
> 还有下半句（M5 验收当天补的）：**也要先问"被测的环境和用户的环境是不是同一个"。**
> 出处是手机上一按导出就报 `nodebuffer is not supported by this platform` ——
> 205 个测试 + 16 条闸门全绿，因为它们全跑在 Node/jsdom 上，而 Node 有浏览器没有的 `Buffer`。
> 测试环境比真实环境宽容，就会把浏览器的缺失悄悄补上。见 `M5-设计.md` §9 第 8 条。
>
> 文档索引见 README 末尾。

---

## 交付版（`release/v1.0.0`）

`master` 是开发线（保留全部里程碑文档与测试）；**交给客户的是 `release/v1.0.0` 分支**：
去掉了开发/课程痕迹，报告人可在界面里配置，并产出一个可以直接内网部署的静态包。

```powershell
git checkout release/v1.0.0
python tools/make_release_zip.py         # → dist/mcc-inspection-tool-v1.0.0.zip（含 .sha256 与清单）
npm run test:e2e                         # 真实浏览器 E2E（21 条，测的就是上面那个 zip）
```

| 交付物 | 位置 |
| --- | --- |
| 部署包（52 个文件，462 KB） | `dist/mcc-inspection-tool-v1.0.0.zip` |
| 客户文档（随包发给客户） | `docs/release/客户部署与使用说明.md` |
| 部署样例（Nginx / IIS / 零依赖静态服务） | `docs/release/{nginx.conf.example,web.config.example,serve_static.py}` |
| 本次清理的完整说明 | `docs/management/v1.0.0-发布清理.md` |
| **真实浏览器验证报告** | `docs/management/v1.0.0-浏览器E2E验证报告.md` |

客户要改默认报告人时只碰两个地方：界面「我的 → 个人信息配置」，或 `app/product.js` 里的
`DEFAULT_PROFILE`（产品名 / 版本 / 出品方也在这个文件里，**版本号只有这一处真相源**）。

---

## 当前状态

**UI（移动端优先改造）已完成** —— 2026-09-25

| 里程碑 | 内容 | 状态 |
| --- | --- | --- |
| M0 | 拆包、数据库 schema、Word A4 报告底座 | ✅ 完成 |
| M1 | 项目管理 CRUD + 立柱/横梁检测记录录入 | ✅ 完成 |
| M2 | 项目级 Word 导出（与真实客户报告**逐属性对拍一致**） | ✅ 完成 |
| M3 | 缺陷填报完善（图片/规范/建议/绑定项目）+ 附页导出 | ✅ 完成 |
| M4 | 报告管理（列表/筛选/详情/删除） | ✅ 完成 |
| UI | 移动优先响应式改造（静态壳 + 客户端渲染，为 M5 铺路） | ✅ 完成 |
| M5 | 前端本地化改造（IndexedDB + docx JS + 纯静态 PWA） | ✅ 完成：数据层 / 导出引擎（含附页，0 差异）/ 图片管线与配额 / UI 接线 / **PWA 与离线**；**只剩真机验收**（见 checklist） |

**M5 已完成的部分**（新代码全在 `web/`，与 `webapp/` 并存）：

- **数据层**：`web/app/db.js`（IndexedDB 连接/建库/事务纪律）+ `web/app/repo/*`（含**手写级联**——
  IndexedDB 没有外键）+ `web/tests/`（fake-indexeddb，断言逐条对应 Python 数据层测试）；
- **导出引擎**：`web/app/report/{spec,engine,postprocess}.js` —— 数据 → docx，再由 11 个补丁
  补齐到与对拍基线**逐属性一致**。**闸门 A（复刻冻结基线，含附页）与闸门 B（对齐真实报告）都是 0 差异**；
- **图片管线**：`web/app/image-pipeline.js`（EXIF 摆正 → 等比缩放 → JPEG 现压 → 缩略图，
  编解码可注入因而在 Node 里可测）+ `web/app/storage.js`（配额/持久化，含 iOS 闲置清理的显式提示）；
  原图字节原样入库、**只有缩略图落库**（设计文档 3.4 的那一次有意偏离），全尺寸导出副本**导出时现压**；
- **附页**：`web/app/report/attachments.js` + `engine.js` 的附页部分（两列 9 行信息表、每份独立成页、
  图片嵌入、缺失降级），并**纳入闸门 A**；
- **UI 接线**：`web/index.html` + `web/app/{main,router}.js` + `web/app/views/*`（项目 / 检测记录 /
  报告 / 我的 / 数据管理 / 关于）+ `web/app/ui/*`（DOM 原语、确认弹窗、提示、检测面交互）。
  壳与 `webapp/templates/` + `webapp/static/css/app.css` 一一对应，**CSS 是生成物**（同一份真相源）；
- **数据管理页**（`#/me/data`）：已用空间、持久化授权、**导出/导入备份 zip**、重建缩略图、清除全部报告；
- **PWA（离线可用）**：`web/sw.js` + `web/manifest.webmanifest` + 生成的 `web/assets/shell.js`
  （离线清单 + 内容指纹版本号）。清单是**算出来的**不是手写的 —— SW 最常见的失败是"漏一个文件"，
  在线全绿、断网白屏；测试会反查"源码 import 到的每个模块在不在清单里"。新版本**不自动 skipWaiting**，
  以免正在填表的页面被换掉；
- **闸门 C（不借助 Python 的自检）**：`web/app/report/fingerprint.js` 用 JS 重写了指纹与差异逻辑，
  与 Python 冻结的 `generated_baseline.fingerprint.json` **逐属性一致**（0 差异），
  于是"没有 Python 的环境也能自检"这条链闭合了；
- **备份**：`web/app/import-export.js` —— `backup.json` + 原图打进一个 zip；导入先 `inspectBackup()`
  把"会覆盖什么"讲清楚再确认（备份是完整快照，不做合并）；缩略图不进备份，导入时现重建；
- **闸门自身的可信度**：`tools/verify_gate_sensitivity.py` 往产物里逐个下毒（图片尺寸/换成别的图/
  漏嵌/文本/合并/行高/加粗），验证闸门**确实抓得住**，而不是"这个属性根本没被比"；
- **生成物同步**：`tools/export_web_assets.py`（config.js / spec.js / **styles/app.css** / vendor 库 /
  底座 docx ← Python 侧）、`tools/export_fixture_data.py`（基准数据 → 语言中立 JSON）；
- **Flask 版本未受影响**：`webapp/` / `app.py` / `tests/` / `requirements*.txt` 一行未改，
  348 项 Python 测试与四条基线闸门保持全绿（它是中期展示的演示素材）。

UI 交付：底部 3 Tab（项目 / 报告 / 我的）+ 桌面顶栏导航（同一个 partial 两处渲染）、检测面「摘要行 + 下级编辑」（原生 `<details>`，**无 JS 也能录入并提交**）、三态着色与警告灯双通道、构件信息横向表格布局、表单页固定底部操作条、`/` 落地到项目 Tab、模块进度搬到 `/about`、「我的」页（报告人卡 / 数据概览 / 清除全部报告 / 应用信息）。三档断点，**只有 ≥960px 一处做结构性变化**。

M4 交付：报告管理列表（倒序 + 隐患等级徽标 + 缩略图 + 绑定项目）、顶部统计（总数 / 高 / 中 / 低，同时就是筛选控件）、详情页（全字段 + 大图）、删除（应用内确认弹窗 + 图片一并删除 + 自动解除项目关联）。**不改数据库结构**（未新增表/列，`SCHEMA_VERSION` 仍为 1）。

M3 交付：隐患图片（必填、拍照/相册、≤20MB、原图落盘且保留原文件名）、相关规范/补充建议、绑定项目；项目详情显示真实关联报告与「附加 N 份并导出 / 仅导出检测报告」二选一；导出附页（每份独立成页、9 行两列信息表、导出时现压的图片副本、图片缺失时降级）。

> **架构说明（M5 已完成）**：数据层与导出引擎都已经迁到前端（IndexedDB + docx JS），
> **对外交付入口是纯静态的 `web/`（可离线安装的 PWA）**。
>
> `webapp/` + `app.py`（Flask 版）**保留但降级为 legacy**：
> 它是对外交付入口的**参考实现与规格来源** —— 客户换模板时的流程是
> "先改 Python → 重新 `--bless` 基线 → JS 引擎跟上"，闸门 A/B 的基准也由它产出。
> 它仍然能跑（`python app.py`），但**不再是要交给现场用的那一版**。
> 两边的数据是**各自独立的**（SQLite 文件 vs 浏览器 IndexedDB），不会互相同步；
> 要搬数据请用「我的 → 数据管理」的备份 zip。

## 范围

**包含**：立柱 / 横梁截面尺寸检测（每检测面 5 个厚度值，自动计算最小值）· 缺陷检测填报 · 报告管理 · 项目管理 · 项目级 Word 报告导出 · **本地存储（浏览器 IndexedDB；legacy 版为 SQLite）** 与本地/局域网 Web 部署 · 离线可用。

**不包含**（已确认范围外）：膜厚检测 · 玻璃面板尺寸及厚度检测 · 速记 · 统计 · 登录 · 结构安全评定 · 原生手机 App。

> 依据 `docs/management/03 ProjectCharter 3.0.docx`。

## 运行

**M5 纯前端版**（推荐；数据存在浏览器里，需要支持 import maps 的浏览器 = Chrome 89+ / Safari 16.4+ / Firefox 108+）：

```powershell
python tools/serve_web.py                 # 起静态服务器，并打印手机能打开的局域网地址
# 或者用任意静态服务器：
python -m http.server 8080 --directory web
```

然后浏览器打开 <http://127.0.0.1:8080>。**不要双击 `index.html` 用 `file://` 打开** ——
IndexedDB 与 ES modules 都会受限（真这样打开时页面会给出这句提示）。

**离线使用**：打开一次之后浏览器会缓存应用壳（Service Worker），之后断网也能打开、能录入、能导出 Word。
手机上建议「添加到主屏幕」（iOS 只有这样才能拿到较持久的存储）；离线缓存的版本号在「我的 → 关于」里，
改过任何一个被缓存的文件它就会变（查"怎么还是旧页面"时先看它）。

**Flask 参考实现**（服务端渲染、无 JS 也能录入；中期展示用）：

```powershell
python -m pip install -r requirements.txt
python app.py
```

浏览器打开 <http://127.0.0.1:5000>。首次启动会自动按 `webapp/schema.sql` 建库（`defects.db`）。

使用顺序：新建项目 → 进入项目详情 → 添加检测记录（选立柱或横梁模板）→ 填写构件信息与检测面读数 → 保存。

### 手机真机验证（局域网访问）

两份清单，风险点不同：

| 验什么 | 清单 | 起服务 |
| --- | --- | --- |
| Flask 版 UI 改造（按钮点得动吗） | `docs/management/真机验证checklist.md` | `python app.py --lan` |
| **M5 纯前端版**（照片方向 / 会不会丢数据 / 离线） | `docs/management/M5-真机验证checklist.md` | `python tools/serve_web.py` |

（下面这一段是 **Flask 版**的局域网说明；M5 版由 `tools/serve_web.py` 代劳，
它同样会打印手机地址，前置条件与排错完全一致。）

用手机打开 Flask 版，需要绑定 `0.0.0.0` 并把地址告诉手机：

```powershell
python app.py --lan
```

终端会打印出该在手机里输入的地址，例如：

```
  建筑幕墙检测报告工具
  ----------------------------------------------
  本机访问：http://127.0.0.1:5000
  手机访问：http://192.168.1.9:5000
```

**前置条件（缺一不可）**

| # | 条件 | 怎么确认 / 怎么办 |
| --- | --- | --- |
| 1 | 手机与电脑连**同一个 Wi-Fi / 局域网** | 电脑上 `ipconfig` 看 IPv4 是不是 `192.168.x.x` / `10.x.x.x`（`127.` 或 `169.254.` 开头说明没连上网络） |
| 2 | 手机**关掉 VPN / 代理** | VPN 会把局域网流量也劫走，表现是"网址打不开但电脑自己打得开" |
| 3 | **Windows 防火墙放行 TCP 5000** | 首次 `--lan` 启动时系统会弹「是否允许访问网络」→ 勾选**专用网络**。若当时点了取消，用管理员 PowerShell 补一条：<br>`New-NetFirewallRule -DisplayName "幕墙检测工具 5000" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow -Profile Private` |
| 4 | 路由器没开**客户端隔离**（AP Isolation） | 常见于公司网 / 访客网：同一 Wi-Fi 下设备互相不通。换手机热点或家用网络即可 |

**排查顺序**（能快速区分是防火墙问题还是手机问题）：

1. 电脑自己打开 `http://192.168.1.9:5000`（用局域网 IP，不用 127.0.0.1）→ 打不开说明服务没绑对；
2. 电脑能开、手机打不开 → 按上表 2/3/4 逐条查；
3. 都不行 → `python app.py --lan --port 8080` 换端口再试（有些网络屏蔽 5000）。

> ⚠️ **安全边界**：本应用没有登录（已确认范围外），`--lan` 之后**同一网段内任何设备**打开网址都能增删数据、清除全部报告。只在自己的热点 / 家 / 办公室内网下使用，别在公司大内网或公共 Wi-Fi 上开。
>
> 调试器已与 `--lan` 强制互斥：`python app.py --debug --lan` 会直接拒绝启动（Werkzeug 调试器能在浏览器里执行任意代码，绑到局域网等于把它开放出去）。

真机验证的逐项清单见 [`docs/management/真机验证checklist.md`](docs/management/真机验证checklist.md)。

## 依赖

| 文件 | 内容 | 用途 |
| --- | --- | --- |
| `requirements.txt` | `flask`、`python-docx`、`pillow` | 运行应用所需（Pillow 用于隐患图片的压缩与 EXIF 摆正） |
| `requirements-dev.txt` | 追加 `pytest`、`openpyxl` | 跑测试与 `tools/verify_case_data.py` |

## 测试

**全部闸门一条命令**（推荐；共 14 条，约 17 秒）：

```powershell
python tools/verify_all.py          # 汇总表 + 任一失败则退出码 1
python tools/verify_all.py --list   # 只列出会跑什么
```

它按顺序跑：生成 JS 产物 → 生成物同步（2 条）→ Python 测试 → 前端 JS 测试 →
4 条 Flask 基线 → 补丁验证 → 附页基线 → 闸门 A（两半）→ 闸门 B → **闸门 C（纯 JS）** →
闸门敏感性 → 展示素材版式。**任何代码改动之后都应该跑它**。

逐条手跑（需要看细节时）：

```powershell
python -m pip install -r requirements-dev.txt     # pytest + openpyxl
python -m pytest -q                               # Python 测试套件（348 项）
python -m pytest tests/test_word_report.py -v     # 只跑 Word 版式相关
```

```powershell
npm install                                       # 按 package.json 装开发期 JS 依赖
node tests/js/record_form.test.js                 # 前端功能测试（58 项）
```

验证与交付工具：

```powershell
# 主闸门：从样例回灌其自身数据后重新生成，与样例逐属性对拍
python tools/compare_report_with_sample.py --report deliverables/fidelity-report.md
python tools/compare_report_with_sample.py --bless      # 验收后重新冻结回归基线

# O2：用真实案例数据走完整录入 + 导出，并与案例逐格比对内容
python tools/verify_case_data.py

# 生成 5 份样例报告（章程 Objective 3 的证据）到 deliverables/samples/
python tools/generate_sample_reports.py

# 从样例重生报告底座（webapp/resources/report_base.docx）
python tools/make_report_template.py
```

前端 JS 功能测试（可选，需要 Node.js；命令见上面的「测试」一节）。

> ⚠️ 装 JS 依赖用 `npm install`（清单在 `package.json`），**不要**用 `npm install --no-save <包>`：
> npm 会按 `package.json` 修剪 `node_modules`，装 B 会把先前装的 A 删掉（这个坑踩过两次）。

M5 移植验收（可选，需要 Node.js。设计见 `docs/management/M5-设计.md`）：

```powershell
npm test                      # 数据层 + 引擎 + 附页 + 图片管线 + 指纹 + 端到端 UI + 离线清单 + 平台假设 + 备份导入导出（234 项）
                              # 外加既有的 Flask UI 测试（58 项），共 292 项

npm run test:e2e              # 真实浏览器 E2E（21 项：主流程 / 布局 / 负载 / 离线 / 图片 / 数据安全）
                              # 被测对象是 dist/ 里的交付包本身，需要先在装了 Edge/Chrome 的机器上 npm install
npm run test:android          # 安卓模拟器回归（12 项，需 MuMu + adb 端口转发，见脚本文件头）

# 生成两份被测产物：无附页 / 含附页
node tools/js/generate_from_fixture.mjs

# 闸门 A：JS 引擎产物 vs Python 引擎冻结的基线（两半都要求 0 差异）
python tools/compare_report_with_sample.py --expected tests/fixtures/generated_baseline.docx --actual _work/js_generated.docx
python tools/compare_report_with_sample.py --expected tests/fixtures/attachment_baseline.docx --actual _work/js_generated_attachments.docx

# 闸门 B：JS 引擎产物 vs 真实客户报告裁剪版（要求 0 差异）
python tools/compare_report_with_sample.py --expected tests/fixtures/检测表_真实裁剪.docx --actual _work/js_generated.docx

# 闸门 C：**不借助 Python** 的自检（纯 JS 指纹实现 vs 语言中立的指纹 JSON，要求 0 差异）
node tools/js/check_gate_c.mjs

# 闸门自身可信吗？阴性对照（原样必须 0 差异）+ 7 项下毒必须全部被抓到
python tools/verify_gate_sensitivity.py

# M5-0 侦察的补丁验证（升 docx 库后要重跑）
node tools/js/prototype_postprocess.mjs
python tools/verify_docx_patches.py

# 附页基线与附页夹具（改了附页版式或夹具数据后重跑；--check 只比对）
python tools/build_attachment_baseline.py

# 生成物与真相源同步（改了 webapp/config.py 或 report_layout.json 之后）
python tools/export_web_assets.py --check
python tools/export_fixture_data.py --check
```

> ⚠️ **Node 里没有 canvas**，所以闸门 A 的附页部分用了一个**替身编解码器**
> （`tools/js/fixture-codec.mjs`）：尺寸/方向的计算走**产品代码**，只有"重采样像素"是替身
> （用夹具的 `_摆正` 副本）。替身**在需要缩放时会直接报错**，因此它不可能祝福一个
> "我们不会真的交付"的产物。理由与自锁见 `docs/management/M5-设计.md` 4.7。

## 交付物

| 路径 | 说明 |
| --- | --- |
| `deliverables/samples/` | 5 份样例报告 + 清单（章程 Objective 3 的度量证据） |
| `deliverables/fidelity-report.md` | 与客户样例的逐属性对拍报告 |
| `deliverables/m5-gate-a-diff.md` | 闸门 A 的归档报告（两半 0 差异 + 闸门可信度证据） |
| `deliverables/prp/` | PRP 展示素材：4 张证明类图（收敛曲线 / 敏感性表 / 测试总览 / 架构对比），由 `tools/make_prp_figures.py` 生成，图上的数字取自真实运行输出 |
| `tests/fixtures/generated_baseline.docx` | 回归基线：生成物偏离即测试失败，直到显式重新冻结 |
| `tests/fixtures/generated_baseline.fingerprint.json` | **闸门 C** 的期望值（语言中立），纯 JS 自检用它 |

## 目录结构

```text
Capstone/
├── app.py                     入口：create_app() + app.run()
├── requirements.txt
├── webapp/                    应用包
│   ├── __init__.py            应用工厂：注册蓝图、启动建库
│   ├── config.py              路径、预置缺陷类型、截面要求条文、检测面建议值
│   ├── db.py                  SQLite 连接 / 建库 / 查询助手 / transaction()
│   ├── schema.sql             4 张表：projects / measurement_records /
│   │                          thickness_readings / defects
│   ├── resources/
│   │   ├── report_base.docx   Word 报告底座（由样例派生，见下）
│   │   └── report_layout.json 版式规格（语言中立，供 M5 的前端移植复用）
│   ├── routes/                pages.py / projects.py / records.py / defects.py / reports.py / me.py
│   │                          （defects = 需求 3.3 填报写入；reports = 需求 3.4 报告管理；
│   │                            me = 需求 3.7 我的；pages = 落地重定向 + 关于页）
│   ├── services/
│   │   ├── thickness.py       5 个厚度读数 -> 最小值、格式化
│   │   ├── projects.py        项目读写、列表统计、删除影响面
│   │   ├── measurements.py    记录表单解析、事务化增删改、分组读取
│   │   ├── defects.py         缺陷表单解析、读写、附页渲染数据、报告管理查询/删除
│   │   ├── images.py          隐患图片：上传校验、落盘命名、导出压缩副本、列表缩略图
│   │   └── word_report.py     A4 底座 + 表格原语 + 检测表/附页构建
│   ├── templates/             base / _nav / about / index 占位
│   │                          projects / records / defects / reports / me
│   └── static/                css/app.css · js/{app,record_form,defects_form}.js
├── web/                       M5：纯前端版（浏览器里跑，数据存 IndexedDB）
│   ├── index.html             应用壳（含 import map：裸模块名 → vendor/；挂 manifest 与图标）
│   ├── sw.js                  Service Worker：预缓存应用壳、版本化、不自动 skipWaiting
│   ├── manifest.webmanifest   PWA 清单（standalone / 主题色 / 三个图标）
│   ├── icons/                 icon-192 · icon-512 · icon-512-maskable（tools/make_web_icons.py 生成）
│   ├── styles/
│   │   ├── app.css            **生成物** ← webapp/static/css/app.css（同一份壳，勿手改）
│   │   └── m5.css             M5 自己新增的样式（手写）
│   ├── app/
│   │   ├── main.js            引导 + hash 路由分发 + 渲染互斥量
│   │   ├── router.js          路由表 / 匹配 / 链接生成（纯函数）
│   │   ├── db.js              IndexedDB 连接 / 建库 / 事务纪律 / 错误翻译
│   │   ├── repo/              数据层：projects · measurements · defects · images
│   │   ├── thickness.js       5 个厚度读数 -> 最小值（对齐 Python 版）
│   │   ├── clauses.js         截面尺寸归一化与条文解析
│   │   ├── image-pipeline.js  EXIF 摆正 / 等比缩放 / JPEG 现压 / 缩略图（编解码可注入）
│   │   ├── storage.js         配额与持久化：警告线 / 拦截线 / iOS 闲置清理提示
│   │   ├── export.js          项目 → docx → 下载（含附页、文件名规则）
│   │   ├── import-export.js   备份 zip：导出 / 预检 / 导入（覆盖式）
│   │   ├── config.js          生成物（源自 webapp/config.py，勿手改）
│   │   ├── views/             页面：projects · records · reports · me · layout
│   │   ├── ui/                dom · dialog（确认弹窗+提示队列）· objecturl · record-form
│   │   └── report/
│   │       ├── engine.js      数据 -> docx（docx JS 库，含附页）
│   │       ├── attachments.js 附页：版式换算 / 现压图片 / 缺失降级
│   │       ├── fingerprint.js 指纹 + 差异（纯 JS，供闸门 C）
│   │       ├── image-size.js  JPEG/PNG 文件头读尺寸（不依赖 canvas）
│   │       ├── postprocess.js 11 个补丁：把库的输出补齐到与基线逐属性一致
│   │       └── spec.js        生成物（源自 report_layout.json，勿手改）
│   ├── assets/                report_layout.json · report_base.docx · fixture_data.json · shell.js（生成物）
│   ├── vendor/                docx.mjs · jszip.min.js（vendored）· jszip.js（ESM 包装）
│   ├── tests/                 234 项：数据层 / 引擎 / 附页 / 图片管线 / 配额 / 路由 / 指纹（闸门 C）/ 备份导入导出 /
│   │                          端到端（jsdom + fake-indexeddb）/ 模块图自检 / PWA 离线清单 /
│   │                          平台假设（浏览器没有 Buffer，真机导出的那个 bug）
│   ├── e2e/                   21 项**真实浏览器**用例（Playwright，测的是 dist/ 里的交付包）：
│   │                          主流程 / 移动端布局 / 边界负载 / 离线 / 图片管线 / 鲁棒性 / 数据安全
│   │                          android-remote.mjs = 安卓模拟器回归（CDP over adb，12 项）
│   └── package.json           仅声明本目录为 ESM 作用域
├── reports/                   导出的 .docx（gitignore）
├── uploads/defects/           隐患图片（gitignore）
├── tests/
│   ├── fixtures/              检测表_真实裁剪.docx（对拍基准，勿改）
│   │                          金骐智谷_金骐_检测报告.docx（字体/主题来源）
│   │                          generated_baseline.docx（回归基线）
│   │                          generated_baseline.fingerprint.json（基线指纹）
│   │                          attachment_baseline.docx（附页基线，Python 引擎冻结）
│   │                          attachment/（附页夹具图片：横拍 / 竖拍 EXIF=6 / 摆正副本）
│   ├── js/record_form.test.js 前端功能测试（jsdom）
│   ├── test_db.py             表结构、约束、级联语义
│   ├── test_thickness.py      最小值计算
│   ├── test_word_report.py    A4 页面、字体、表格原语、版式常量上锁
│   ├── test_measurements.py   表单解析、事务回滚、编辑锁定、条文与需求报告一致
│   ├── test_projects.py       项目 CRUD 与校验
│   ├── test_records.py        记录 CRUD、模板锁定、最小值链路
│   ├── test_report_export.py  导出路由、文件名、空项目、无玻璃
│   ├── test_report_fidelity.py 与样例逐属性对拍 + 回归基线
│   ├── test_images.py         图片校验、命名、EXIF 摆正、压缩、降级
│   ├── test_defects.py        缺陷表单、绑定项目、落盘原子性、附页数据
│   ├── test_attachment_export.py 附页结构、分页、图片、无附页路径不变
│   ├── test_reports.py        报告管理：列表/排序/统计/筛选/详情/缩略图/删除
│   ├── test_ui.py             UI 契约：底部 Tab、操作条、横向表格布局、卡片列表、我的页
│   ├── test_text_fit.py       列宽适配度量工具
│   ├── test_extract_layout_spec.py 版式提取器与规格一致性
│   ├── test_case_data.py      案例期望行构造（条文列的合并语义）
│   └── test_web.py            路由与完整链路冒烟
├── deliverables/              5 份样例报告 + 对拍报告（章程 Objective 3 的证据）
├── tools/                     compare_report_with_sample.py · verify_case_data.py
│                              generate_sample_reports.py · make_report_template.py
│                              case_data.py（案例解析，多工具共用）
│                              verify_all.py（一条命令跑完全部闸门）
│                              verify_gate_sensitivity.py（闸门可信度：阴性 + 下毒）
│                              serve_web.py（起 M5 静态服务 + 打印手机地址）
│                              make_prp_figures.py（PRP 展示素材 + 版式自检）
│                              export_web_assets.py · export_fixture_data.py（M5 生成物）
│                              attachment_fixture.py · build_attachment_baseline.py（附页夹具）
│                              js/generate_from_fixture.mjs · js/fixture-codec.mjs
│                              js/image-headers.mjs · js/prototype_postprocess.mjs
└── docs/                      需求、计划、章程、案例资料、设计文档
```

## Word 报告底座说明（重要）

**版式**对齐真实客户报告第 12-13 页（表2-4 立柱 / 表2-5 横梁）。对拍基准是它的裁剪版
`tests/fixtures/检测表_真实裁剪.docx`（由 `python tools/build_fixture.py` 生成），
所有数值集中在 `webapp/resources/report_layout.json`，由 `tests/test_word_report.py` 上锁：

| 项目 | 值 |
| --- | --- |
| 页面 | A4 `11907 × 16839` twips；上边距 `1440`、下 `1843`、左右 `907`；页眉距离 `850`、页脚 `964`（取自真实报告里含立柱/横梁表的那一节） |
| 字体 | 西文 Times New Roman；中文走主题字体（`eastAsiaTheme="minorEastAsia"`，等线）。**字体不在本次对齐范围**，真实报告的 SimSun/10.5pt 不采纳 |
| 立柱/横梁表 | 表宽 `10833` twips，固定布局，居中（比正文区 10093 宽 → 两侧对称溢出），11 列 `1077/850/1416/789/790×3/789/790×2/1962` |
| 表头 | 2 行，「不加粗」；「厚度检测结果（mm）」横跨 7 列；「检测构件\n位置」「尺寸检测结果m×n\n（mm×mm）」是多段落 |
| 行高 | 表头 567；数据行立柱 522 / 横梁 567（均为"至少"语义） |
| 单元格边距 | 单元格上不写 `tcMar`，只由表级 `tblCellMar`（左右 57）与默认值决定 |
| 边框 | 外框 single / sz=12 / 000000，内部横竖线 sz=6 |

换基准的取证工具：`python tools/extract_layout_spec.py <报告.docx>` —— 一条命令列出"新报告与当前规格的每一处不同"，并可 `--json` 输出候选规格（**不会自动覆盖**）。

**为什么底座要从旧样例派生**：python-docx 自带模板的主题把中文字体映射成**宋体**，`金骐智谷_金骐_检测报告.docx` 是**等线**。若新建文档后再"设置字体"，中文就会落到宋体上。`webapp/resources/report_base.docx` 保留了该样例的 `theme1.xml` / `styles.xml` 并清空正文（`python tools/make_report_template.py` 从 `config.FONT_SAMPLE` 重生），因此生成的新文档天然沿用其字体，代码里不硬编码任何中文字体名。

## 关键业务规则

- 每个检测面的最小值为该面 5 个读数的派生值，**不落库**，导出保留两位小数（`webapp/services/thickness.py`）
- **前端实时最小值只是预览**：保存与导出时由服务端重算，前端结果不被信任
- 厚度读数**允许留空**（现场可能只测几个点），但"非空却不是数字"会被拦下：输入框标红 + 就地提示「请填数字」+ **禁用保存按钮**，并拦截回车触发的隐式提交；此时最小值仍按有效值计算
- 检测面标签为短文本（真实数据：立柱 `B` / `H`，横梁 `t`），允许自由输入，不做枚举约束
- 同一构件有多个检测面时，Word 导出需把「楼层 / 构件位置 / 尺寸检测结果 / 截面尺寸要求」四列纵向合并
- 尺寸结果自动把 `x` / `X` / `*` 规范化为 `×`（如 `63x164` → `63×164`）
- 截面尺寸要求存**文案快照**；为空时显示「无」
- **编辑检测记录时模板类型不可切换**，三道防线：界面无控件、路由不接收该字段、`UPDATE` 语句不含该列
- 检测记录与其厚度读数在**同一事务**内提交，任一步失败整体回滚
- 删除项目 → 级联删除其检测记录；关联缺陷报告 `project_id` **置空保留**
- 隐患图片存文件路径（`uploads/defects/`），不入库为 base64/BLOB

### Word 导出（M2）

- 文件名 `项目编号_房屋名称_检测报告.docx`，非法字符替换为 `_` 并限长
- **只有存在记录的章节才输出**（立柱 / 横梁各自判断）；两者都无则只出信息段 + 备注
- **不输出玻璃模块**（范围外，测试里反向断言）
- 表头「厚度检测结果 (mm)」横向跨 7 列；**多面构件**的「楼层 / 构件位置 / 尺寸结果 / 截面尺寸要求」四列纵向合并；**单面构件不写 `vMerge`**（与样例一致）
- 「截面尺寸要求」数据格 8pt + 左右 60 边距（复刻样例，为长条文挤空间）；其余单元格不写字号（继承，Word 下 10pt）
- 版式数值全部存放于 `webapp/resources/report_layout.json`，由测试与样例实测值上锁
- 条文文案**以需求报告为准**（全角标点）；预置项只允许追加，不得改动或重排已有项（历史快照靠索引回填）

### 缺陷报告与附页（M3）

- 隐患图片**必填**：拍照/相册、≤20MB、扩展名与真实格式双校验（防改扩展名的假图片）
- **原图落盘、压缩副本不落库**：落盘名为 `<uuid>_<清洗后的原名>.<ext>`，从路径即可反推原文件名（无需额外字段、无需迁移）；压缩在**导出时现压**（长边 ≤1600px、JPEG q=80），与「最小值不落库」同一原则
- 图片按 **EXIF 方向摆正**（手机竖拍必须），透明区域合成为白底
- 图片缺失/损坏 → 附页仍能导出，就地显示「（图片缺失：原名）」，**绝不因一张图让整份报告失败**
- 附页结构（需求 4.4）：标题 `检测报告附页（N/总数）`（带 `pageBreakBefore`，不产生游离空段）+ 9 行两列信息表（末行「图片文件」用于追溯原文件名）+ 「隐患图片」标签与图片
- 项目详情在有关联报告时提供二选一：「附加 N 份并导出」/「仅导出检测报告」
- **无附页路径与 M2 完全一致**：`add_trailing_empty` 已移到文档末尾，对无附页输出是恒等变换（对拍主闸门与回归基线继续生效）

### 报告管理与缩略图（M4）

- 模块边界严格对齐需求：**3.3 填报**留在 `/defects/*`（写入），**3.4 报告管理**在 `/reports/*`（查看 + 管理）；旧的 `/defects/<id>` 用 **308** 永久重定向兜住
- 顶部统计与筛选是**两件事**：统计恒为全量（`COUNT(*)` + `COALESCE(SUM(CASE WHEN ...))`，空表时 `SUM` 会返回 NULL，不写 `COALESCE` 就会显示「高 None」），筛选只影响列表
- 列表排序 `created_at DESC, id DESC`：`created_at` 只到秒，同秒内必须靠 `id` 兜底，否则顺序会抖动
- 缩略图**不复用**导出的 1600px 压缩副本：`images.thumbnail_bytes()` 内存现压 240px JPEG，配合 `Cache-Control: immutable`（落盘名含 uuid、系统无"改图"路径 → 同一 URL 字节永不变化）。**不落盘、不落库**，与「最小值不落库」同一原则；两个尺寸共用 `_oriented_rgb()`，EXIF 摆正行为不会两处分叉
- 删除顺序**先删库、后删文件**：反过来的话一旦 DELETE 失败就会留下指向不存在图片的记录（用户可见的数据损坏），按此顺序最坏只是一个不可见的孤儿文件
- 需求 3.4e 的「删除后自动解除项目关联」不需要 `UPDATE ... SET project_id = NULL` —— 关联就在这一行上，删除即解绑
- 列表页所有派生字段（徽标类名、时间文案、缩略图 URL、项目标签、图片是否存在）由 `routes/reports.py::_card()` 统一装配，模板只做 `{{ }}` 输出 —— 这是给 UI 阶段/ M5 前端渲染留的交接面（同一份 dict 可直接 `jsonify`）

### 移动端界面（UI）

- **导航**：一个 partial（`templates/_nav.html`）渲染两处 —— 移动端底部 3 Tab（项目 / 报告 / 我的）、桌面顶栏导航。高亮由 app 级 `context_processor` 按**端点前缀**推导（`records.*` 归「项目」、`defects.*` 归「报告」），不靠路由传参，漏传不会丢高亮
- **Tab 的显示/隐藏**：浏览类页面（列表 / 详情）显示 Tab；表单类页面用 `{% block tabbar %}` 覆盖成空，改用**固定底部操作条**（保存必须落在拇指可达处，校验提示也移进操作条，否则长表单里提示会在屏幕外）
- **检测面录入**：`<table>` 8 列在 375px 下每列不足 24px，无法使用 → 改成 `<ol>` + 原生 `<details>/<summary>` 的**摘要行 + 下级编辑**
  - 摘要行显示：三态圆点 + 检测面名称 + 进度 `N/5` + 最小值 + 警告灯
  - **自动展开不需要 JS**：新增模式首行、校验失败的行由服务端写 `open`；编辑模式全折叠（摘要行即记录概览）
  - 折叠状态下浏览器仍提交 `<details>` 内的控件 → **禁用 JS 也能把预渲染的那一行填完并保存**（多面构件的"添加检测面"需要 JS —— 改造前的表格布局同样如此，不是退化）
- **三态着色与警告灯是两个独立通道**：着色（灰 / 黄 / 绿）表示"还剩多少活"，警告灯（只在有非法读数时亮）表示"能不能保存"。合并成一个信号会让"5 格全填 `abc`"看起来像填完了
- **输入时不打扰**：出现非法值只在摘要行亮警告灯，不自动展开；点保存被拦截时才展开非法行并聚焦第一个
- **构件信息**：label 左 / 控件右的两列网格（横向表格布局）。用 `minmax(0, 1fr)` 而不是 `1fr`（后者最小值是 `auto`，长内容会撑破网格）；桌面**复用同一 DOM**，只调整宽度
- **断点**：base（手机）/ 640px / 960px / max-359px（读数网格 5 列 → 3 列）。**只有 960px 一处做结构性变化**（底部 Tab → 顶栏导航），其余只调宽度、字号、间距
- **触控与字号硬约束**：输入框移动端 `font-size: 16px`（iOS 聚焦缩放的红线）、命中区 ≥44px、`viewport-fit=cover` + `env(safe-area-inset-bottom)` 处理 iPhone 底部横条 —— 桌面在 960px 档把这些收回改造前的观感

## 文档索引

- `docs/requirements/` 需求报告（原始需求全文）
- `docs/management/` 项目章程、开发计划、M1/M2/M4/UI/M5 设计、阶段交接记录
- `docs/management/M5-设计.md` M5 的设计与实测结论（含"闸门盲区"的发现与补法、M5-4 实施中的 4 个时序问题）
- `docs/management/真机验证checklist.md` Flask 版 UI 的真机清单
- `docs/management/M5-真机验证checklist.md` M5 纯前端版的真机清单（照片方向 / 配额 / 离线）
- `docs/management/signed/` 签署类文档（含签名与联系方式，不入仓库）
- `docs/samples/` 检测结果案例（Excel + 截图）
