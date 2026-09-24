# 建筑幕墙检测报告生成工具

Existing Curtain Wall Inspection Data Recording and Report Generation Tool —— NYU MS in Management and Systems 毕业项目（Capstone）。

面向幕墙检测工程师的本地 Web 工具：录入立柱 / 横梁截面尺寸检测数据与缺陷检测记录，一键导出与客户模板排版一致的 Word 检测报告。

---

## 当前状态

**M3（缺陷填报完善 + 项目关联 + 附页导出）已完成** —— 2026-09-24

| 里程碑 | 内容 | 状态 |
| --- | --- | --- |
| M0 | 拆包、数据库 schema、Word A4 报告底座 | ✅ 完成 |
| M1 | 项目管理 CRUD + 立柱/横梁检测记录录入 | ✅ 完成 |
| M2 | 项目级 Word 导出（与样例**逐属性对拍一致**） | ✅ 完成 |
| M3 | 缺陷填报完善（图片/规范/建议/绑定项目）+ 附页导出 | ✅ 完成 |
| M4 | 报告管理（列表/筛选/详情/删除） | ⏳ 待开发 |
| UI | 移动优先响应式改造（静态壳 + 客户端渲染，为 M5 铺路） | ⏳ 待开发 |
| M5 | 前端本地化改造（IndexedDB + docx JS + 纯静态 PWA，移除 Flask） | ⏳ 待开发 |

M3 交付：隐患图片（必填、拍照/相册、≤20MB、原图落盘且保留原文件名）、相关规范/补充建议、绑定项目；项目详情显示真实关联报告与「附加 N 份并导出 / 仅导出检测报告」二选一；导出附页（每份独立成页、9 行两列信息表、导出时现压的图片副本、图片缺失时降级）。

> **架构说明**：M5 将把导出与数据层迁移到前端（IndexedDB + docx JS），移除 Flask 后端改为纯静态 PWA。M2/M3 的 Python 实现是该迁移的**参考实现与规格来源**，`report_layout.json` 中的数值可直接被 JS 复用。

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
| `requirements.txt` | `flask`、`python-docx`、`pillow` | 运行应用所需（Pillow 用于隐患图片的压缩与 EXIF 摆正） |
| `requirements-dev.txt` | 追加 `pytest`、`openpyxl` | 跑测试与 `tools/verify_case_data.py` |

## 测试

```powershell
python -m pip install -r requirements-dev.txt     # pytest + openpyxl
python -m pytest -q                               # Python 测试套件（170 项）
python -m pytest tests/test_word_report.py -v     # 只跑 Word 版式相关
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

前端 JS 功能测试（可选，需要 Node.js）：

```powershell
npm install --no-save jsdom
node tests/js/record_form.test.js    # 35 项：实时最小值、非法读数拦截、增删检测面行
```

## 交付物

| 路径 | 说明 |
| --- | --- |
| `deliverables/samples/` | 5 份样例报告 + 清单（章程 Objective 3 的度量证据） |
| `deliverables/fidelity-report.md` | 与客户样例的逐属性对拍报告 |
| `tests/fixtures/generated_baseline.docx` | 回归基线：生成物偏离即测试失败，直到显式重新冻结 |

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
│   ├── routes/                pages.py / projects.py / records.py / defects.py
│   ├── services/
│   │   ├── thickness.py       5 个厚度读数 -> 最小值、格式化
│   │   ├── projects.py        项目读写、列表统计、删除影响面
│   │   ├── measurements.py    记录表单解析、事务化增删改、分组读取
│   │   ├── defects.py         缺陷表单解析、读写、附页渲染数据装配
│   │   ├── images.py          隐患图片：上传校验、落盘命名、导出时压缩
│   │   └── word_report.py     A4 底座 + 表格原语 + 检测表/附页构建
│   ├── templates/             base / index / projects / records / defects
│   └── static/                css/app.css · js/{app,record_form,defects_form}.js
├── reports/                   导出的 .docx（gitignore）
├── uploads/defects/           隐患图片（gitignore）
├── tests/
│   ├── fixtures/              金骐智谷_金骐_检测报告.docx（对拍基准，勿改）
│   │                          generated_baseline.docx（回归基线）
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
│   ├── test_text_fit.py       列宽适配度量工具
│   ├── test_extract_layout_spec.py 版式提取器与规格一致性
│   └── test_web.py            路由与完整链路冒烟
├── deliverables/              5 份样例报告 + 对拍报告（章程 Objective 3 的证据）
├── tools/                     compare_report_with_sample.py · verify_case_data.py
│                              generate_sample_reports.py · make_report_template.py
│                              case_data.py（案例解析，多工具共用）
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

## 文档索引

- `docs/requirements/` 需求报告（原始需求全文）
- `docs/management/` 项目章程、开发计划、M1 设计、阶段交接记录
- `docs/management/signed/` 签署类文档（含签名与联系方式，不入仓库）
- `docs/samples/` 检测结果案例（Excel + 截图）
