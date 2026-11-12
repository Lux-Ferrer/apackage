# 进度会议上传材料（status_update_package）

学校要求上传 **Current WBS (PDF)** 与 **Work Product Drafts**。这个包就是按这两项组织的，
每份文件都能从仓库重新生成，不是手搓的。

| 文件 | 内容 | 来源 |
| --- | --- | --- |
| `ReadMe.txt` | 给教授的封面说明（英文，~180 词） | `tools/make_status_package.py` 内嵌 |
| `WBS_Update.pdf` | 当前 WBS + 甘特图（40 个任务，33 Completed / 3 In Progress / 4 Planned，A3 横版一页） | `python tools/make_current_wbs.py` |
| `UI_Screenshots.pdf` | 三张界面证据（数据录入 / 报告列表 / 项目详情，375×812 手机视口） | `node web/e2e/capture-status-shots.mjs` |
| `Sample_Report.docx` | 真实导出的 Word 样例（4 条检测记录 + 3 份附页，16 KB） | 同上（脚本顺手导出） |
| `QA_Evidence_Summary.md` | 测试证据摘要：英文 At-a-glance + 从验收报告第 4、5 节抽取的原始表格 | `tools/make_status_package.py` |
| `QA_Evidence_Summary.pdf` | 上面那份的 PDF（Word 转出，两页 A4） | 见下 |

## 重新生成（4 步，约 1 分钟）

```powershell
# 1) 当前 WBS（Excel + PDF，状态口径在 tools/make_current_wbs.py 的 STATUS_BY_ID）
python tools/make_current_wbs.py

# 2) 三张界面图 + 样例 Word（自起服务，跑完自动关）
node web/e2e/capture-status-shots.mjs

# 3) 组装包（ReadMe / QA 摘要 md / 截图 PDF / 拷贝 WBS 与样例）
python tools/make_status_package.py

# 3b) QA 摘要 PDF：Word 打开 _work/status/QA_Evidence_Summary.docx → 另存为 PDF
#     （这一步在 Word 里做，或参考 git 历史里的 COM 脚本；产物放到包里同名）

# 4) 打包
python tools/make_status_package.py --zip-only
```

> ⚠️ 顺序要点：`--zip-only` 之前不要重跑第 3 步 —— 第 3 步会清空包目录，
> 把第 3b 步生成的 `QA_Evidence_Summary.pdf` 一起删掉。

## 两个口径决定（免得以后对不上）

1. **WBS 不直接改基线文件**。`deliverables/WBS_Gantt_ZeyuJin.xlsx` 是"批准的基线"，
   而且 `tests/test_wbs_gantt.py` 把它逐列逐色锁死了。所以状态快照是**另生成**一份
   （`WBS_Gantt_ZeyuJin_Current.xlsx` + `Current_WBS_Update.pdf`），两者与基线共用
   `tools/make_wbs_gantt.py::TASKS` 这一份任务数据。
2. **状态更新周期**：每次里程碑变化只改 `tools/make_current_wbs.py::STATUS_BY_ID` 一个地方，
   Excel 与 PDF 会同时变；`AS_OF_LABEL` / `TODAY` 一起改，图上的"今天"虚线才准。
