# docs —— 项目文档

本目录存放与代码分离的文档与参考资料。

| 目录 | 内容 |
| --- | --- |
| `requirements/` | 需求报告（`需求报告.txt`、`幕墙检测APP需求报告.docx`）—— 完整需求全文，含已确认不做出的模块 |
| `management/` | `03 ProjectCharter 3.0.docx`（范围与里程碑的权威依据）、`后续开发计划.md`（表结构/模块清单/M0~M5/工时估算）、`2026-09-09_阶段1-PoC与开发计划.md`（阶段交接记录） |
| `management/signed/` | 签署类文档：`04 Project_sponsor_Agreement_v5.3_signed.pdf`、`07-Part1 SponsorsProjectAcceptanceDocument V3.3_signed.pdf`、`Sign.pdf`（原始签名页扫描）、`Sign_p2.pdf`/`sign2.pdf`、`Sign_p2.docx`（签名页 Word 版）。**含签名与联系方式，已在 `.gitignore` 中排除，不入仓库** |
| `samples/` | `检测结果案例.xlsx`（立柱 10 行、横梁 5 行真实数据）、两张案例截图 |

## 注意

- 范围冲突时以 `management/03 ProjectCharter 3.0.docx` 为准；
- `samples/检测结果案例.xlsx` 是 M2 的验收数据来源，Word 导出必须能用它灌出与样例一致的表格；
- Word 版式的**对拍基准**不是这里的截图，而是真实客户报告 `A06YG-2026-001…doc` 第 12-13 页的裁剪版
  `tests/fixtures/检测表_真实裁剪.docx`（用 `python tools/build_fixture.py` 从该 .doc 重新裁出），请勿修改该文件；
  `tests/fixtures/金骐智谷_金骐_检测报告.docx` 现在只作**字体/主题**来源（见 `config.FONT_SAMPLE`）。
