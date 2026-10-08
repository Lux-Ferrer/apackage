# -*- coding: utf-8 -*-
"""冻结附页对拍的**期望产物**：用 Python 引擎把附页夹具渲染成 docx。

为什么需要它
------------
对拍基准（``tests/fixtures/检测表_真实裁剪.docx``）只含立柱/横梁两张检测表，
**没有附页**（真实报告的缺陷附页在另一册里，未纳入裁剪基准）。
所以附页的期望值必须自己造一份，并沿用与 M2 完全一样的规矩：

    同一份数据 → Python 引擎生成并**冻结** → JS 引擎重跑 → 逐属性对拍

于是本脚本做三件事：
  1. 取对拍基准的项目信息 + 两组检测记录（与 ``generated_baseline.docx`` 同源，
     这样"有附页/无附页"两个产物只差附页部分）；
  2. 把 :mod:`tools.attachment_fixture` 里的三份缺陷报告交给 **Python 的**附页链路
     （``defects.attachment_views`` → ``word_report.build_project_report``）；
  3. 落盘 ``tests/fixtures/attachment_baseline.docx``。

⚠️ 图片从 ``tests/fixtures/attachment/`` 读：``images.absolute_path()`` 只取 basename 再拼到
``uploads_dir()``，而那是运行期目录（gitignore）。所以这里**临时改写**
``config.UPLOADS_DIR`` 指向夹具目录 —— 只在本进程内生效，且必须显式说明（不改 webapp 代码，
M5 的硬约束是 Flask 侧一行不动）。

用法::

    python tools/build_attachment_baseline.py            # 生成图片 + 冻结基线
    python tools/build_attachment_baseline.py --check    # 只检查是否同步
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import attachment_fixture                                     # noqa: E402
from tools.compare_report_with_sample import extract_groups, extract_project, sample_root  # noqa: E402
from webapp import config                                                # noqa: E402
from webapp.services import defects as defect_service                    # noqa: E402
from webapp.services import images as image_service                      # noqa: E402
from webapp.services import word_report as wr                            # noqa: E402

OUTPUT = ROOT / "tests" / "fixtures" / "attachment_baseline.docx"


def build_document():
    """返回（文档, 渲染用的附页视图）。"""
    root = sample_root(config.GOLDEN_SAMPLE)
    project = extract_project(root)
    groups = extract_groups(root)

    # 图片目录指到夹具目录（只影响本进程；见模块 docstring）
    config.UPLOADS_DIR = attachment_fixture.IMAGE_DIR

    rows = attachment_fixture.defect_rows()
    workdir = ROOT / "_work" / "attachment_fixture"
    views = defect_service.attachment_views(rows, workdir)

    doc = wr.build_project_report(project, groups, attachments=views)
    return doc, views, groups


def summary(views) -> str:
    lines = []
    for index, view in enumerate(views, start=1):
        if view["image_path"]:
            state = "已压缩" if view["compressed"] else "原尺寸"
            lines.append("  附页 %d：%s → %s / %s"
                         % (index, view["original_name"], _twips(view), state))
        else:
            lines.append("  附页 %d：%s → 降级（图片缺失）"
                         % (index, view["original_name"]))
    return "\n".join(lines)


def _twips(view) -> str:
    return "嵌入 %d×%d twips" % (view["image_width_twips"], view["image_height_twips"])


def main() -> int:
    parser = argparse.ArgumentParser(description="冻结附页对拍基线")
    parser.add_argument("--check", action="store_true", help="只检查是否同步")
    args = parser.parse_args()

    written = attachment_fixture.make_images()
    if not args.check:
        print("夹具图片：%s" % "、".join(path.name for path in written))

    doc, views, groups = build_document()
    target = ROOT / "_work" / "attachment_baseline_new.docx"
    target.parent.mkdir(parents=True, exist_ok=True)
    wr.save(doc, target)

    if args.check:
        if not OUTPUT.exists():
            print("缺少 %s，请运行：python tools/build_attachment_baseline.py"
                  % OUTPUT.relative_to(ROOT))
            return 1
        # 冻结基线是 zip：字节级时间戳会变，所以比**指纹**而不是比字节
        from tools.compare_report_with_sample import document_fingerprint, diff
        diffs = diff(document_fingerprint(OUTPUT), document_fingerprint(target), "doc")
        if diffs:
            print("附页基线与当前引擎不一致（%d 处），请重新冻结："
                  "python tools/build_attachment_baseline.py" % len(diffs))
            for path, expected, actual in diffs[:8]:
                print("  %-40s 基线=%-24s 实际=%s"
                      % (path, repr(expected)[:24], repr(actual)[:32]))
            return 1
        print("附页基线与当前引擎一致 ✅（%s）" % OUTPUT.relative_to(ROOT))
        return 0

    target.replace(OUTPUT)
    print("附页基线已冻结：%s" % OUTPUT.relative_to(ROOT))
    print("  检测记录：%d 组 / %d 个检测面"
          % (len(groups), sum(len(item["faces"]) for g in groups for item in g["records"])))
    print(summary(views))
    return 0


if __name__ == "__main__":
    sys.exit(main())
