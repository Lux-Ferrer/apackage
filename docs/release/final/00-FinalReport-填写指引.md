# 收尾三件套：填写说明 + 待补清单 + 可直接粘贴的文本

> 目录：`docs/release/final/`
> 生成时间：2026-11-24

---

## 0. 三个文件分别是什么

| 文件 | 性质 | 处理 |
| --- | --- | --- |
| `07-Part1 SponsorsProjectAcceptanceDocument V3.3.docx` | **甲方验收文件 · 计划部分**（Goal + Objectives，需甲方签字） | ✅ 已填，另存为 `… - Zeyu Jin.docx`（**原模板未改动**） |
| `07-Part2 SponsorsProjectAcceptanceDocument V3.3.docx` | **甲方验收文件 · 结果部分**（逐条判定 + 评分 + 双方签字） | ✅ 已填，另存为 `… - Zeyu Jin.docx` |
| `06 AppliedProject FinalReport Guidelines v6.21.docx` | **结题论文的写作规范**（50 页正文 + 装订格式） | ⚠️ **不是表单，没法"填"** —— 它是 Final Report 的规格书，见 §3 |

填好的两份可以直接拿去给姚部长签字；`06` 我们按它的要求写论文（下面 §4 给了能直接粘贴的封面页与摘要）。

---

## 1. 已替你填好的内容（Part 1 / Part 2）

| 字段 | 填的值 |
| --- | --- |
| Project Title | Curtain Wall Inspection Report Tool: An Offline-First Mobile Web Application for On-Site Inspection Records and Word Report Generation |
| Student Name | Zeyu Jin |
| Sponsoring Organization | MCC Central Research Institute of Building and Construction (Shenzhen) Co., Ltd. |
| Project Goal | 一句话：交付一个**无服务器、可离线**的手机工具，让现场检测员录入立柱/横梁截面尺寸（每面 5 个读数、最小值自动算）与缺陷记录，并生成与客户现有 Word 报告**同版式**的检测报告（含附页） |
| Objective #1 | **报告版式保真**：三道独立对拍闸门 0 差异 + 7/7 下毒检出 |
| Objective #2 | **功能覆盖**：追溯矩阵 43 条全实现，598 项自动化测试（348 Python + 250 前端）+ 21 项 E2E 全绿 |
| Objective #3 | **离线无服务器**：整条链路 0 条外发请求；封掉 App 网络后仍能导出 Word |
| Objective #4 | **真机可用**：触控区 ≥44px、键盘不遮保存、返回键不误退 |
| Objective #5 | **可交付可交接**：版本化交付包（网页 + APK）+ sha256 + 三份文档 + 0 个 P0/P1 遗留 |
| Part 2 日期 | Planned 2026-09-10 → 2026-12-05；Actual 2026-09-10 → **2026-11-24** |
| Part 2 判定 | Goal = **Yes**；Objective #1~#5 全部 **HAS BEEN MET**，每条后面附了实测证据 |

> `Actual End Date` 我填的是**交付包完成日**（2026-11-24）。如果学校要求填"签字/验收日"，等姚部长签完改成那天即可。

## 2. 必须由你/甲方补的 4 处（我不能编造）

| 位置 | 现在 | 要填什么 |
| --- | --- | --- |
| Part 1 · Project Sponsor Name and Title | 下划线空着 | 甲方对接人**英文姓名 + 职务**（如 "Mr. Yao, Department Director"） |
| Part 1 · Sponsor Contact Information | 下划线空着 | 邮箱 + 电话 |
| Part 2 · Sponsor's evaluation | `A / A- / B+ …` 未勾选 | 由甲方勾选 |
| Part 2 · Acceptance 三选一 + 两处签字/日期 | 全部空着 | 由甲方勾选并**手签英文名**（规范明确：不得用打印体/手写字体） |

另外：Part 2 里每条 Objective 后面有 `Sponsor Initials: ______`，甲方逐条小签即可。

## 3. `06 Guidelines` 的硬性要求（写论文时逐条对照）

| 要求 | 具体 |
| --- | --- |
| 篇幅 | **正文最少 50 页**，**双倍行距**（不含封面/摘要/目录/附录） |
| 字体 | Calibri 12 或 Verdana 11；标题可更大 |
| 页边距 | 右边 1"，**左边 1.5"** |
| 页眉页脚 | **页眉留白**；页脚**只放居中页码** |
| 图表 | 居中；编号 `X-y`（X = 章号）；要有 Table of Figures / Table of Tables |
| 结构 | 封面 → Abstract → 目录 →（图/表目录）→（Dedication）→ Acknowledgements → Declaration →（缩写表）→ 正文各章 → **Appendices** |
| 附录必备 | **签好字的 Acceptance Document（Part 1 + Part 2，按 PDF 插进文档）**；Project Plan / 基线 vs 实际 WBS 偏差讨论；APA 格式参考文献；其他支持材料 |
| 提交 | Word 或 PDF，**单个文件**上传 Brightspace，文件名里带论文标题 |

## 4. 可直接粘贴的封面页与摘要（按规范写好，去掉了 `<brackets>`）

### 4.1 封面页字段

```
Curtain Wall Inspection Report Tool:
An Offline-First Mobile Web Application for On-Site Inspection Records
and Word Report Generation

by

Zeyu Jin

A paper submitted in partial fulfillment of the requirements for the degree of
Master of Science
at the
Division of Programs in Business
School of Professional Studies
New York University

Fall, 2026
```

### 4.2 Abstract（约 250 词，可直接用）

> Field inspectors at MCC Central Research Institute of Building and Construction (Shenzhen) record
> curtain-wall cross-section measurements and defect findings on paper, then re-type them into a fixed
> Word template at the office. The re-typing introduces transcription errors, and the report layout has to
> be reproduced by hand for every project. This applied project delivered a server-less, offline-first
> mobile web application that removes that step: inspectors capture five thickness readings per detection
> face (with the minimum computed automatically), photograph defects, and generate the sponsor's existing
> Word inspection report — including defect-report attachment pages — directly on the phone.
>
> The main technical risk was report fidelity: "looks the same" is not the same as "is the same". The
> project therefore treated the sponsor's Word report as an executable specification and built three
> independent comparison gates — a replicated frozen baseline, the sponsor's real cropped report, and a
> language-neutral fingerprint self-check — that compare body text, tables, rows, cells and embedded
> images attribute by attribute. All three gates currently report zero differences, and a sensitivity test
> catches seven of seven deliberately injected layout defects. Verification continued in increasingly
> realistic environments: 598 automated tests, 21 real-browser end-to-end cases, and 14 assertions on an
> Android device, where the delivery exposed nine defects that the unit-test layer could not see —
> including a backup-import failure that would have made the tool's only data-recovery path unusable.
>
> The result is a reproducible delivery package (static web bundle plus Android APK) with a recorded
> SHA-256, a deployment guide and an end-user manual, in use on real devices without any back-end service.

## 5. 接下来写正文建议

已有的素材（不重复造）：`docs/management/Final-Report-骨架.md`（章节 + 图表清单 + 日程）、
`交付验收报告-v1.0.2.md`（证据与缺陷表）、`需求对照检查-v1.0.2.md`（需求追溯）、
`v1.0.1-浏览器E2E验证报告.md`（两轮 E2E 实测）。

按规范要补的**新内容**主要是：Literature Survey（8–12 篇，APA）、Situational Analysis（把之前的文档并入）、
Detailed Project Chronology and Critique、Lessons Learned。

> 要不要我从 §4「Introduction / Problem Description」开始，按章起草正文（每章先给英文初稿 + 中文对照），
> 你审一版我再往下写？50 页双倍行距大约 12,000–14,000 词，建议分 5 批给你。
