# 建筑幕墙检测报告生成工具

Existing Curtain Wall Inspection Data Recording and Report Generation Tool —— NYU MS in Management and Systems 毕业项目（Capstone）。

面向幕墙检测工程师的本地 Web 工具：录入立柱 / 横梁截面尺寸检测数据与缺陷检测记录，一键导出与客户模板排版一致的 Word 检测报告。

---

## 当前状态

**M1（项目管理 + 检测记录录入）已完成** —— 2026-09-23

| 里程碑 | 内容 | 状态 |
| --- | --- | --- |
| M0 | 拆包、数据库 schema、Word A4 报告底座 | ✅ 完成 |
| M1 | 项目管理 CRUD + 立柱/横梁检测记录录入 | ✅ 完成 |
| M2 | 项目级 Word 导出（立柱/横梁表，与样例对拍） | ⏳ 待开发 |
| M3 | 缺陷报告完善（图片/规范/建议/绑定项目）+ 附页导出 | ⏳ 待开发 |
| M4 | 报告管理 | ⏳ 待开发 |
| M5 | 测试、打磨、交付打包 | ⏳ 待开发 |

M1 交付：项目增删改查（编号唯一、列表显示记录数、删除二次确认并提示级联影响）；立柱/横梁两种模板的检测记录录入，每检测面 5 个厚度读数并实时计算最小值；多检测面构件；编辑时模板类型锁定；项目详情展示记录数与关联报告。

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

使用顺序：新建项目 → 进入项目详情 → 添加检测记录（选立柱或横梁模板）→ 填写构件信息与检测面读数 → 保存。

## 依赖

| 文件 | 内容 | 用途 |
| --- | --- | --- |
| `requirements.txt` | `flask`、`python-docx` | 运行应用所需 |
| `requirements-dev.txt` | 追加 `pytest`、`openpyxl` | 跑测试与 `tools/verify_case_data.py` |

## 测试

```powershell
python -m pip install -r requirements-dev.txt     # pytest + openpyxl
python -m pytest -q                               # Python 测试套件（132 项）
python -m pytest tests/test_word_report.py -v     # 只跑 Word 版式相关
```

两个额外的验证工具：

```powershell
python tools/verify_case_data.py     # 用 docs/samples 的真实案例数据走完整录入链路并逐面比对最小值
python tools/make_report_template.py # 从样例重生报告底座（webapp/resources/report_base.docx）
```

前端 JS 功能测试（可选，需要 Node.js）：

```powershell
npm install --no-save jsdom
node tests/js/record_form.test.js    # 35 项：实时最小值、非法读数拦截、增删检测面行
```

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
│   │   └── report_base.docx   Word 报告底座（由样例派生，见下）
│   ├── routes/                pages.py / projects.py / records.py / defects.py
│   ├── services/
│   │   ├── thickness.py       5 个厚度读数 -> 最小值、格式化
│   │   ├── projects.py        项目读写、列表统计、删除影响面
│   │   ├── measurements.py    记录表单解析、事务化增删改、分组读取
│   │   └── word_report.py     A4 底座 + 表格原语（列宽/边框/合并/行高）
│   ├── templates/             base / index / projects / records / defects
│   └── static/                css/app.css · js/app.js · js/record_form.js
├── reports/                   导出的 .docx（gitignore）
├── uploads/defects/           隐患图片（gitignore）
├── tests/
│   ├── fixtures/              金骐智谷_金骐_检测报告.docx（对拍基准，勿改）
│   ├── js/record_form.test.js 前端功能测试（jsdom）
│   ├── test_db.py             表结构、约束、级联语义
│   ├── test_thickness.py      最小值计算
│   ├── test_word_report.py    A4 页面、字体、表格原语、与样例参数对齐
│   ├── test_measurements.py   表单解析、事务回滚、编辑锁定
│   ├── test_projects.py       项目 CRUD 与校验
│   ├── test_records.py        记录 CRUD、模板锁定、最小值链路
│   └── test_web.py            路由与完整链路冒烟
├── tools/                     make_report_template.py · verify_case_data.py
└── docs/                      需求、计划、章程、案例资料、设计文档
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

## 文档索引

- `docs/requirements/` 需求报告（原始需求全文）
- `docs/management/` 项目章程、开发计划、M1 设计、阶段交接记录
- `docs/management/signed/` 签署类文档（含签名与联系方式，不入仓库）
- `docs/samples/` 检测结果案例（Excel + 截图）
