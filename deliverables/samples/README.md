# 样例报告（5 份）

由 `tools/generate_sample_reports.py` 生成；检测数据来自 `docs/samples/检测结果案例.xlsx`，
项目信息为构造值。用于章程 Objective 3 的度量：

> Five sample reports generated from test data match the client's template in structure and formatting.

## 清单

| 文件 | 项目编号 | 房屋名称 | 检测日期 | 立柱检测面 | 横梁检测面 |
| --- | --- | --- | --- | --- | --- |
| `JCZG_金骐智谷_检测报告.docx` | JCZG | 金骐智谷 | 2026-09-03 | 10 | 5 |
| `JC2Q_金骐智谷二期_检测报告.docx` | JC2Q | 金骐智谷二期 | 2026-09-10 | 10 | 5 |
| `HXDS_华兴大厦_检测报告.docx` | HXDS | 华兴大厦 | 2026-09-18 | 10 | 5 |
| `ZJGC_中建广场_检测报告.docx` | ZJGC | 中建广场 | 2026-10-08 | 10 | 5 |
| `BLYY_宝利医院_检测报告.docx` | BLYY | 宝利医院 | 2026-10-15 | 10 | 5 |

## 每份报告的预期结构

- 项目信息段 5 行（项目编号 / 房屋名称 / 房屋地点 / 委托单位 / 检测日期）
- 「幕墙立柱截面尺寸检测结果」标题 + 表格（5 条记录、10 个检测面；B/H 两面纵向合并四列）
- 「幕墙横梁截面尺寸检测结果」标题 + 表格（5 条记录、5 个检测面；单面不合并）
- 固定备注：`备注：检测构件位置详见检测工作内容附件 18。`
- **不含玻璃模块**（范围外）

## 结构一致性验证

见 `deliverables/fidelity-report.md`（由 `tools/compare_report_with_sample.py` 生成）：
从样例回灌其自身数据后重新生成并逐属性比较，覆盖表格/行/单元格全部版式属性与合并网格。
