# -*- coding: utf-8 -*-
"""从样例报告重生「报告底座」模板。

底座的构成
----------
取样例的 ``styles.xml``（docDefaults：西文 Times New Roman + ``eastAsiaTheme``）、
``theme1.xml``（中文主题字体 = 等线）与 ``sectPr``（A4 / 页边距 1440 / docGrid），
然后清空正文。

来源样例是 ``config.FONT_SAMPLE``（金骐智谷那份），**不是**版式对拍基准
``config.GOLDEN_SAMPLE``（真实报告裁剪版）—— 后者的 docDefaults 是 SimSun/10.5pt，
采纳它等于顺手改字体，而字体不在本次范围内。

为什么需要它
------------
python-docx 自带模板的主题把中文字体映射成**宋体**，与样例的**等线**不一致。
如果新建文档后再"设置字体"，中文就会落到宋体上；从样例派生则天然沿用样例字体，
不需要在代码里硬写任何中文字体名。

用法（项目根目录）
------------------
    python tools/make_report_template.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document                              # noqa: E402

from webapp import config                              # noqa: E402
from webapp.services.word_report import clear_body      # noqa: E402


def build(src=None, dst=None) -> Path:
    # 注意：底座取自 **FONT_SAMPLE** 而不是 GOLDEN_SAMPLE。
    # 对拍基准（检测表_真实裁剪.docx）的 docDefaults 是 SimSun/10.5pt，
    # 采纳它等于顺手改掉字体 —— 本次范围不含字体，所以仍从原样例派生主题。
    src = Path(src) if src else config.FONT_SAMPLE
    dst = Path(dst) if dst else config.REPORT_BASE_TEMPLATE
    if not src.exists():
        raise SystemExit("找不到样例报告：%s" % src)

    doc = Document(str(src))
    clear_body(doc)
    dst.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(dst))
    return dst


if __name__ == "__main__":
    path = build()
    print("报告底座已生成：%s" % path)
