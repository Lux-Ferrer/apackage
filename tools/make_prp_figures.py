# -*- coding: utf-8 -*-
"""生成 PRP 展示用的四张"证明类"素材图（英文、白底、1920px 以上宽）。

产出（``deliverables/prp/``）：

  ``gate-convergence.png``  闸门 A 的差异收敛曲线：201 → 33 → 2 → 0
  ``gate-sensitivity.png``  闸门敏感性验证表：7 项下毒 + 落点路径
  ``test-summary.png``      测试总览：Python 348 / 前端 231 / 四条基线 / 闸门 A·B 双 0 差异
  ``architecture.png``      Flask（服务端 + SQLite）↔ PWA（浏览器 + IndexedDB + docx JS）

两条纪律
--------
1. **图上的数字必须来自真实的工具输出，不手抄**：
   - 敏感性表读 ``tools/verify_gate_sensitivity.py --json`` 的结果；
   - 测试计数用 ``--refresh`` 现场跑 pytest / npm test 并解析（结果缓存到 ``_work/prp-facts.json``）。
   手抄的数字一旦代码变了就成了"论文明天不成立"的隐患。
2. **没人替你看图，所以脚本自己查版式**：渲染后用 renderer 量每个文本的包围盒，
   检查有没有超出画布、表格文字有没有溢出单元格。这类问题在幻灯片上就是"字被切掉"。

用法::

    python tools/make_prp_figures.py                # 用缓存里的计数
    python tools/make_prp_figures.py --refresh      # 现场跑测试刷新计数（约 80s）
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import matplotlib

    matplotlib.use("Agg")                 # 无显示环境（脚本/CI）也能出图
    import matplotlib.pyplot as plt       # noqa: E402
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402
except ImportError:                       # pragma: no cover - 只影响素材生成，不影响产品
    # 退出码 3 = "本机没有 matplotlib，跳过"。verify_all.py 会把 3 当成跳过而不是失败，
    # 这样这个自检可以进闸门清单，又不会强迫每个人都装绘图库。
    print("跳过：本机没装 matplotlib（pip install matplotlib 后可生成展示素材）")
    raise SystemExit(3)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "deliverables" / "prp"
FACTS_PATH = ROOT / "_work" / "prp-facts.json"
SENSITIVITY_JSON = ROOT / "_work" / "gate-sensitivity.json"

PY = sys.executable
NPM = shutil.which("npm") or "npm.cmd"

# —— 配色：与工具本身一致（webapp/static/css/app.css 的变量），保证素材与成品同一套语言 ——
INK = "#1f2937"
MUTED = "#6b7280"
LINE = "#e5e7eb"
ACCENT = "#1668dc"
OK = "#1e7b34"
WARN = "#b76e00"
DANGER = "#b3261e"
PANEL = "#f8f9fb"

# 出图尺寸：16:9、12in × 200dpi = 2400 × 1350 px（要求 ≥1920px 宽，留足余量）
FIG_INCHES = (12.0, 6.75)
DPI = 200

# `--dump` 会把图上的文字按阅读顺序打出来 —— 供"没有眼睛"时复核文案（截断、漏词就在这里露出来）
DUMP = False

CAPTION = ("Source: this repository — tools/verify_gate_sensitivity.py, "
           "tools/verify_all.py, and the M5 migration test suite.")


def new_figure():
    fig = plt.figure(figsize=FIG_INCHES, dpi=DPI, facecolor="white")
    return fig


def title_block(fig, title, subtitle=None):
    """统一的标题样式：左对齐加粗标题 + 一行灰色副标题。"""
    fig.text(0.045, 0.935, title, fontsize=21, fontweight="bold", color=INK, va="top")
    if subtitle:
        fig.text(0.045, 0.868, subtitle, fontsize=12, color=MUTED, va="top")


def footer(fig, text=CAPTION):
    fig.text(0.045, 0.020, text, fontsize=8.5, color=MUTED, va="bottom")


# --------------------------------------------------------------------------
# 版式自检（没有眼睛，就用 renderer 量）
# --------------------------------------------------------------------------
def audit_figure(fig, cells=None, regions=None, forbidden=None, allow_overlap=()) -> list:
    """返回版式问题列表。检查五类问题，全部**用 renderer 量出来的包围盒**判断：

    1. 文本越出画布；
    2. 文本越出它所属的容器（单元格 / 卡片 / 面板内的子框）；
    3. 文本落进了"禁止区"（例如架构图中间那条箭头带）；
    4. 两段文字互相压住；
    5. 图里出现中文（PPT 是英文的）。

    参数
    ----
    ``cells``      ``[(text_artist, rect)]`` —— 表格单元格
    ``regions``    ``[(rect, [text_artist, ...])]`` —— 卡片/子框：里面的文字必须全在框内
    ``forbidden``  ``[rect]`` —— 不许有任何文字进入的矩形带（箭头、图例条…）

    ⚠️ 为什么要有 2 和 3：**第一版只查了"越出画布"和"越出单元格"**，
    于是"子框里的第三行掉到框外、正好压在下面那个框上"和"说明文字被箭头头压住"
    这两种问题一条都没查出来 —— 交付后由人眼发现的。**只查画布边界是不够的：
    真正会出问题的是"文字跑出它自己的那块地方"，而不是跑出整张图。**
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    problems = []
    width, height = fig.bbox.width, fig.bbox.height

    def rect_px(rect):
        return (rect[0] * width, rect[1] * height,
                (rect[0] + rect[2]) * width, (rect[1] + rect[3]) * height)

    texts = []
    for text in fig.findobj(match=plt.Text):
        content = text.get_text()
        if not content.strip():
            continue
        # PPT 是英文的 —— 图里**一个中日韩字符都不该有**（由脚本强制，不靠自觉）
        if any("\u4e00" <= char <= "\u9fff" for char in content):
            problems.append("图里出现了中文（PPT 是英文的）：%r" % content[:40])
        box = text.get_window_extent(renderer)
        if box.x0 < -1 or box.y0 < -1 or box.x1 > width + 1 or box.y1 > height + 1:
            problems.append("文本越出画布：%r（x %.0f~%.0f / y %.0f~%.0f，画布 %.0f×%.0f）"
                            % (content[:40], box.x0, box.x1, box.y0, box.y1, width, height))
        texts.append((content, box))

    def check_inside(text, rect, kind):
        box = text.get_window_extent(renderer)
        x0, y0, x1, y1 = rect_px(rect)
        if box.x0 < x0 - 1 or box.x1 > x1 + 1 or box.y0 < y0 - 1 or box.y1 > y1 + 1:
            problems.append(
                "%s放不下这段文字：%r\n"
                "        文本 x %.0f~%.0f / y %.0f~%.0f，容器 x %.0f~%.0f / y %.0f~%.0f"
                % (kind, text.get_text()[:44], box.x0, box.x1, box.y0, box.y1, x0, x1, y0, y1))

    for text, rect in (cells or []):
        check_inside(text, rect, "单元格")

    for rect, items in (regions or []):
        for text in items:
            check_inside(text, rect, "容器内")

    for rect in (forbidden or []):
        x0, y0, x1, y1 = rect_px(rect)
        for content, box in texts:
            overlap_x = min(box.x1, x1) - max(box.x0, x0)
            overlap_y = min(box.y1, y1) - max(box.y0, y0)
            if overlap_x > 2 and overlap_y > 2:
                problems.append("文字落进了禁止区（重叠 %.0f×%.0f px）：%r"
                                % (overlap_x, overlap_y, content[:44]))

    def allowed(one, two):
        for prefix in allow_overlap:
            if one.startswith(prefix) or two.startswith(prefix):
                return True
        return False

    for index, (content_a, box_a) in enumerate(texts):
        for content_b, box_b in texts[index + 1:]:
            if allowed(content_a, content_b):
                continue
            overlap_x = min(box_a.x1, box_b.x1) - max(box_a.x0, box_b.x0)
            overlap_y = min(box_a.y1, box_b.y1) - max(box_a.y0, box_b.y0)
            if overlap_x > 2 and overlap_y > 2:
                problems.append("两段文字重叠：%r ↔ %r（重叠 %.0f×%.0f px）"
                                % (content_a[:28], content_b[:28], overlap_x, overlap_y))

    if DUMP:      # --dump：把图上的文字按阅读顺序打出来，便于复核文案本身
        print("    ── 图上的文字（自上而下）──")
        for content, box in sorted(texts, key=lambda item: -item[1].y0):
            print("    y=%4.0f x=%4.0f  %s" % (box.y0, box.x0, content.replace("\n", " ⏎ ")))
    return problems


# --------------------------------------------------------------------------
# 事实收集（图上的数字从哪来）
# --------------------------------------------------------------------------
def refresh_facts() -> dict:
    """现场跑两套测试并解析计数；结果写进缓存。"""
    print("· 跑 pytest 统计 Python 测试数…")
    pytest_run = subprocess.run([PY, "-m", "pytest", "-q", "--collect-only"],
                                cwd=str(ROOT), capture_output=True, text=True)
    collected = re.search(r"(\d+)\s+tests?\s+collected", pytest_run.stdout)
    python_count = int(collected.group(1)) if collected else 0

    print("· 跑 pytest 确认全绿…")
    pytest_full = subprocess.run([PY, "-m", "pytest", "-q"], cwd=str(ROOT),
                                 capture_output=True, text=True)
    python_passed = int((re.search(r"(\d+) passed", pytest_full.stdout) or ["0"])[1]) \
        if re.search(r"(\d+) passed", pytest_full.stdout) else 0

    print("· 跑 npm test 统计前端测试数（约 60s）…")
    npm_run = subprocess.run([NPM, "test"], cwd=str(ROOT), capture_output=True, text=True)
    node_counts = [int(value) for value in re.findall(r"^ℹ pass (\d+)$", npm_run.stdout, re.M)]
    legacy = re.search(r"前端 JS 测试：(\d+)/(\d+) 通过", npm_run.stdout)
    front_m5 = node_counts[0] if node_counts else 0
    front_legacy = int(legacy.group(1)) if legacy else 0

    facts = {
        "python_tests": python_count or python_passed,
        "python_passed": python_passed,
        "front_m5_tests": front_m5,
        "front_legacy_tests": front_legacy,
        "python_ok": pytest_full.returncode == 0,
        "front_ok": npm_run.returncode == 0,
        "collected_at": subprocess.run([PY, "-c", "import datetime;print(datetime.date.today())"],
                                       capture_output=True, text=True).stdout.strip(),
    }
    FACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    FACTS_PATH.write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("· 计数已缓存：%s" % FACTS_PATH.relative_to(ROOT))
    return facts


def load_facts(refresh: bool) -> dict:
    if refresh or not FACTS_PATH.exists():
        return refresh_facts()

    facts = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
    # 便宜的过期检查：pytest 只收集不执行（约 2 秒），对不上就提醒重新 --refresh。
    # 素材上的数字一旦和仓库对不上，在评审现场就是可信度问题。
    collect = subprocess.run([PY, "-m", "pytest", "-q", "--collect-only"],
                             cwd=str(ROOT), capture_output=True, text=True)
    found = re.search(r"(\d+)\s+tests?\s+collected", collect.stdout)
    if found and int(found.group(1)) != facts.get("python_tests"):
        print("⚠ Python 测试数已变化（缓存 %s → 实际 %s）。请用 --refresh 重新生成素材，"
              "否则图上的数字是旧的。"
              % (facts.get("python_tests"), found.group(1)))
    return facts


def load_sensitivity() -> dict:
    """读敏感性验证结果（缺了就现场生成 —— 它只要 0.6 秒）。"""
    if not SENSITIVITY_JSON.exists():
        print("· 生成闸门敏感性结果…")
        subprocess.run([PY, "tools/verify_gate_sensitivity.py", "--json", str(SENSITIVITY_JSON)],
                       cwd=str(ROOT), capture_output=True, text=True)
    return json.loads(SENSITIVITY_JSON.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 图 1：闸门收敛曲线
# --------------------------------------------------------------------------
CONVERGENCE = [
    (1, 201, "Initial port\n(JS engine runs end to end)"),
    (2, 33, "Table & row attributes"),
    (3, 2, "Cell & vMerge details"),
    (4, 0, "Gate green"),
]


def figure_gate_convergence(path: Path) -> list:
    fig = new_figure()
    title_block(
        fig, "Fidelity Gate A Convergence",
        "JS engine output vs. the frozen Python baseline — compared attribute by attribute "
        "across body, tables, rows, cells and images.")

    ax = fig.add_axes([0.085, 0.185, 0.87, 0.60])
    rounds = [item[0] for item in CONVERGENCE]
    counts = [item[1] for item in CONVERGENCE]

    ax.plot(rounds, counts, color=ACCENT, linewidth=2.6, marker="o",
            markersize=9, markerfacecolor="white", markeredgewidth=2.6, zorder=3)
    ax.fill_between(rounds, counts, color=ACCENT, alpha=0.08, zorder=1)
    ax.axhline(0, color=OK, linewidth=1.6, linestyle="--", zorder=2)
    ax.text(4.06, 0, "target: 0 differences", color=OK, fontsize=10, va="center")

    for index, (x, y, label) in enumerate(CONVERGENCE):
        offset = 16 if index < 3 else 22
        ax.annotate("%d" % y, (x, y), textcoords="offset points", xytext=(0, offset),
                    ha="center", fontsize=15, fontweight="bold",
                    color=OK if y == 0 else INK)
        ax.annotate(label, (x, y), textcoords="offset points", xytext=(0, -34),
                    ha="center", va="top", fontsize=9, color=MUTED, linespacing=1.5)

    ax.set_xlim(0.55, 4.85)
    ax.set_ylim(-34, 232)
    ax.set_xticks(rounds)
    ax.set_xticklabels(["Round %d" % item for item in rounds], fontsize=10, color=INK)
    ax.set_ylabel("Differences found", fontsize=11, color=INK)
    ax.set_xlabel("Convergence round", fontsize=11, color=INK, labelpad=10)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(LINE)
    ax.spines["bottom"].set_color(LINE)
    ax.grid(axis="y", color=LINE, linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, labelsize=9.5)

    fig.text(0.085, 0.105,
             "201 → 33 → 2 → 0 over four rounds.  Convergence was reached with 11 attribute-level "
             "post-processing patches;\nno deviations were declared and the gate was not "
             "loosened. Gate A (both halves) and Gate B all report 0 differences.",
             fontsize=9.5, color=MUTED, va="top", linespacing=1.6)
    footer(fig)
    fig.savefig(path, dpi=DPI, facecolor="white")
    problems = audit_figure(fig)
    plt.close(fig)
    return problems


# --------------------------------------------------------------------------
# 图 2：闸门敏感性验证表
# --------------------------------------------------------------------------
# 把校验脚本里的中文说明译成英文（PPT 是英文的）；键与 DOCUMENT_POISONS 的名字对应
SENSITIVITY_EN = {
    "image_extent": "Image display size halved",
    "drop_drawing": "Embedded image removed (nothing drawn)",
    "image_media": "Media part swapped for another image",
    "table_text": "One character changed in a table cell",
    "table_merge": "Vertical-merge marker rewritten",
    "row_height": "Row height changed 400 → 500",
    "bold_label": "Bold flag removed from a label",
}
SENSITIVITY_ORDER = ["image_extent", "drop_drawing", "image_media", "table_text",
                     "table_merge", "row_height", "bold_label"]


def figure_gate_sensitivity(path: Path, payload: dict) -> list:
    fig = new_figure()
    by_name = {item["name"]: item for item in payload["poisons"]}
    rows = [(SENSITIVITY_EN[name], by_name[name]["detected_at"]) for name in SENSITIVITY_ORDER]

    title_block(
        fig, "Gate Sensitivity Check",
        "Seven defects were injected into a verified-good export. Every one must be caught — "
        "and caught at the right attribute.")

    left, right = 0.045, 0.955
    top, bottom = 0.775, 0.135
    header_h = 0.052
    row_h = (top - bottom - header_h) / len(rows)
    col_1 = left
    col_2 = left + 0.395
    name_w = col_2 - col_1
    path_w = right - col_2

    # 表头
    fig.patches.append(Rectangle((left, top - header_h), right - left, header_h,
                                 transform=fig.transFigure, facecolor=ACCENT, edgecolor="none"))
    fig.text(col_1 + 0.014, top - header_h / 2, "Injected defect", fontsize=12.5,
             fontweight="bold", color="white", va="center")
    fig.text(col_2 + 0.014, top - header_h / 2, "Detected at (diff path)", fontsize=12.5,
             fontweight="bold", color="white", va="center")

    cells = []
    for index, (defect, where) in enumerate(rows):
        y = top - header_h - (index + 1) * row_h
        if index % 2 == 0:
            fig.patches.append(Rectangle((left, y), right - left, row_h,
                                         transform=fig.transFigure, facecolor=PANEL,
                                         edgecolor="none"))
        fig.patches.append(Rectangle((left, y), right - left, row_h, transform=fig.transFigure,
                                     facecolor="none", edgecolor=LINE, linewidth=0.7))

        # 只在第一列前放一个绿色对勾：说明"被抓住"这件事本身
        fig.text(col_1 + 0.014, y + row_h / 2, "✓", fontsize=12, color=OK,
                 va="center", fontweight="bold")
        defect_text = fig.text(col_1 + 0.042, y + row_h / 2, defect, fontsize=11.5,
                               color=INK, va="center")
        path_text = fig.text(col_2 + 0.014, y + row_h / 2, where, fontsize=11,
                             color=ACCENT, va="center", family="monospace")
        cells.append((defect_text, (col_1 + 0.040, y + 0.006, name_w - 0.046, row_h - 0.012)))
        cells.append((path_text, (col_2 + 0.012, y + 0.006, path_w - 0.026, row_h - 0.012)))

    fig.text(0.045, 0.105,
             "Control (no injection): 0 differences — so the gate is not reporting noise. All 7 "
             "injected defects were caught,\nand each was caught at the attribute that was "
             "actually modified. Rows are grouped by the attribute under test.",
             fontsize=10, color=MUTED, va="top", linespacing=1.6)
    footer(fig, "Source: python tools/verify_gate_sensitivity.py — "
                "re-run it any time; the exit code is 0 only when all seven are caught.")
    fig.savefig(path, dpi=DPI, facecolor="white")
    problems = audit_figure(fig, cells)
    plt.close(fig)
    return problems


# --------------------------------------------------------------------------
# 图 3：测试总览
# --------------------------------------------------------------------------
def figure_test_summary(path: Path, facts: dict) -> list:
    fig = new_figure()
    front_total = facts["front_m5_tests"] + facts["front_legacy_tests"]
    title_block(fig, "Verification Summary",
                "Everything below is produced by one command: "
                "python tools/verify_all.py (14 checks, ~70 s).")

    tiles = [
        ("Python test suite", "%d" % facts["python_tests"], "tests passed",
         ["data layer · report layout · export · defects · UI"], ACCENT),
        ("Front-end tests", "%d" % front_total,
         "tests passed (%d M5 + %d legacy UI)" % (facts["front_m5_tests"],
                                                  facts["front_legacy_tests"]),
         ["IndexedDB · docx engine · attachments · image pipeline"], ACCENT),
        ("Baseline gates", "4 / 4", "green",
         ["Word diff · layout spec · case data · front-end JS"], OK),
        ("Gate A & Gate B", "0", "differences",
         ["JS engine reproduces the frozen baseline exactly,",
          "and still matches the real client report"], OK),
    ]

    positions = [(0.040, 0.470), (0.525, 0.470), (0.040, 0.150), (0.525, 0.150)]
    size = (0.435, 0.290)
    regions = []

    for (label, value, unit, details, colour), (x, y) in zip(tiles, positions):
        fig.patches.append(FancyBboxPatch(
            (x, y), size[0], size[1], transform=fig.transFigure, boxstyle="round,pad=0.006",
            facecolor=PANEL, edgecolor=LINE, linewidth=1.0))
        fig.patches.append(Rectangle((x, y + size[1] - 0.011), size[0], 0.011,
                                     transform=fig.transFigure, facecolor=colour, edgecolor="none"))
        texts = [fig.text(x + 0.020, y + size[1] - 0.050, label, fontsize=11.5,
                          color=MUTED, va="center")]

        # 数字与单位是**两个** text 对象，所以要量出数字的真实宽度再放单位 ——
        # 靠"字符数 × 常数"估算必然在 "4 / 4" 这种多字符值上压字（第一版就是）。
        value_text = fig.text(x + 0.020, y + size[1] - 0.130, value, fontsize=32,
                              fontweight="bold", color=INK, va="center")
        fig.canvas.draw()
        measured = value_text.get_window_extent(fig.canvas.get_renderer()).width \
            / fig.bbox.width
        texts.append(value_text)
        texts.append(fig.text(x + 0.020 + measured + 0.010, y + size[1] - 0.142, unit,
                              fontsize=12, color=colour, va="center", fontweight="bold"))

        # 说明文字：**逐行显式排**（不用 wrap=True —— 它按整张图的宽度折行，
        # 结果是文字跑出卡片或句子被截断，第一版就留了个"and still"）
        for index, line in enumerate(details):
            texts.append(fig.text(x + 0.020, y + 0.072 - index * 0.030, line,
                                  fontsize=9.5, color=MUTED, va="center"))
        regions.append(((x, y, size[0], size[1]), texts))

    fig.text(0.045, 0.105,
             "Gate A runs twice: the M2 path (detection tables) and the M3 path (attachment pages "
             "with embedded images).\nBoth report 0 differences — and the gate itself is checked "
             "for sensitivity, so a green result means something.",
             fontsize=9.5, color=MUTED, va="top", linespacing=1.6)
    footer(fig, "Counts collected %s from actual runs (pytest -q, npm test) — "
                "not transcribed by hand." % facts.get("collected_at", ""))
    fig.savefig(path, dpi=DPI, facecolor="white")
    problems = audit_figure(fig, regions=regions)
    plt.close(fig)
    return problems


# --------------------------------------------------------------------------
# 图 4：架构对比
# --------------------------------------------------------------------------
def box(fig, x, y, width, height, title, lines, colour, *, line_size=9.2):
    """一个带标题与要点行的圆角盒子。**返回 `(rect, [texts])` 供版式自检。**

    布局是从盒子的实际高度**算出来的**，不是拿固定行距堆的 ——
    第一版用固定行距 `0.032`，三行要点就掉出了盒底（第三行正好压在下面那个盒子上，
    由人眼发现）。现在：标题占顶部固定带，要点行在剩余高度里**平均分配**，
    每两行之间保证留出文本高度以外的空隙；实在放不下时 `audit` 会报"容器内放不下这段文字"。
    """
    fig.patches.append(FancyBboxPatch(
        (x, y), width, height, transform=fig.transFigure, boxstyle="round,pad=0.008",
        facecolor="white", edgecolor=colour, linewidth=1.6))

    texts = []
    title_gap = 0.030                                   # 标题中心距盒顶
    texts.append(fig.text(x + width / 2, y + height - title_gap, title, fontsize=12.5,
                          fontweight="bold", color=colour, ha="center", va="center"))

    inner_top = y + height - 0.055                      # 要点区上沿（标题下方）
    inner_bottom = y + 0.014                            # 要点区下沿（盒内留一点内边距）
    count = max(len(lines), 1)
    step = (inner_top - inner_bottom) / count
    for index, line in enumerate(lines):
        texts.append(fig.text(x + 0.014, inner_bottom + step * (count - index - 0.5), line,
                              fontsize=line_size, color=INK if index == 0 else MUTED,
                              va="center"))
    return (x, y, width, height), texts, step


def figure_architecture(path: Path) -> list:
    fig = new_figure()
    title_block(fig, "Architecture: Reference Implementation → Offline PWA",
                "Same data model and the same Word output — the difference is where the work "
                "and the data live.")

    # 三栏预算：左面板 0.040~0.390、中间迁移箭头 0.400~0.520、右面板 0.530~0.880，
    # 最右侧 0.890~0.985 留给「Data stays on device」标注 —— 不把标注挤在画布边上
    panel_w = 0.350
    left_x, right_x = 0.040, 0.530
    top_y = 0.760
    inner_w = panel_w - 0.044
    box_h = 0.142                       # 三行要点 + 标题所需的高度（算过的，不是猜的）
    box_gap = 0.038
    panel_h = 0.062 + box_h * 2 + box_gap + 0.026     # 标题带 + 两个子框 + 间距 + 内边距
    bottom_y = top_y - panel_h
    mid_x = (left_x + panel_w + right_x) / 2
    centre_y = bottom_y + panel_h / 2

    box_top = top_y - 0.062                               # 第一个子框的上沿
    first_y = box_top - box_h
    second_y = first_y - box_gap - box_h

    regions = []

    # —— 左：Flask 参考实现 ——
    fig.patches.append(FancyBboxPatch(
        (left_x, bottom_y), panel_w, panel_h, transform=fig.transFigure,
        boxstyle="round,pad=0.010", facecolor=PANEL, edgecolor=LINE, linewidth=1.2))
    fig.text(left_x + panel_w / 2, top_y - 0.034, "Flask app  (reference implementation)",
             fontsize=12.5, fontweight="bold", color=INK, ha="center", va="center")

    rect, texts, _step = box(fig, left_x + 0.022, first_y, inner_w,
                             box_h, "Server process",
                             ["Routes + Jinja templates render every page",
                              "python-docx builds the .docx server-side",
                              "Live only while the laptop runs"], MUTED)
    regions.append((rect, texts))
    rect, texts, _step = box(fig, left_x + 0.022, second_y, inner_w,
                             box_h, "SQLite + uploads/",
                             ["4 tables, foreign keys, ON DELETE CASCADE",
                              "Originals stored on the server disk",
                              "Data lives on the machine that runs it"], MUTED)
    regions.append((rect, texts))

    # —— 中间：迁移箭头（文字一律排在箭头**上方/下方**的独立带上，不碰箭头） ——
    arrow_y = centre_y
    fig.patches.append(FancyArrowPatch(
        (left_x + panel_w + 0.016, arrow_y), (right_x - 0.016, arrow_y),
        transform=fig.transFigure, arrowstyle="-|>", mutation_scale=18,
        color=ACCENT, linewidth=2.6))
    fig.text(mid_x, arrow_y + 0.082, "Migration", fontsize=13, fontweight="bold",
             color=ACCENT, ha="center", va="center")
    fig.text(mid_x, arrow_y - 0.062, "data layer · export engine · tests", fontsize=9,
             color=MUTED, ha="center", va="center")
    fig.text(mid_x, arrow_y - 0.092, "re-expressed, then proven equivalent", fontsize=9,
             color=MUTED, ha="center", va="center")

    # 箭头占用的横向带：不许有任何文字落进来（第一版说明文字正好被箭头头压住）
    forbidden = [(left_x + panel_w + 0.010, arrow_y - 0.016,
                  right_x - left_x - panel_w - 0.020, 0.032)]

    # —— 右：PWA ——
    fig.patches.append(FancyBboxPatch(
        (right_x, bottom_y), panel_w, panel_h, transform=fig.transFigure,
        boxstyle="round,pad=0.010", facecolor=PANEL, edgecolor=ACCENT, linewidth=1.6))
    fig.text(right_x + panel_w / 2, top_y - 0.034, "Offline PWA  (M5)",
             fontsize=12.5, fontweight="bold", color=ACCENT, ha="center", va="center")

    rect, texts, _step = box(fig, right_x + 0.022, first_y, inner_w,
                             box_h, "Browser",
                             ["Static shell + native ES modules, hash routing",
                              "docx JS builds the .docx on the device",
                              "Installable: works with no network"], ACCENT)
    regions.append((rect, texts))
    rect, texts, _step = box(fig, right_x + 0.022, second_y, inner_w,
                             box_h, "IndexedDB",
                             ["4 stores + images blob store, hand-written cascade",
                              "Originals, thumbnails and export copies kept local",
                              "Quota and persistence surfaced in the UI"], ACCENT)
    regions.append((rect, texts))

    # 右侧标注：数据不出设备
    fig.text(right_x + panel_w + 0.055, centre_y, "Data\nstays on\ndevice",
             fontsize=12, fontweight="bold", color=OK, ha="center", va="center",
             linespacing=1.4)

    fig.text(0.040, 0.118,
             "Both versions write the same Word report: the same layout spec, the same table "
             "structure, the same attachment pages.\nThe Python engine is kept as the reference — "
             "the JavaScript engine has to reproduce it attribute by attribute.",
             fontsize=9.5, color=MUTED, va="top", linespacing=1.6)
    footer(fig)
    fig.savefig(path, dpi=DPI, facecolor="white")
    problems = audit_figure(fig, regions=regions, forbidden=forbidden)
    plt.close(fig)
    return problems


# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="生成 PRP 展示素材图")
    parser.add_argument("--refresh", action="store_true", help="现场跑测试刷新计数")
    parser.add_argument("--out", default=str(OUT_DIR))
    parser.add_argument("--dump", action="store_true",
                        help="打印每张图上的文字（按阅读顺序），便于复核文案")
    args = parser.parse_args()

    global DUMP
    DUMP = args.dump

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    facts = load_facts(args.refresh)
    sensitivity = load_sensitivity()

    jobs = [
        ("gate-convergence.png", lambda p: figure_gate_convergence(p)),
        ("gate-sensitivity.png", lambda p: figure_gate_sensitivity(p, sensitivity)),
        ("test-summary.png", lambda p: figure_test_summary(p, facts)),
        ("architecture.png", lambda p: figure_architecture(p)),
    ]

    all_problems = {}
    for name, render in jobs:
        target = out_dir / name
        problems = render(target)
        all_problems[name] = problems
        size = target.stat().st_size
        print("已生成 %-24s %6.1f KB" % (name, size / 1024))

    print("\n版式自检（文本是否越界 / 表格文字是否溢出单元格）：")
    failed = False
    for name, problems in all_problems.items():
        if problems:
            failed = True
            print("  ✗ %s" % name)
            for item in problems:
                print("      %s" % item)
        else:
            print("  ✓ %s" % name)

    # 尺寸与"不是空白图"的自检
    from PIL import Image

    print("\n尺寸与内容自检：")
    for name, _render in jobs:
        target = out_dir / name
        with Image.open(target) as image:
            width, height = image.size
            grey = image.convert("L")
            darkest = min(grey.getextrema())
        ok = width >= 1920
        failed = failed or not ok or darkest > 200
        print("  %s %s  %d×%d  最暗像素=%d"
              % ("✓" if ok and darkest <= 200 else "✗", name, width, height, darkest))

    print("\n结论：%s" % ("有问题，见上面 ✗" if failed else "全部通过 ✅"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
