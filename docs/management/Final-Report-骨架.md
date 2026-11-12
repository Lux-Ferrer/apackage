# Final Report 骨架（结题论文）

> 截止：**2026-12-05**（今天 2026-11-12，剩余 **23 天**）
> 受众：NYU MS in Management and Systems 评审委员会 + 客户方（中冶建筑研究总院（深圳）有限公司）
> 语言：**英文正文**（课程要求；若确认可用中文，同一骨架逐节替换即可）
> 体量建议：**9,000–12,000 词**正文 + 图表 + 附录（评审通常按 25–35 页估算）

---

## 0. 一句话定位（写进 Abstract 的最后一句）

> An offline-first, pure-static web application that reproduces an existing corporate Word report
> **attribute-for-attribute**, and the verification method that proves it — three independent
> fidelity gates plus real-browser E2E on both desktop and Android.

三个可辩护的贡献（评审最看重的"你到底贡献了什么"）：
1. **可复现的"版式保真"验证方法**：三道互相不替代的对拍闸门 + 7 项下毒敏感性验证（§7.2）。
2. **把"客户既有 Word 报告"当作规格说明书**：11 个后处理补丁，逐属性 0 差异（§6.3）。
3. **测试环境的诚实性**：从 jsdom → 真桌面浏览器 → 真安卓浏览器，每层都抓到上一层的盲区（§7.4，9 个缺陷的实证）。

---

## 1. 章节骨架（按写作顺序编号，非最终章节顺序）

### 1.1 Title Page
- Title（候选）：**"Faithful by Construction: An Offline-First Field Tool that Reproduces Corporate Inspection Reports Attribute-by-Attribute"**
- Subtitle：A capstone project for 中冶建筑研究总院（深圳）有限公司
- Author / Program / Date / Client / Advisor

### 1.2 Abstract（英文，250–300 词，最后写）
四句结构：问题 → 方法（设计 + 验证）→ 结果（数字）→ 意义（可迁移的经验）。

### 1.3 Keywords
curtain-wall inspection; offline-first PWA; document fidelity testing; differential testing; field data collection; mobile web

### 2. Introduction（~1,000 词）
- 2.1 Context：幕墙检测的现场作业与报告交付（客户是谁、现有流程怎么走）
- 2.2 Problem：现场录入靠纸/表格 → 手工排版 Word → 错漏与重复劳动；客户对"报告版式一字不差"有硬要求
- 2.3 Objectives（3 条，与 §4 需求表对齐）
- 2.4 Contributions（上面那三条）
- 2.5 Structure of the paper

> 素材：`docs/requirements/需求报告.txt`、`docs/management/2026-09-09_阶段1-PoC与开发计划.md`
> 待补：客户访谈的定性材料（谁在用、一天几张表、错一次的成本）

### 3. Related Work（~1,200 词）
- 3.1 Inspection data capture on mobile（离线优先、表单化录入）
- 3.2 Document generation & template fidelity（为什么"看起来一样"不等于"属性一样"）
- 3.3 Testing for fidelity: golden-file / differential testing / metamorphic testing
- 3.4 PWA & offline capabilities（Service Worker、缓存版本化、安全上下文约束）
- 3.5 Gap：既有实践很少把"版式保真"当作**可执行判据**，也少有人报告"测试环境比生产环境宽容"造成的漏检

> 待补：8–12 篇文献（PWA/offline、golden master testing、mobile field data collection、WordprocessingML 规范）
> 提示：§3.5 是论文的"理论钩子"，要明确写出本项目的做法如何填这个 gap。

### 4. Requirements & Analysis（~1,200 词）
- 4.1 Stakeholders & as-is process（图：As-Is vs To-Be 流程对比）
- 4.2 Functional requirements（表：编号 R1…R12，含验收方式）
- 4.3 Non-functional / constraints：现场无网、只用手机、报告版式不可变、数据不能丢、不引入服务端
- 4.4 Scope decisions & trade-offs（明示"不做"的 6 项，以及为什么）
- 4.5 Acceptance criteria（这张表就是最后 §8 的验收清单）

> 素材：`docs/requirements/需求报告.txt`、`docs/management/UI-设计.md`（范围与决策）、`docs/management/交付验收报告-v1.0.1.md` §2
> 图表：Table 4.1 需求-验收对照表（直接复用验收报告 §2/§6）

### 5. System Design（~1,500 词）
- 5.1 Architecture overview（图：静态壳 / IndexedDB / docx 引擎 / SW 缓存）
- 5.2 Data model（4 张业务表 + 图片表 + meta；为什么没有外键就要手写级联）
- 5.3 **Report fidelity design**：把客户报告拆成"版式规格 JSON + 11 个后处理补丁"
- 5.4 Image pipeline：EXIF 摆正 → 等比缩放 → 现压 → 缩略图（为什么原图原样入库）
- 5.5 Offline & update strategy：内容指纹版本化、不自动 skipWaiting
- 5.6 Design decisions as ADRs（挑 6 条写"选项—取舍—结论"）
  1. 纯静态无后端 vs 轻后端　2. IndexedDB vs SQLite-WASM　3. docx 库 vs 手写 OOXML
  4. 三道闸门 vs 一道闸门　5. 个人信息放 meta 表（不升 schema 版本）　6. 版本号单一真相源（`product.js`）

> 素材：`docs/management/M5-设计.md`（架构与闸门章节）、`docs/management/UI-设计.md`
> 图表：Figure 5.1 架构图（可直接用 `deliverables/prp/architecture.png`）

### 6. Implementation（~1,800 词）
- 6.1 Stack & repo layout（为什么"无打包器 + import map"）
- 6.2 Data layer & transaction discipline（IndexedDB 的"await 陷阱"）
- 6.3 Report engine & the 11 patches（表：补丁 → 现象 → 修法）
- 6.4 Attachment (附页) pipeline（两列信息表、每份独立成页、缺失降级）
- 6.5 UI shell（移动优先、底部 Tab 与操作条、`[hidden]` 与 SVG 命名空间两个真机坑）
- 6.6 Release engineering（交付包自检、`.mjs` MIME、VERSION.txt、sha256）
- 6.7 Code-level lessons（"契约冻结的是 id/class，不是 DOM 层级"这类）

> 素材：`web/app/**`、`docs/management/M5-设计.md` §1/§9、`docs/management/v1.0.1-发布清理.md`

### 7. Evaluation & Quality Assurance（~2,000 词，**论文的核心章节**）
- 7.1 Test strategy overview（图：五层金字塔：单元 → 引擎对拍 → 版式闸门 → 桌面 E2E → 安卓）
- 7.2 **The three gates**（A 复刻冻结基线 / B 对齐真实客户报告 / C 无 Python 自检）+ **敏感性验证**（7 项下毒）
  - 表：每道闸门"比了什么 / 不比什么 / 盲区是什么"
  - 关键论证：0 差异不是终点，"这个属性有没有被比"才是（引 M5 §4.6 的盲区案例）
- 7.3 Fidelity results：逐属性 0 差异 + 产物字节级复核（python-docx / Pillow）
- 7.4 **Real-environment verification**（本项目的独特之处）
  - 桌面 21 项 + 安卓 14 项；表格：每层抓到的问题清单（9 个缺陷表）
  - 三个 P0 的故事线：`boot()` 入口未覆盖 → `nodebuffer` 平台差异 → 备份导入无测试
  - 一句可引用结论：**"绿"要先问两件事：这个属性被比了吗？这个环境和用户的一样吗？**
- 7.5 Performance & load（表：20 份附页 0.93s、连续导出、长任务 50ms、堆增长）
- 7.6 Threats to validity（jsdom 与浏览器差异、模拟器与真机差异、无 iOS 设备）

> 素材：`docs/management/v1.0.1-浏览器E2E验证报告.md`（全部数字与截图）、`tools/verify_all.py`、`tools/verify_gate_sensitivity.py`
> 图表：Figure 7.1 收敛曲线（`deliverables/prp/gate-convergence.png`）、Figure 7.2 敏感性表（`gate-sensitivity.png`）、Table 7.1 缺陷表

### 8. Results, Discussion & Limitations（~1,200 词）
- 8.1 Requirements coverage（需求表 → 通过/有条件通过/不在范围）
- 8.2 What worked and why（保真靠"把报告当规格"+ 可执行闸门）
- 8.3 What we'd do differently（更早引入真浏览器 E2E；更早给"导入"配测试）
- 8.4 Limitations：iOS 未验、手势未验、数据不跨设备、内网 http 无离线/安装（安全上下文）
- 8.5 Business impact（现场时间节省估算、返工率、报告一致性）

> 素材：`docs/management/交付验收报告-v1.0.1.md` §2/§6/§7（几乎可直接翻译）

### 9. Conclusion & Future Work（~600 词）
- 3 条结论（对应 §1.3 的贡献）
- Future work：iOS 适配与真机验证、多设备协同（需服务端）、报告模板可配置化、离线冲突合并

### 10. References & Appendices
- References（GB/ISO 标准、WordprocessingML、PWA、测试方法论相关）
- Appendix A：架构与数据模型细节
- Appendix B：11 个补丁的对照表
- Appendix C：测试清单与复跑命令
- Appendix D：客户部署与使用说明（摘要）

---

## 2. 图表清单（多数已经存在，直接复用）

| 编号 | 内容 | 来源 | 状态 |
| --- | --- | --- | --- |
| Fig 5.1 | 架构对比图（Flask 参考实现 ↔ 离线 PWA） | `deliverables/prp/architecture.png` | ✅ 已有 |
| Fig 7.1 | 闸门收敛曲线（201→33→2→0） | `deliverables/prp/gate-convergence.png` | ✅ 已有 |
| Fig 7.2 | 闸门敏感性（7 项下毒） | `deliverables/prp/gate-sensitivity.png` | ✅ 已有 |
| Fig 7.3 | 测试总览（348 / 239 / 16 / 21 / 14） | `deliverables/prp/test-summary.png`（数字需按最终值刷新） | ⚠️ 刷新 |
| Fig 7.4 | 安卓实机截图拼图（4 张：主流程 / 键盘 / 安装 / 离线） | `_work/emu/*.png` | ✅ 已有，需排版 |
| Fig 7.5 | 修复前后对照（键盘遮挡：bar.bottom 774 → 478） | 同上 | ✅ 已有数据 |
| Table 4.1 | 需求-验收对照表 | 验收报告 §2 | ✅ 已有 |
| Table 5.1 | 数据模型 | M5 设计 §2 | ✅ 已有 |
| Table 6.1 | 11 个后处理补丁 | M5 设计 §1.4 | ✅ 已有 |
| Table 7.1 | 9 个缺陷（级别/发现方式/根因/防线） | 验收报告 §5 | ✅ 已有 |
| Table 7.2 | 性能与负载实测 | E2E 报告 §5 / 验收报告 §4 | ✅ 已有 |

---

## 3. 时间表（今天 11-12 → 12-05）

| 日期 | 里程碑 | 产出 |
| --- | --- | --- |
| 11-12 ~ 11-14 | 锁定骨架与数字口径；补文献清单（10 篇） | 本骨架定稿 + References 初稿 |
| 11-15 ~ 11-18 | 写 §4 需求、§5 设计（含 6 条 ADR） | Draft v1 前两章 |
| 11-19 ~ 11-22 | 写 §6 实现、§7 评估（**核心**，配 5 张图） | Draft v1 §6/§7 |
| 11-23 ~ 11-25 | 写 §2 引言、§3 文献、§8 结果与限制、§9 结论 | Draft v1 全文 |
| 11-26 ~ 11-28 | Abstract、图表排版、交叉引用、术语统一 | Draft v2（完整可读） |
| 11-29 ~ 12-01 | 自查（逻辑/数字/引用）+ 客户方事实核对 | Draft v3 |
| 12-02 ~ 12-03 | 润色（英文语言）、页数与格式合规 | Near-final |
| 12-04 | 最终提交前检查（文件名/PDF/附件/封面） | **Final** |
| 12-05 | 提交 | — |

**写作顺序建议**：§4 → §5 → §6 → §7 → §8 → §9 → §2 → §3 → Abstract。
（先写"有素材的硬章节"，最后写引言与摘要，避免反复重写。）

---

## 4. 写作时的"事实口径"（避免数字前后不一致）

论文里可以放心引用的数字（都来自仓库可复跑的命令）：

| 口径 | 值 | 出处/命令 |
| --- | --- | --- |
| Python 测试 | **348** | `python -m pytest -q` |
| 前端 Node 测试 | **239** | `node --test "web/tests/*.test.mjs"` |
| 版式闸门条数 | **16** | `python tools/verify_all.py` |
| 闸门 A/B/C 差异 | **0**（A 两半 + B + C） | 同上 |
| 敏感性下毒 | **7/7 被抓住** | `python tools/verify_gate_sensitivity.py` |
| 桌面 E2E | **21 项全绿** | `npm run test:e2e` |
| 安卓回归 | **14 项断言全绿，0 控制台错误** | `npm run test:android` |
| 交付包 | 53 文件 / 465 KB / sha256 `245f5c9…` | `dist/*.sha256` |
| 20 份附页导出 | 0.93 s，docx 59 KB | E2E 实测输出 |
| 连续导出 ×3 | 0.82 / 0.89 / 0.87 s | 同上 |
| 长任务 | 最长 50 ms | 同上 |
| 缺陷总数 | 9（3×P0、4×P1、2×P2） | 验收报告 §5 |

> 提醒：PRP 的 `test-summary.png` 上写的是 234/58，最终报告请用 **239** 并重新生成该图
> （`python tools/make_prp_figures.py --refresh`）。

---

## 5. 现在就该做的三件事

1. **确认语言与篇幅**（英文 9–12k 词？还是课程允许中文？）——影响后面所有写作安排。
2. **补 8–12 篇文献**（PWA/offline、golden master/differential testing、移动端现场数据采集、WordprocessingML），
   我可以先把候选清单拉出来，你确认后我写成可引用的条目。
3. **刷新 `test-summary.png` 的数字**（239 / 348 / 16 / 21 / 14），论文与 PRP 共用。

> 你确认后我可以直接开始逐章起草（从 §4 需求与 §5 设计开始），每章先给英文初稿 + 中文对照说明，
> 你审一遍再往下写；所有表格与图都从仓库现有材料生成，不手抄数字。
