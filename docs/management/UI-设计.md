# UI 设计 —— 移动端优先改造（静态壳 + 客户端渲染，为 M5 铺路）

> 上游依据：`docs/requirements/需求报告.txt` **2.1 导航结构**、**3.2~3.7** 各模块的交互描述、
> `docs/management/后续开发计划.md`（登录/导航壳：Web 端把「底部 4 Tab」改造成顶部/侧边导航）。
> 前置：M1~M4 已完成（281 项测试全绿，四条基线闸门全绿）。
> 状态：**已确认，开始实施**（2026-09-25）。第 9 节的 4 个决策点全部按推荐方案执行：
> ①「我的」纳入「清除全部报告」；②`/` 重定向到 `/projects/`、模块进度搬到 `/about`；
> ③项目列表统一改卡片列表；④检测面名称移到展开区、摘要行保持纯展示。
> 实施分 UI-1~UI-5 五个阶段，每阶段结束跑全量测试 + 四条基线闸门。

---

## 0. 结论先说

| 项 | 结论 |
| --- | --- |
| 导航 | 底部 **3 个 Tab：项目 / 报告 / 我的**（需求的「应用」Tab 拆解进「报告」，见第 1 节） |
| 检测面录入 | `<table>` 8 列 → **`<ol>` + `<details>/<summary>` 摘要行 + 下级编辑**。折叠是**原生行为**，无 JS 也能用 |
| 三态着色 | 灰（未填）/ 黄（部分）/ 绿（完成）—— 表达**还剩多少活** |
| 警告灯 | **独立通道**，只在有非法读数时亮 —— 表达**能不能保存**。不与三态合并（理由见 3.5） |
| 构件信息 | label 左 / 控件右的两列网格（横向表格布局），桌面**复用同一布局**只加宽 |
| 断点 | 3 档；**只有 ≥960px 一处做结构性变化**（底部 Tab → 顶部导航） |
| 业务代码 | **零改动**：不动 `services/*` 的语义、不动 Word 导出链路的任何一个字节 |
| 新增功能 | 「我的」页（报告人卡 + 数据概览 + 数据管理 + 应用信息），见第 7 节与第 1.4 节的范围说明 |
| 工时 | 核心 **≈19.5h**（2.5 工作日）；含「我的」数据管理 **≈22.5h**（3 工作日） |
| 最大风险 | `record_form.js` 改造 + 移动端"折叠态藏起错误"—— 对策见第 6.2 与 7.3 节 |

**一句话原则**：这一阶段改的是「怎么画、怎么点」，**不改「数据是什么、存到哪、导出成什么」**。
所以四条基线闸门（Word 对拍 / 版式提取 / 案例校验 / 前端 JS）在本阶段结束时必须仍然全绿 —— 它们
和 UI 无关，**绿了就证明这次改造确实没碰业务**。

---

## 1. 底部 Tab 导航

### 1.1 与需求 2.1 的对照（先讲清取舍）

需求 2.1 原本是 **4 个主 Tab**，其中「应用」下还有 3 个子 Tab：

```
需求原文                                本设计
登录页                                  （范围外，已确认不做）
└─ 主界面（底部 4 Tab）
     ├─ 应用（3 个子 Tab）
     │    ├─ 工作台（速记）      ──→   范围外（已确认）
     │    ├─ 检测填报（缺陷报告） ──→   报告 Tab 的「+ 新建报告」入口
     │    └─ 报告管理            ──→   Tab ②「报告」
     ├─ 项目                     ──→   Tab ①「项目」
     ├─ 统计                     ──→   范围外（已确认）
     └─ 我的                     ──→   Tab ③「我的」
```

**为什么合并成 3 个而不是保留 4 个**：速记被砍掉之后，「应用」这个 Tab 里只剩「检测填报」一项 ——
为单一入口保留一个 Tab 会浪费一个拇指区，而且它和「报告管理」在数据上是同一条链路
（填完就进报告列表，需求 3.3.1 的流程图就是这么画的）。所以把**填报入口放在报告列表页右上角**
（M4 已经这么做了：列表页头部的「+ 新建报告」按钮）。统计 Tab 直接移出（范围外）。

> 这是本项目**第二次**把需求的 4 Tab 收敛为更少：后续开发计划里也写了「登录/导航壳：Web 端把
> 『底部 4 Tab』改造成顶部/侧边导航」。如果你更希望保留 4 个 Tab（把「填报」单列），说一声，
> 代价只是多一个 Tab 定义 + 一个空的中转页。

### 1.2 结构

```
┌─────────────────────────────┐
│ 顶栏（移动端只留标题，桌面端放导航）│   ← 现有 .topbar，移动端缩小
├─────────────────────────────┤
│                             │
│         内容区                │   ← main，底部留出 Tab 高度
│                             │
├─────────────────────────────┤
│   ▦        ▤        ◍       │   ← 底部 Tab（移动端固定）
│  项目      报告      我的      │
└─────────────────────────────┘
  ↑ env(safe-area-inset-bottom) 会被算进这条的高度
```

```html
{# templates/_nav.html —— 一个定义，渲染两处（顶栏 / 底栏），源文件不重复 #}
<nav class="{{ nav_class }}" aria-label="主导航">
  {% for item in nav_items %}
  <a class="nav-item {% if active_tab == item.key %}active{% endif %}"
     href="{{ url_for(item.endpoint) }}"
     {% if active_tab == item.key %}aria-current="page"{% endif %}>
      <span class="nav-icon" aria-hidden="true">{{ item.icon }}</span>
      <span class="nav-label">{{ item.label }}</span>
  </a>
  {% endfor %}
</nav>
```

- **移动端**：`position: fixed; bottom: 0`，3 等宽，图标在上文字在下。
- **桌面端（≥960px）**：同一个 partial 用 `nav_class="topnav"` 再渲染一次，进顶栏、横排、隐藏图标。
  两份 DOM 是同一份模板产出，**只有输出重复、源码不重复**；`active` 逻辑也共用。
- **`active_tab` 由端点前缀推导**，不靠每个路由传参（漏传就会丢高亮）：

```python
# webapp/__init__.py 的 context_processor
_TAB_BY_PREFIX = {"projects": "projects", "records": "projects",
                  "reports": "reports", "defects": "reports",
                  "me": "me", "pages": "me"}
@app.context_processor
def _nav_context():
    endpoint = (request.endpoint or "")
    prefix = endpoint.split(".")[0]
    return {"active_tab": _TAB_BY_PREFIX.get(prefix, "projects"),
            "nav_items": NAV_ITEMS}
```

注意 `records.*`（检测记录）归到「项目」Tab，`defects.*`（缺陷填报是报告链路的起点）归到「报告」Tab ——
这样从项目详情钻进检测记录表单时，用户仍感觉自己在「项目」里。

### 1.3 哪些页面显示 Tab、哪些隐藏

**规则**：**列表 / 概览 / 详情等"浏览类"页面显示 Tab；表单 / 编辑类页面隐藏 Tab，改用底部固定操作条。**

| 页面 | Tab | 底部固定条 | 理由 |
| --- | --- | --- | --- |
| 项目列表 `/projects/` | ✅ 显示 | — | Tab 根页面 |
| 项目详情 `/projects/<id>` | ✅ 显示 | — | 浏览路径的一部分，保留横向切换能力 |
| 检测记录表单 `records/new`・`records/edit` | ❌ 隐藏 | ✅ 取消 / 保存 | 长表单 + 数字键盘，Tab 会占掉拇指区并误触；保存必须固定在拇指可达处 |
| 模板选择 `records/new`（无 template 参数） | ❌ 隐藏 | — | 一次性选择，选完即走 |
| 报告列表 `/reports/` | ✅ 显示 | — | Tab 根页面 |
| 报告详情 `/reports/<id>` | ✅ 显示 | — | 浏览 + 删除，删除已在页面底部操作区 |
| 缺陷填报表单 `/defects/new` | ❌ 隐藏 | ✅ 取消 / 提交保存 | 同上；`#form-status` 一并放进操作条，禁用保存时提示不会被挤出屏幕 |
| 项目表单 `projects/new`・`edit` | ❌ 隐藏 | ✅ 取消 / 保存 | 同上 |
| 我的 `/me/` | ✅ 显示 | — | Tab 根页面 |
| 应用信息 `/about`（原首页的模块进度表） | ✅ 显示 | — | 从「我的 → 应用信息」进入，保留 Tab 便于返回 |

实现（零 JS、零上下文传参）：`base.html` 把 Tab 包在 `{% block tabbar %}{% include "_nav.html" %}{% endblock %}` 里，
表单模板用 `{% block tabbar %}{% endblock %}` 覆盖成空。**一个块名，一眼可查**。

### 1.4 落地页的调整（含「我的」的边界）

- **`GET /` 改为 302 → `/projects/`**。当前 `/` 是「模块进度」表 —— 那是开发期产物，
  作为现场工具的首屏不合适。
- 模块进度表搬到 **`GET /about`**，入口在「我的 → 应用信息」。答辩时点两下就能展示范围符合性，
  日常使用不会挡路。
- 品牌 logo 链接、`pages.index` 的所有引用一并改到 `/projects/`。

**「我的」页的内容边界**（需求 3.7 逐条对照）：

| 需求 3.7 | 本设计 | 说明 |
| --- | --- | --- |
| a) 用户信息卡（姓名/部门/部门编码/工号） | ✅ 做 | 取 `config.DEFAULT_REPORTER`；工号为空则不显示这一行（需求原文"有则显示"） |
| b) 数据概览（速记数、报告数） | ✅ 做，**换内容** | 速记范围外 → 改为 **项目数 / 检测记录数 / 报告数**，对当前工具更有意义 |
| c) 数据管理：清除全部速记 | ❌ 不做 | 速记范围外 |
| c) 数据管理：清除全部报告 | ⚠️ **待你确认** | 见第 9 节决策 1。只做**报告**，附带删除隐患图片文件 |
| d) 退出登录 | ❌ 不做 | 无登录（3.1 范围外） |
| e) 应用信息（名称、版本、出品部门） | ✅ 做 | 与「模块进度」表放在同一页 |

---

## 2. 检测面「摘要行 + 下级编辑」

### 2.1 为什么必须改（先算账）

现状 `records/form.html` 是一张 8 列的 `<table>`：`检测面 | 1 | 2 | 3 | 4 | 5 | 最小值 | ✕`。

iPhone SE 竖屏 320px，扣掉 `.wrap` 左右各 12px 与卡片左右各 28px，可用宽度只有 **240px**；
8 列平均每列 30px —— 小数读数（`2.14`，14px 字号）需要约 34px，**根本装不下**。
375px 的常见机型也只有约 295px（每列 37px），贴着极限；再加上输入框 1px 边框与 6px 内边距，
实际可输入区域不足 24px。**结论：这套列布局在手机上无法使用，不是"挤一点"的问题。**

### 2.2 标记：`<details>` / `<summary>` —— 本次改造的关键决策

```html
<ol class="face-list" id="face-list" data-value-count="5" data-face-max="6">
  <li>
    <details class="face-row" data-index="0" {% if row.open %}open{% endif %}>
      {# 摘要行：纯展示，不含任何表单控件 #}
      <summary class="face-summary">
        <span class="face-dot state-{{ row.state }}" aria-hidden="true"></span>
        <span class="face-name">{{ row.face or '新检测面' }}</span>
        <span class="face-count">{{ row.filled_count }}/{{ value_count }}</span>
        <span class="face-min">最小 <b class="min-value">{{ row.min_text or '—' }}</b></span>
        <span class="face-lamp" {% if not row.invalid_count %}hidden{% endif %}>
          ⚠ {{ row.invalid_count }} 格不是数字
        </span>
      </summary>

      {# 下级编辑：真正的输入区 #}
      <div class="face-editor">
        <label class="face-field">检测面
          <input type="text" class="face-input" name="face_0" list="face-suggestions"
                 maxlength="10" autocomplete="off" value="{{ row.face }}" placeholder="如 B">
        </label>

        <div class="reading-grid">
          {% for position in range(1, value_count + 1) %}
          <label class="reading-cell">
            <span class="reading-label">{{ position }}</span>
            <input type="text" class="reading" name="value_0_{{ position }}"
                   inputmode="decimal" autocomplete="off" enterkeyhint="{{ 'done' if position == value_count else 'next' }}"
                   pattern="-?(\d+(\.\d*)?|\.\d+)" value="{{ row.readings[position - 1] }}">
            <span class="input-hint">请填数字</span>
          </label>
          {% endfor %}
        </div>

        <div class="face-editor-foot">
          <span class="hint">最小值自动计算，不用手填</span>
          <button type="button" class="row-remove">删除这个检测面</button>
        </div>
      </div>
    </details>
  </li>
</ol>
```

**为什么用原生 `<details>` 而不是自定义 div + JS 开合**，这一条决定了整个改造的风险等级：

1. **自动展开不需要 JS**：服务端在需要展开的行上写 `open` 属性即可（第 2.6 节的规则全部落在服务端判定），
   没有"JS 在什么时机展开"的竞态问题；
2. **无 JS 时功能不退化**：折叠状态下浏览器仍会提交 `<details>` 内的表单控件（它们不是 `disabled`），
   而空行默认 `open`，所以**没有 JS 也能完整录入并保存**（这是现有 `record_form.js` 第 3 条约定，必须保住）；
3. **摘要行是纯展示面**：不放输入框，就不需要 `event.preventDefault()` 去抢 `<summary>` 的点击
   （这是 `<details>` 里塞控件的经典坑）；
4. 无障碍免费：键盘可 Tab 到 `<summary>`，回车/空格开合，屏幕阅读器天然理解。

**代价（明确写下来）**：`检测面名称` 输入框从"表格第一列"移到了展开区里，摘要行只显示一个派生标签。
换来的是上面 4 条收益。若你更希望名称能在摘要行内直接编辑，需要给 `<summary>` 加 `preventDefault`
逻辑，并接受"点空白处开合、点输入框编辑"的模糊边界（第 9 节决策 4）。

### 2.3 摘要行显示什么

| 元素 | 内容 | 更新时机 |
| --- | --- | --- |
| 状态圆点 | 三态颜色（2.4） | 输入时（JS）+ 首屏（服务端） |
| 检测面名称 | `row.face`，空则「新检测面」 | 输入时（JS 从 `face-input` 同步） |
| 已填进度 | `3/5` | 输入时 |
| 最小值 | `最小 2.98`（占位 `—`） | 输入时，服务端先算一份保证无 JS 可见 |
| 警告灯 | `⚠ N 格不是数字`，无事时 `hidden` | 输入时 / 服务端校验失败回填时 |

摘要行一行放得下 5 个元素吗？按 375px 估算：圆点 10px + 名称 48px + 进度 34px + 最小值 76px +
警告灯（只在出错时出现，必要时换行到第二行）。**设计上让 `.face-summary` 是 `flex-wrap: wrap`，
警告灯独占第二行**，这样正常状态永远是一行，出错状态才变两行。

### 2.4 三态着色（表达"还剩多少活"）

| 态 | 类名 | 判据 | 圆点 | 颜色 |
| --- | --- | --- | --- | --- |
| 未填 | `state-none` | 有效读数 = 0 | ○ 空心 | `--muted`（灰） |
| 部分 | `state-partial` | 1 ≤ 有效读数 < 5 | ◐ 半实心 | `#b76e00`（黄） |
| 完成 | `state-done` | 有效读数 = 5 | ● 实心 | `--ok-fg`（绿） |

**「有效读数」= 非空且能解析为数字的个数**（`parseReading` 返回 `number` 才算）。
所以"5 个格子全填了 `abc`"是 **未填 + 警告灯**，不是完成 —— 这个定义要和 2.5 一起看。

### 2.5 警告灯（表达"能不能保存"）—— 为什么必须独立

这是一个容易做错、做错了很危险的地方：**完整度和有效性是两个正交的维度**。

如果把它们揉进一个颜色（比如"有非法值就整行变红"），会出现两种情况：
- 5 个非法值 → 按"填满了"判成**绿色**，用户以为可以保存，点保存却发现按钮是灰的 —— 困惑；
- 或者把非法行涂成"部分完成"的黄色 → 用户以为只是还没填完，继续往下走 —— 更糟。

所以本设计用**两个视觉通道**：

| 通道 | 表达 | 形态 | 只在何时出现 |
| --- | --- | --- | --- |
| 三态**着色** | 完整度（还要填几格） | 摘要行左侧圆点 | 始终 |
| 警告**灯** | 有效性（能不能保存） | 摘要行右侧 `⚠ N 格不是数字` | 仅当存在非法格子 |

这样"5 个非法值"读起来是：**灰点（还没填对）+ 红灯（有 4~5 格不是数字）**，语义准确。
格子级别的红框与就地「请填数字」保持现状不变。

### 2.6 自动展开 / 收起规则

| 场景 | 行为 | 实现位置 |
| --- | --- | --- |
| 新增记录，首屏 | 唯一的那一行展开并聚焦第 1 个读数 | 服务端 `open` |
| 服务端校验失败回填 | **所有含错误的行**展开（`errors` 里出现 `face_N` / `value_N_i` 即判该行有错） | 服务端 `open` |
| 编辑记录、无错误 | **全部折叠** —— 摘要行就是"这条记录有哪些面、最小值多少"的概览（需求 3.5.2 要的"逐条展开查看"） | 服务端不写 `open` |
| 点「+ 添加检测面」 | 新行展开 + 聚焦第 1 个读数 | JS |
| 正在输入时出现非法值 | **不自动展开**，只在摘要行亮警告灯；若该行已展开则就地标红 | JS 只改 class / 文本 |
| 点「保存」但被拦截 | 展开所有非法行、聚焦第一个非法输入 | JS |
| 用户手动点摘要行 | 独立开合，**允许多行同时展开**（不做手风琴） | 原生 `<details>` |

两条"不做"的决定，理由写出来免得后人以为是漏了：

- **不做手风琴（同时只开一行）**：修错时常常要来回改两行，手风琴会强迫用户在错误之间往返点击。
- **不做"填满 5 格自动收起"**：用户刚敲完第 5 格、焦点还在输入框里，此时把内容从手指底下收走是
  典型的"聪明反被聪明误"。想收就自己点摘要行。

### 2.7 视图模型：服务端先算好，模板只输出

沿用 M4 定下的约定（`routes/reports.py::_card()`）—— **模板里不写业务逻辑**。
`routes/records.py::_row()` 在现有的 `index/face/readings/min_text` 之上补齐：

```python
def _row(index, face, readings, error_fields=()):
    filled = [v for v in readings if thickness.parse_ok(v)]      # 有效（非空且是数字）的个数
    invalid = [v for v in readings if thickness.is_invalid(v)]    # 非空但不是数字的个数
    state = "done" if len(filled) == VALUE_COUNT else ("partial" if filled else "none")
    return {
        "index": index, "face": face, "readings": readings,
        "min_text": thickness.face_min_text(readings),   # 既有：无 JS 也能看到最小值
        "filled_count": len(filled),
        "state": state,                                   # none / partial / done
        "invalid_count": max(len(invalid), row_error_count),  # 服务端校验失败时用它点亮警告灯
        "open": is_open,                                  # 见 2.6 的判定
    }
```

`invalid_count` 取"格子里的非法值个数"与"服务端错误条数"的较大值：前者管首屏（编辑已有记录时
可能残留非法文本），后者管校验失败回填（此时用户输入被原样回填，服务端已知哪几格错了）。
两条来源都是为了**同一个目的：折叠态也必须能看见错误**（第 7.3 节的风险对策）。

> 「最小值不落库」原则不变 —— `min_text` 只是渲染值，由 `services/thickness.py` 现算。

### 2.8 JS 的职责边界

`record_form.js` 现在的 4 条约定全部保留，只把**结构操作**换成 details 之后新增"派生状态刷新"：

| 保留 | 新增 | 明确不做 |
| --- | --- | --- |
| 最小值只用于即时预览，服务端重算才是准 | `updateSummary(row)`：刷新三态类、进度、最小值文本、警告灯 | 不做自动跳格（见 2.9） |
| 行下标必须落在 `0..face_max-1` | 保存被拦截时展开非法行并聚焦 | 不做高度动画（`details` 高度动画兼容性差且卡） |
| 无 JS 时照常提交 | `face-input` 输入时同步摘要行名称 | 不接管开合（交给原生） |
| 非法读数 → 标红 + 就地提示 + 禁用保存 + 拦截提交 | | |

### 2.9 键盘与输入细节

- `inputmode="decimal"`（已有）→ 手机上直接弹数字键盘；
- `enterkeyhint="next"` / `"done"`（新增）→ 键盘右下角显示「下一项」/「完成」，给用户方位感；
- `pattern="-?(\d+(\.\d*)?|\.\d+)"`（已有）→ 无 JS 时的原生校验兜底；
- **不自动跳格**：现场常见单手操作 + 回头改数，自动跳格会让"回去改一格"变成"改一次跳一次"。
  用 `enterkeyhint` 引导即可；
- **输入框字号 ≥16px**：iOS Safari 对 <16px 的输入框会在聚焦时自动放大页面，这是硬约束（写进 CSS 注释）；
- `<datalist>` 的检测面建议值（已有）保留。

---

## 3. 构件信息表单的横向表格布局

### 3.1 现状与目标

现状 `.field-row` 是 `flex` 三列（楼层 / 构件位置 / 尺寸结果）+ 下方整行的"截面尺寸要求"。
375px 下三个字段各约 94px，`楼层` 输入"二十三层"会挤；而且 `label` 在上、控件在下，
纵向空间利用率低。

**目标：label 左 / 控件右的两列网格**（移动端原生设置页的形态），一屏能看完全部构件信息。

```html
<div class="form-table">
  <div class="form-row">
    <label for="floor">楼层</label>
    <div class="form-control">
      <input type="text" id="floor" name="floor" maxlength="30" value="…" placeholder="如：六层">
      <p class="field-error">…</p>
    </div>
  </div>
  <div class="form-row">…构件位置…</div>
  <div class="form-row">…尺寸结果（mm）…</div>
  <div class="form-row form-row-block">…截面尺寸要求（整行，见 3.2）…</div>
</div>
```

```css
.form-table { border-top: 1px solid var(--line); }
.form-row {
    display: grid; grid-template-columns: 84px minmax(0, 1fr);
    gap: 4px 12px; align-items: center;
    padding: 10px 0; border-bottom: 1px solid var(--line);
}
.form-row > label { margin: 0; text-align: right; font-weight: 600; color: var(--muted); }
.form-control { min-width: 0; }            /* 允许输入框在网格里收缩 */
```

三个细节的理由：

- **label 右对齐**：中文标签只有 2~5 字，右对齐让控件列形成一条干净的竖线，
  左边参差反而更难扫读（iOS 设置页同款）；
- **`minmax(0, 1fr)` 而不是 `1fr`**：`1fr` 的最小值是 `auto`，长内容会把网格撑破 —— 这是 grid 的经典坑；
- **`.form-error` 放在 `.form-control` 里**：错误紧贴出错的控件，而不是跑到下一行去。

### 3.2 「截面尺寸要求」为什么单独占整行

它的选项是完整条文，例如：

> 立柱铝型材开口部位的厚度不应小于 5.0mm，闭口部位的厚度不应小于 3mm

放在 `84px + 1fr` 的控件列里（375px 下约 250px）只能显示约 8 个字。处理：

1. `<select>` 仍放在控件列里（保持行式布局的一致）；
2. **闭合态被浏览器截断是可接受的** —— 手机上点开 `<select>` 会弹出原生选择器，
   选项列表是全屏宽度的，条文能完整读到；
3. 额外加一行 `hint`，用 3 行 JS 在 `change` 时把当前选中的条文全文显示出来（P2 级打磨，可砍）；
4. 历史条文哨兵项（`__keep__`）的展示逻辑不变。

### 3.3 桌面怎么"复用同一布局"

这是你明确的要求，所以**不做**"桌面切回三列"的分支。桌面端只做三件事：

| 变化 | 值 |
| --- | --- |
| 内容宽度 | 主体沿用现有 `.wrap` 的 `max-width: 980px`；**表单页限制在 720px 居中**（label 到控件的距离不会拉到需要转头看的程度） |
| label 列宽 | `84px → 96px`（给"尺寸结果（mm）"这类稍长的标签留位） |
| 行内边距 | `10px → 12px` |

**一套 DOM，一处结构，两个宽度值** —— 桌面不会出现"另一个版本的表单"。

---

## 4. 断点策略

### 4.1 断点表

| 断点 | 目标设备 | 变化内容 |
| --- | --- | --- |
| **base**（<640px） | 手机竖屏 | 单列；底部固定 Tab；`.wrap` 左右 12px；卡片内边距 16px；输入框 16px 字号；命中区 ≥44px |
| **`@media (min-width: 640px)`** | 大屏手机 / 平板竖屏 | 内容 `max-width: 640px` 居中；卡片内边距 20px；表单 label 列 96px；**读取读数网格间距放大**。列表仍是单列 |
| **`@media (min-width: 960px)`** | 桌面 | **唯一的结构性变化：底部 Tab → 顶栏导航**；恢复 `.wrap` 的 980px；表单页 720px 居中；`table.grid` 恢复现有桌面观感 |
| **`@media (max-width: 359px)`** | iPhone SE / 小屏 | 读数网格从 5 列换成 **3 列 ×2 行**（`grid-template-columns: repeat(3, minmax(0,1fr))`），避免每格窄于 60px |

```css
:root { --bottom-bar-h: 56px; --safe-bottom: env(safe-area-inset-bottom, 0px); }
main  { padding-bottom: calc(var(--bottom-bar-h) + var(--safe-bottom) + 12px); }
.tabbar { position: fixed; left: 0; right: 0; bottom: 0; height: calc(var(--bottom-bar-h) + var(--safe-bottom));
          padding-bottom: var(--safe-bottom); display: flex; background: #fff;
          border-top: 1px solid var(--line); }
.tabbar .nav-item { flex: 1 1 0; display: flex; flex-direction: column; align-items: center;
                    justify-content: center; gap: 2px; min-height: 44px; text-decoration: none; }
@media (min-width: 960px) {
    .tabbar { display: none; }                 /* 底栏隐藏 */
    .topnav { display: flex; gap: 18px; }      /* 顶栏导航出现（同一个 partial） */
    main { padding-bottom: 32px; }
}
```

### 4.2 三条硬约束（写下来防止后面被"优化"掉）

1. **只有一个断点做结构性变化**（960px 的 Tab 搬家）。其余断点只允许调宽度、字号、间距、内边距 ——
   一旦有第二个结构断点，就出现了"两套布局要同时维护"，正是本次改造想避免的。
2. **不用 JS 媒体查询、不用 UA 判断**。响应式全部在 CSS 里，JS 只做状态派生（2.8）。
   好处：打印、无障碍、无 JS 场景都自然正确。
3. **视图 meta 加 `viewport-fit=cover`**，配合 `env(safe-area-inset-bottom)` 处理 iPhone 底部横条 ——
   不加的话固定底栏会被横条压住最后一行的点击区。

### 4.3 触控与字号

| 元素 | 最小尺寸 | 说明 |
| --- | --- | --- |
| Tab 项 / 主按钮 | 44×44px | Apple HIG 的最小命中区 |
| 摘要行 | 48px 高 | 折叠态的整行可点 |
| 读数输入框 | 高 44px，字号 16px | 16px 是防 iOS 聚焦缩放的红线 |
| `.row-remove` / 文本链接 | 命中区补到 44px（用 padding，不放大字号） | 现在只有 `padding: 2px 6px`，手机上很难点 |

---

## 5. 与现有 Jinja 模板的迁移路径

### 5.1 逐文件处置表

| 文件 | 处置 | 具体动作 |
| --- | --- | --- |
| `templates/base.html` | **改** | 顶栏移动端瘦身；新增 `{% block tabbar %}`；`include "_nav.html"` 两处渲染；viewport 加 `viewport-fit=cover` |
| `templates/_nav.html` | **新增** | Tab 定义（一个 partial，两处渲染） |
| `templates/index.html` | **改名/改** | 内容搬到 `templates/about.html`（模块进度），落地页改由 `/projects/` 承担 |
| `templates/me/index.html` | **新增** | 报告人卡 + 数据概览 + 数据管理 + 应用信息入口 |
| `templates/records/form.html` | **改（重写主体）** | 表格 → 摘要行 + `<details>` 编辑区；构件信息 → `.form-table`；底部固定操作条；`{% block tabbar %}` 置空 |
| `templates/records/choose_template.html` | 微调 | 卡片小屏铺满（`flex-basis: 100%`）；已接近可用 |
| `templates/projects/list.html` | **改** | `table.grid` → 卡片列表（全断点统一，见第 9 节决策 3） |
| `templates/projects/detail.html` | **改（小）** | `<details class="record">` 结构本来就对（M1 就用原生 disclosure）；把「编辑 / 删除」从 `<summary>` 移到展开区底部（现在 summary 里的链接命中区太小，且和开合点击冲突）；`table.data-table` 加小屏横滚容器 |
| `templates/projects/form.html` | 微调 | `.field` → `.form-table` 行式布局；加入底部操作条 |
| `templates/defects/form.html` | **改（结构）** | 分节（隐患信息 / 处理建议 / 归属）保留；`.field` → `.form-table`；隐患等级 radio → 三选一分段控件 `.segmented`（需求 3.3.2 要求"三选一按钮"）；底部操作条 + `#form-status` 进位；`{% block tabbar %}` 置空 |
| `templates/reports/list.html`・`_card.html` | **不动** | M4 已经是卡片 + 缩略图 + 徽标，正是为移动端设计的；只有 CSS 间距微调 |
| `templates/reports/detail.html` | 微调 | 大图已 `max-height: 60vh`；`th/td` 两列表在手机上可用；确保「删除报告」在页面底部操作区（已是） |
| `static/css/app.css` | **改（追加为主）** | 新增「移动优先」段落 + 3 个媒体查询；既有类只做 2 处调整（`.wrap` 桌面值不变、`table.grid` 小屏横滚）；**颜色变量一个都不动** |
| `static/js/record_form.js` | **改** | 结构操作从 table 换到 details；新增 `updateSummary()`；保留全部既有语义（见 2.8） |
| `static/js/app.js` | **不动** | 确认弹窗机制与 UI 改造无关 |
| `static/js/defects_form.js` | 微调 | 图片预览与分段控件的联动（若有） |
| `routes/records.py` | **改（小）** | `_row()` 扩展视图模型（2.7）；`open` 判定 |
| `routes/pages.py` | **改** | `/` 重定向到 `/projects/`；`MODULES` 表移到 `/about` |
| `routes/me.py` | **新增** | `GET /me/`；（可选）`POST /me/reports/clear` |
| `services/defects.py` | 视决策 1 | 若做「清除全部报告」：新增 `delete_all()`（复用 M4 的"先删库后删文件"顺序） |
| `services/word_report.py`／`resources/report_layout.json`／`tests/fixtures/*`／`tools/compare_report_with_sample.py` | **禁止改动** | 对拍基线与闸门本体 |
| `tests/js/record_form.test.js` | **改** | 夹具 HTML + 选择器层（见 5.3） |
| `tests/test_records.py` | **改 1 行** | 只有 `'id="face-table"'` 这一条断言需要改（见 5.2） |
| 其余 Python 测试 | **基本不动** | 新增 `tests/test_me.py`、（未改动）`test_reports.py` 等 |

### 5.2 契约冻结清单 —— 本次改造最重要的风险控制

UI 改造要动到被测试锁着的标记，处理方式是**把"标记契约"和"容器结构"分开**：
**只允许换容器（`<table>` → `<ol>`），其余 id / name / class 一律不动。**

| 类别 | 冻结内容 | 谁在依赖 |
| --- | --- | --- |
| id | `record-form`、`save-record`、`form-status`、`add-face`、`face-hint`、`face-row-template`、`face-suggestions`、`image-preview` | `tests/test_records.py`、`record_form.js`、`defects_form.js` |
| name | `face_<i>`、`value_<i>_<j>`、`floor`、`member_position`、`size_result`、`requirement_index`；**`template_type` 不出现** | `measurements.parse_record_form`、`records.py`、M1/M2 的编辑锁定测试 |
| class | `reading`、`face-input`、`min-value`、`input-hint`、`is-min`、`is-invalid`、`row-remove`、`face-row` | `record_form.js` + 35 项 JS 测试 |
| 结构约束 | 每个 `input.reading` 的**直接父元素**内必须有 `.input-hint`；每行**恰好一个** `.min-value` | `updateRow()` 与 JS 测试的 `inputHint()` 用 `input.parentNode.querySelector(...)` |
| 行为约束 | 折叠状态下输入仍能提交；无 JS 时也能完成录入 | 现有 JS 约定的第 3 条 |

只改一处：容器 `table#face-table > tbody > tr.face-row`
→ `ol#face-list > li > details.face-row`，**于是 `tests/test_records.py` 只有第 87 行一条断言需要同步**
（`'id="face-table"'` → `'id="face-list"'`）。这是刻意设计出来的结果，不是巧合。

### 5.3 JS 测试的改造范围

`tests/js/record_form.test.js` 的结构是「假 DOM 夹具 + 真实 `record_form.js`」。改造落在**夹具层**：

| 部分 | 动作 | 量 |
| --- | --- | --- |
| 夹具 HTML（第 38~84 行：`faceRow` / `templateRow` / `<template>`） | 换成 details 结构 | ~35 行 |
| `const tbody = querySelector('#face-table tbody')` | → `#face-list` | 1 行 |
| `rows()` | → `querySelectorAll('details.face-row')` | 1 行 |
| `minText` / `readingInputs` / `type` / `inputHint` / `click` / `submitForm` | **不改**（都基于冻结的 class 与父子关系） | 0 |
| **35 项既有断言** | **不改**（全部走上面这些 helper） | 0 |
| 新增断言 | 三态着色 3 项、警告灯 3 项、自动展开（服务端 `open` 由 Python 测试覆盖；JS 侧覆盖"保存被拦截时展开非法行"）2 项、摘要行名称同步 1 项、进度 `N/5` 2 项 | ~11 项 |

### 5.4 渐进增强的三个层次（承诺不退化）

| 层次 | 能力 | 依赖 |
| --- | --- | --- |
| ① 无 JS | 录入、开合、提交、原生 `pattern` 校验、服务端渲染的最小值与三态初值 | 只有 HTML + 服务端 |
| ② 有 JS | 实时最小值、高亮最小值、即时非法提示、三态/警告灯实时刷新、增删检测面、摘要行名称同步 | `record_form.js` |
| ③ 有 JS + 应用内弹窗 | 删除确认走 `<dialog>`（老浏览器降级为原生 `confirm`） | `app.js`（不改） |

**每一层都必须能独立完成"录入一条检测记录"这个核心任务** —— 这是验收里会实际检查的项。

---

## 6. 分阶段实施（每阶段结束都必须全绿）

| 阶段 | 内容 | 结束判据 |
| --- | --- | --- |
| **UI-1 骨架** | `base.html` + `_nav.html` + `app.css` 移动段落 + `/` 重定向 + `/about` | 页面能在 375px 下正常浏览、Tab 可切换、四条基线闸门仍绿 |
| **UI-2 检测记录表单**（最大块） | `records/form.html` 重写 + `records.py::_row()` + `record_form.js` + JS 测试夹具与新增断言 | `pytest` 全绿（含 test_records 的 1 行同步）+ JS 测试 46 项全绿 |
| **UI-3 其余页面** | 项目列表卡片化、项目详情 summary 重排、项目表单、缺陷表单分段控件、报告详情微调 | `pytest` 全绿；人工核对 5 个页面的 375 / 768 / 1280 三档 |
| **UI-4 我的**（含决策 1） | `routes/me.py` + `templates/me/index.html` + （可选）`delete_all()` + `tests/test_me.py` | 新增测试全绿 |
| **UI-5 回归与验收** | 全量测试 + 四条基线闸门 + 三档断点人工核对 + 真实手机（或 DevTools 设备模拟）走一遍演示路径 | 见第 8 节 |

---

## 7. 实施成本评估

### 7.1 工时分解

| 阶段 | 文件级工作 | 工时 |
| --- | --- | --- |
| UI-1 骨架 | base.html 60% 改写、`_nav.html` 新增、app.css 新增约 180 行、pages.py 调整、context_processor | **3.5h** |
| UI-2 检测记录表单 | `records/form.html` 重写（156 → 约 190 行）、`records.py::_row()` 扩展、`record_form.js`（205 → 约 280 行）、JS 测试夹具重写 + 11 项新断言 | **8.0h** |
| UI-3 其余页面 | 项目列表卡片化、项目详情、项目表单、缺陷表单（含分段控件）、报告详情微调、模板选择页 | **5.0h** |
| UI-4 我的 | `routes/me.py`、`templates/me/index.html`、`tests/test_me.py`（约 10 项）、（若做）`delete_all()` + 其测试 | **3.0h** |
| UI-5 回归验收 | Python 断言同步（预计 ≤8 处）、JS 测试跑通、四条闸门、三档人工核对、演示路径 | **3.0h** |
| | | **合计 22.5h ≈ 3 个工作日** |

其中 UI-4 的「清除全部报告」占约 1h。**核心改造（UI-1/2/3/5）≈ 19.5h ≈ 2.5 天。**

### 7.2 与"从零写一套前端"的对比（为什么这个估价是可信的）

本阶段之所以能在 3 天内完成，是因为前面三个里程碑已经把它需要的东西准备好了：

| 已有基础 | 省下的工作 |
| --- | --- |
| M4 的报告列表已经是卡片 + 缩略图 + 徽标 | 报告 Tab 几乎零改造 |
| M1 的项目详情已经用原生 `<details>` 做记录展开 | 移动端展开模式已被验证，直接沿用 |
| `record_form.js` 已把"最小值/非法校验/增删行"做成独立函数 | UI-2 是**改造**而非重写，语义层零变化 |
| 所有表单控件已用语义化 `label` + `id` + `name` | 无需重做无障碍与表单提交 |
| 35 项 JS 测试 + 281 项 Python 测试 | 改造有安全网，敢动结构 |
| Word 输出与 UI 完全解耦（服务端渲染 docx） | **UI 再怎么改都不可能影响对拍基线** |

### 7.3 风险与缓解

| # | 风险 | 概率/影响 | 缓解 |
| --- | --- | --- | --- |
| 1 | `record_form.js` 改造引入回归（现场录入是核心功能） | 中 / **高** | 契约冻结清单（5.2）+ 35 项 JS 断言语义保留 + 11 项新断言 + 手工走一遍"3 面 × 5 值"的完整录入 |
| 2 | **折叠态把错误藏起来**，用户不知道哪里错了 | 中 / **高** | 警告灯在折叠态可见；服务端把出错行默认展开；点保存被拦截时自动展开非法行并聚焦（2.6 三条合力） |
| 3 | 固定底栏遮住内容 / 被 iPhone 横条压住 | 中 / 中 | 单一 `--bottom-bar-h` 变量 + `main` padding + `viewport-fit=cover`；三档人工核对 |
| 4 | iOS 聚焦缩放（输入框字号 <16px） | 中 / 中 | 硬约束写进 CSS 注释；人工核对（CSS 无法被 pytest 覆盖，只能靠核对清单） |
| 5 | 桌面观感退化（被"移动优先"拖累） | 中 / 中 | 960px 档保留现有 `.wrap` 与 `table.grid` 观感；表单页 720px 居中避免控件拉太长 |
| 6 | 「我的 → 清除全部报告」误删 | 低 / **高**（不可恢复） | 二次确认写明条数 + "隐患图片一并删除" + 后端复用 M4 的"先删库后删文件"顺序 + flash 回显实际删除条数 |
| 7 | 改造中顺手动了业务代码 | 低 / **高** | 四条基线闸门作为最终判据；`services/word_report.py`、`report_layout.json`、`tests/fixtures/*` 列入禁止改动 |

### 7.4 时间紧时可以砍的范围（按性价比排序）

| 砍掉 | 省 | 代价 |
| --- | --- | --- |
| 「我的 → 数据管理（清除全部报告）」 | 1.0h | 需求 3.7c 只完成一半（速记那半本来就不做） |
| 截面尺寸要求的"全文 hint"（JS 3 行） | 0.5h | 闭合态看不到完整条文，靠点开选择器读 |
| 模板选择页微调 | 0.5h | 手机上卡片略挤，功能正常 |
| 缺陷表单的等级分段控件（保留 radio） | 1.0h | 手机上的"三选一按钮"观感差一些（需求原文要求按钮形式） |
| 桌面 960px 档的顶栏导航搬家 | 1.5h | 桌面仍是可用的（顶栏已有导航），只是不符合"改造为顶部导航"的要求 |

**不建议砍的**：UI-2（检测记录表单）和 UI-5（回归）。前者是日程里唯一"非做不可"的移动端改造
（现状在手机上根本填不了数），后者是保证没碰业务的安全网。

---

## 8. 验收标准

| # | 验收项 | 证据 |
| --- | --- | --- |
| 1 | 375px 下能完整录入一条"3 个检测面 × 5 个读数"的记录 | 手工走一遍（含增删行、改错值） |
| 2 | 摘要行三态着色正确：0 格灰 / 1~4 格黄 / 5 格绿 | JS 测试 3 项 |
| 3 | 非法读数亮警告灯，且**折叠态也看得见** | JS 测试 + Python 测试（服务端 `invalid_count` 初值） |
| 4 | 服务端校验失败回填时，出错行默认展开 | Python 测试断言 `open` 属性 |
| 5 | 点保存被拦截时，非法行自动展开并聚焦第一个非法输入 | JS 测试 |
| 6 | 无 JS 时仍能录入并保存（`<details>` 折叠不影响提交） | 手工：禁用 JS 走一遍 |
| 7 | 三个 Tab 在列表 / 详情页显示，在表单页隐藏且出现固定操作条 | 逐页核对表（1.3 节） |
| 8 | `active_tab` 在钻入子页面时仍高亮正确的 Tab | 逐页核对（含 `records.*` 归到「项目」） |
| 9 | 960px 档底部 Tab 换成顶栏导航，无第二个结构断点 | 核对 CSS：只有 1 处 `@media` 改结构 |
| 10 | 构件信息为 label 左 / 控件右的横向布局，桌面复用同一 DOM | 核对模板（无媒体查询分支的结构差异） |
| 11 | 输入框移动端字号 ≥16px、命中区 ≥44px | 核对清单 |
| 12 | 「我的」显示报告人、项目数/记录数/报告数、应用信息 | `tests/test_me.py` |
| 13 | （若做）清除全部报告：二次确认 + 图片一并删除 + flash 回显条数 | `tests/test_me.py` |
| 14 | **`python -m pytest -q` 全绿**（预计 ≈300 项） | 命令输出 |
| 15 | **`node tests/js/record_form.test.js` 全绿**（预计 ≈46 项） | 命令输出 |
| 16 | **四条基线闸门全绿**（对拍 / 版式提取 / 案例校验 / 前端 JS） | 逐条命令输出 —— 证明 UI 改造没碰业务 |

---

## 9. 需要你拍板的 4 个点

1. **「我的 → 数据管理 → 清除全部报告」是否纳入？**
   需求 3.7c 明文要求，但它是**不可恢复**的破坏性操作，而且当初确认范围时"统计 / 登录 / 速记"被排除、
   「我的」没被明确排除。我**建议纳入**（答辩时"数据管理"是完整度加分项），安全设计见 7.3 风险 6。
   若你倾向于"本期不做破坏性功能"，我就只做只读的报告人卡 + 数据概览 + 应用信息。

2. **落地页改造**：`GET /` 从「模块进度」改为 302 → `/projects/`，模块进度搬到 `/about`
   （入口在「我的 → 应用信息」）。代价是 `tests/test_web.py::test_home_page` 改 1 处断言。
   **推荐这么做** —— 首屏是开发状态表对"现场工具"来说不合适。

3. **项目列表用卡片还是表格？** 我建议**统一改卡片列表**（全断点一致），这样"桌面复用同一布局"
   这条要求才成立；代价是桌面端项目列表看起来更像卡片流而不是表格。
   备选：只在 <640px 变卡片、桌面保留 `table.grid` —— 但那会引入第二个结构断点，与 4.2 的约束冲突。

4. **检测面名称的编辑位置**：移到展开区里（摘要行保持纯展示，换来原生 disclosure 的零 JS 可靠性 ——
   **推荐**），还是留在摘要行内联编辑（需要给 `<summary>` 加 `preventDefault`，点击语义会变模糊）？

这 4 点定下来我就开工，按第 6 节分阶段做，每个阶段结束跑一次全量测试 + 四条基线闸门再往下走。
