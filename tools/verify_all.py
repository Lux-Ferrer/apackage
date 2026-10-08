# -*- coding: utf-8 -*-
"""一条命令跑完全部闸门 —— 免得"改了代码忘了重跑某个闸门"。

为什么值得单独写一个脚本
------------------------
到 M5-3 为止，一整套验证已经膨胀到 **10 条**（4 条 Flask 基线 + 2 半闸门 A + 闸门 B +
闸门敏感性 + 2 个生成物同步检查 + Python/JS 两套单测）。
人会漏跑，而这一整套的全部意义就是"不许漏"。

本脚本只做编排：逐条执行、实时打印、最后给一张汇总表。
任何一条失败 → 退出码 1，并列出失败项。**不修改任何文件**（生成物检查用 `--check` 模式）。

用法::

    python tools/verify_all.py              # 跑全部
    python tools/verify_all.py --list       # 只列出会跑什么
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
NPM = shutil.which("npm") or "npm.cmd"
NODE = shutil.which("node") or "node"


def steps() -> list:
    """(名称, 命令, 说明)。顺序按"从便宜到贵"排，早失败早停。"""
    return [
        ("生成物同步",
         [PY, "tools/export_web_assets.py", "--check"],
         "web/ 下的生成物是否仍与 Python 真相源一致"),
        ("基准数据同步",
         [PY, "tools/export_fixture_data.py", "--check"],
         "fixture_data.json 是否仍与对拍基准一致"),
        ("Python 测试",
         [PY, "-m", "pytest", "-q"],
         "348 项：数据层 / 版式 / 导出 / 缺陷 / UI / 工具"),
        ("前端 JS 测试",
         [NPM, "test"],
         "数据层 + 引擎 + 附页 + 图片管线 + 既有 UI 测试"),
        ("Flask 基线：回灌对拍",
         [PY, "tools/compare_report_with_sample.py"],
         "Python 引擎产物 vs 真实客户报告裁剪版"),
        ("Flask 基线：版式提取",
         [PY, "tools/extract_layout_spec.py", "_work/A06YG_full.docx"],
         "版式规格与基准逐项一致（需要 _work/A06YG_full.docx）"),
        ("Flask 基线：案例校验",
         [PY, "tools/verify_case_data.py"],
         "案例解析出的期望行与报告逐格一致"),
        ("补丁验证",
         [PY, "tools/verify_docx_patches.py"],
         "docx 库输出补齐后与基线逐属性一致（升库后必跑）"),
        ("附页基线",
         [PY, "tools/build_attachment_baseline.py", "--check"],
         "附页基线是否仍与当前 Python 引擎一致"),
        ("闸门 A：复刻基线",
         [PY, "tools/compare_report_with_sample.py",
          "--expected", "tests/fixtures/generated_baseline.docx",
          "--actual", "_work/js_generated.docx"],
         "JS 产物 vs Python 冻结基线（无附页）"),
        ("闸门 A：附页",
         [PY, "tools/compare_report_with_sample.py",
          "--expected", "tests/fixtures/attachment_baseline.docx",
          "--actual", "_work/js_generated_attachments.docx"],
         "JS 产物 vs Python 冻结基线（含附页）"),
        ("闸门 B：对齐真实报告",
         [PY, "tools/compare_report_with_sample.py",
          "--expected", "tests/fixtures/检测表_真实裁剪.docx",
          "--actual", "_work/js_generated.docx"],
         "JS 产物 vs 真实客户报告裁剪版"),
        ("闸门敏感性",
         [PY, "tools/verify_gate_sensitivity.py"],
         "阴性对照 + 7 项下毒，证明闸门不是摆设"),
    ]


def need_js_products() -> list:
    """闸门 A/B 需要先有 JS 产物；缺了就先生成。"""
    return [
        ("生成 JS 产物",
         [NODE, "tools/js/generate_from_fixture.mjs"],
         "产出 _work/js_generated.docx 与 _work/js_generated_attachments.docx"),
    ]


def run(name: str, command: list, note: str, index: int, total: int) -> tuple:
    print("\n" + "=" * 78)
    print("[%d/%d] %s" % (index, total, name))
    print("      %s" % note)
    print("      $ %s" % " ".join(str(part) for part in command))
    print("-" * 78)
    started = time.time()
    result = subprocess.run(command, cwd=str(ROOT))          # 输出直接透传，便于看细节
    elapsed = time.time() - started
    ok = result.returncode == 0
    print("%s（%.1fs）" % ("✅ 通过" if ok else "❌ 失败（退出码 %d）" % result.returncode, elapsed))
    return name, ok, elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description="跑完全部验证闸门")
    parser.add_argument("--list", action="store_true", help="只列出会跑什么")
    parser.add_argument("--skip", action="append", default=[],
                        help="跳过名称包含该子串的步骤（可重复）")
    args = parser.parse_args()

    plan = need_js_products() + steps()
    plan = [item for item in plan if not any(word in item[0] for word in args.skip)]

    if args.list:
        for index, (name, command, note) in enumerate(plan, 1):
            print("%2d. %-22s %s" % (index, name, note))
            print("    $ %s" % " ".join(str(part) for part in command))
        return 0

    results = []
    total = len(plan)
    for index, (name, command, note) in enumerate(plan, 1):
        results.append(run(name, command, note, index, total))

    failed = [item for item in results if not item[1]]
    print("\n" + "=" * 78)
    print("汇总（共 %d 条，耗时 %.1fs）" % (len(results), sum(item[2] for item in results)))
    print("=" * 78)
    for name, ok, elapsed in results:
        print("  %s  %-24s %6.1fs" % ("✅" if ok else "❌", name, elapsed))

    if failed:
        print("\n失败 %d 条：%s" % (len(failed), "、".join(item[0] for item in failed)))
        return 1
    print("\n全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
