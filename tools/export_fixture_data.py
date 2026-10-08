# -*- coding: utf-8 -*-
"""把对拍基准（真实报告裁剪版）里的**数据**导出成语言中立的 JSON，供 M5 的 JS 引擎使用。

为什么需要它
------------
对拍闸门的做法是"回灌基准自己的数据 → 用我们的引擎重新生成 → 逐属性比较"。
Python 侧靠 ``compare_report_with_sample.py`` 的 ``extract_project`` / ``extract_groups``
从 docx 里认出"哪些表是检测表、哪些行是数据行"。**这套读取逻辑不移植到 JS** ——
它是测试设施，不是产品能力。所以由本脚本把数据导出成 JSON，JS 只实现"数据 → docx"这一半，
正好是要移植的那一半。

产出：``web/assets/fixture_data.json``

用法::

    python tools/export_fixture_data.py
    python tools/export_fixture_data.py --check     # 只检查是否同步
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import attachment_fixture                                   # noqa: E402
from tools.compare_report_with_sample import (extract_groups,        # noqa: E402
                                              extract_project, sample_root)
from webapp import config                                            # noqa: E402

SOURCE = config.GOLDEN_SAMPLE
OUTPUT = ROOT / "web" / "assets" / "fixture_data.json"


def build_attachments() -> list | None:
    """附页夹具：三份缺陷报告 + 图片路径。

    与项目/检测记录不同，附页的数据**不在对拍基准里**（基准只含立柱/横梁两张表），
    所以期望产物由 ``tools/build_attachment_baseline.py`` 用 Python 引擎单独冻结。
    这里只导出"数据"这一半，JS 侧照同一份数据重跑。

    ``oriented_source``：带 EXIF 方向的那张图另有一份"已摆正副本"，
    **只给 Node 端的闸门替身用**（Node 里没有 canvas，没法真的旋转像素）。
    浏览器管线不需要它 —— 理由见 ``tools/attachment_fixture.py`` 的说明。
    """
    if not attachment_fixture.defect_rows():
        return None
    sources = attachment_fixture.relative_sources()
    oriented = attachment_fixture.relative_oriented_sources()
    return [
        {
            "defect": row,
            "source": sources.get(row["image_path"]),
            "oriented_source": oriented.get(row["image_path"]),
        }
        for row in attachment_fixture.defect_rows()
    ]


def build_payload() -> dict:
    root = sample_root(SOURCE)
    project = extract_project(root)
    groups = extract_groups(root)
    return {
        "_source": SOURCE.name,
        "_note": "由 tools/export_fixture_data.py 从对拍基准导出；JS 引擎只消费这份数据，"
                 "不实现「从文档里认表」的逻辑（那是测试设施）。",
        "project": project,
        "attachments": build_attachments(),
        "groups": groups,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="把基准 fixture 的数据导出为 JSON")
    parser.add_argument("--check", action="store_true", help="只检查是否同步")
    args = parser.parse_args()

    text = json.dumps(build_payload(), ensure_ascii=False, indent=2) + "\n"

    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != text:
            print("web/assets/fixture_data.json 与基准不同步，请运行："
                  "python tools/export_fixture_data.py")
            return 1
        print("web/assets/fixture_data.json 与基准一致 ✅")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8")
    payload = json.loads(text)
    print("已生成 %s" % OUTPUT.relative_to(ROOT))
    print("  项目字段：%s" % ", ".join(payload["project"].keys()))
    for group in payload["groups"]:
        print("  %s：%d 条记录 / %d 个检测面"
              % (group["template_type"], len(group["records"]),
                 sum(len(item["faces"]) for item in group["records"])))
    attachments = payload.get("attachments") or []
    states = [
        ("有图" if (item["source"] and (ROOT / item["source"]).exists()) else "缺图（走降级）")
        for item in attachments
    ]
    print("  附页：%d 份（%s）" % (len(attachments), "、".join(states) or "无"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
