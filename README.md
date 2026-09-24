# 建筑幕墙检测报告生成工具

Existing Curtain Wall Inspection Data Recording and Report Generation Tool —— NYU MS in Management and Systems 毕业项目（Capstone）。

面向幕墙检测工程师的本地 Web 工具：录入立柱 / 横梁截面尺寸检测数据与缺陷检测记录，一键导出与客户模板排版一致的 Word 检测报告。

---

## 当前状态

**M0（代码底座）已完成** —— 2026-09-22

| 里程碑 | 内容 | 状态 |
| --- | --- | --- |
| M0 | 拆包、数据库 schema、Word A4 报告底座 | ✅ 完成 |
| M1 | 项目管理 + 立柱/横梁检测记录录入 | ⏳ 待开发 |
| M2 | 项目级 Word 导出（立柱/横梁表，与样例对拍） | ⏳ 待开发 |
| M3 | 缺陷报告完善（图片/规范/建议/绑定项目）+ 附页导出 | ⏳ 待开发 |
| M4 | 报告管理 | ⏳ 待开发 |
| M5 | 测试、打磨、交付打包 | ⏳ 待开发 |

M0 具体交付：代码按职责拆包（路由 / 数据访问 / 服务）；4 张表的 schema 与建库逻辑；Word 报告底座（A4 页面 + 样例字体 + 表格原语）；PoC 的缺陷填报链路迁移进蓝图并保持可用；56 项自动化测试。

## 范围

**包含**：立柱 / 横梁截面尺寸检测（每检测面 5 个厚度值，自动计算最小值）· 缺陷检测填报 · 项目管理 · 项目级 Word 报告导出 · 本地 SQLite 存储与本地 Web 部署。

**不包含**（已确认范围外）：膜厚检测 · 玻璃面板尺寸及厚度检测 · 速记 · 统计 · 登录 · 结构安全评定 · 原生手机 App。

> 依据 `docs/management/03 ProjectCharter 3.0.docx`。

## 运行

```powershell
python -m pip install -r requirements.txt
python app.py
```

浏览器打开 <http://127.0.0.1:5000>。首次启动会自动按 `webapp/schema.sql` 建库（`defects.db`）。

## 测试

```powershell
python -m pytest -q          # 全部测试
python -m pytest tests/test_word_report.py -v    # 只跑 Word 版式相关
```

导出的报告底座由样例派生，若 `webapp/resources/report_base.docx` 缺失或需要重建：

```powershell
python tools/make_report_template.py
```

## 目录结构

```text
Capstone/
├── app.py                     入口：create_app() + app.run()
├── requirements.txt
├── webapp/                    应用包
│   ├── __init__.py            应用工厂：注册蓝图、启动建库
│   ├── config.py              路径、预置缺陷类型、截面要求条文、检测面建议值
│   ├── db.py                  SQLite 连接 / 建库 / 查询助手
│   ├── schema.sql             4 张表：projects / measurement_records /
│   │                          thickness_readings / defects
│   ├── resources/
│   │   └── report_base.docx   Word 报告底座（由样例派生，见下）
│   ├── routes/                pages.py / projects.py / defects.py
│   ├── services/
│   │   ├── thickness.py       5 个厚度读数 -> 最小值、格式化
│   │   └── word_report.py     A4 底座 + 表格原语（列宽/边框/合并/行高）
│   ├── templates/             base / index / defects / projects
│   └── static/css/app.css
├── reports/                   导出的 .docx（gitignore）
├── uploads/defects/           隐患图片（gitignore）
├── tests/
│   ├── fixtures/              金骐智谷_金骐_检测报告.docx（对拍基准，勿改）
│   ├── test_db.py             表结构、约束、级联语义
│   ├── test_thickness.py      最小值计算
│   ├── test_word_report.py    A4 页面、字体、表格原语、与样例参数对齐
│   └── test_web.py            路由与完整链路冒烟
├── tools/make_report_template.py
└── docs/                      需求、计划、章程、案例资料
```

## Word 报告底座说明（重要）

报告必须与客户样例 `tests/fixtures/金骐智谷_金骐_检测报告.docx` 排版一致。样例的关键参数（均为实测值）：

| 项目 | 值 |
| --- | --- |
| 页面 | A4 `11906 × 16838` twips，四边页边距 `1440` |
| 字体 | 西文 Times New Roman；中文走主题字体（`eastAsiaTheme="minorEastAsia"`） |
| 立柱/横梁表 | 表宽 `8800` twips，固定布局，11 列 `492/553/614/480/760×6/2101` |
| 表头 | 2 行；「厚度检测结果 (mm)」横跨 7 列；其余 4 列纵向合并 |
| 行高 | 表头 600、数据 400（"至少"语义） |
| 单元格边距 | 上下 60 / 左右 80 twips |
| 边框 | single / sz=4 / auto，含内部横竖线 |

**为什么底座要从样例派生**：python-docx 自带模板的主题把中文字体映射成**宋体**，样例是**等线**。若新建文档后再"设置字体"，中文就会落到宋体上。`webapp/resources/report_base.docx` 保留了样例的 `theme1.xml` / `styles.xml` / `sectPr` 并清空正文，因此生成的新文档天然沿用样例字体，代码里不硬编码任何中文字体名。

## 关键业务规则

- 每个检测面的最小值为该面 5 个读数的派生值，**不落库**，导出保留两位小数（`webapp/services/thickness.py`）
- 检测面标签为短文本（真实数据：立柱 `B` / `H`，横梁 `t`），允许自由输入，不做枚举约束
- 同一构件有多个检测面时，Word 导出需把「楼层 / 构件位置 / 尺寸检测结果 / 截面尺寸要求」四列纵向合并
- 截面尺寸要求存**文案快照**；为空时显示「无」
- 删除项目 → 级联删除其检测记录；关联缺陷报告 `project_id` **置空保留**
- 隐患图片存文件路径（`uploads/defects/`），不入库为 base64/BLOB

## 文档索引

- `docs/requirements/` 需求报告（原始需求全文）
- `docs/management/` 项目章程、开发计划、阶段交接记录
- `docs/samples/` 检测结果案例（Excel + 截图）
