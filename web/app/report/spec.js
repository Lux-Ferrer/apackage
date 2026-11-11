/* 本文件为构建产物，请勿手改（改了下次构建会被覆盖）。
 * 内容：Word 版式规格（字号 pt / 几何 twips）
 *
 * 要换默认报告人/部门：改 app/product.js 里的 DEFAULT_PROFILE，
 * 或者直接用界面「我的 → 个人信息配置」填一次（保存在本机，优先级更高）。
 */

export const SPEC = Object.freeze({
  "_source": "版式数值实测自真实报告 docs/samples/A06YG-2026-001…doc 第 12-13 页（表2-4 立柱 / 表2-5 横梁），经 tools/build_fixture.py 裁剪为对拍基准 tests/fixtures/检测表_真实裁剪.docx。由 tests/test_word_report.py::test_layout_spec_matches_fixture 上锁。",
  "_note": "语言中立：Python 导出引擎读取本文件；将来移植到前端 docx JS 时直接复用同一份数值。字号单位 pt，几何单位 twips（1 pt = 20 twips）。",
  "_scope": "只对齐表格版式（列宽 / 表头文案 / 边框 / 行高 / 边距）。页眉页脚、章节号、表号、检测示意图、结论文字、固定行数填充均不在范围内，不实现。",
  "page": {
    "widthTwips": 11907,
    "heightTwips": 16839,
    "marginTwips": 1440,
    "marginBottomTwips": 1843,
    "marginHorizontalTwips": 907,
    "headerFooterTwips": 850,
    "footerTwips": 964,
    "docGridLinePitch": 312,
    "_note": "取自**含立柱/横梁表的那一节**（对拍基准第 12-13 页所在节）。真实报告各节并不一致：开头说明节是 上1440/下1440/页眉851，含表节是 上1440/下1843/页眉850。以含表节为准，因为本工具生成的报告就是这一节的等价物。"
  },
  "table": {
    "widthTwips": 10833,
    "align": "center",
    "layout": "fixed",
    "border": {
      "val": "single",
      "space": 0,
      "color": "000000",
      "outerSz": 12,
      "innerSz": 6
    },
    "tableCellMargin": {
      "left": 57,
      "right": 57
    },
    "look": {
      "val": "0000",
      "firstRow": 0,
      "lastRow": 0,
      "firstColumn": 0,
      "lastColumn": 0,
      "noHBand": 0,
      "noVBand": 0
    }
  },
  "columns": {
    "widths": [
      1077,
      850,
      1416,
      789,
      790,
      790,
      789,
      790,
      790,
      790,
      1962
    ],
    "_note": "取自表2-4（立柱）。表2-5（横梁）实测为 [1079, 851, 1417, 789, 790, 790, 789, 790, 790, 790, 1958]，前 3 列与末列相差 ≤4 twips（0.2mm，Word 自动重算所致）。本引擎对两张表输出同一套列宽，故以表2-4 为准；对拍时两侧都归一到本规格。",
    "_widthOverrides": {},
    "index": {
      "floor": 0,
      "position": 1,
      "size": 2,
      "face": 3,
      "readingFirst": 4,
      "readingCount": 5,
      "minimum": 9,
      "requirement": 10
    },
    "mergedInBody": [
      "floor",
      "position",
      "size",
      "requirement"
    ]
  },
  "rows": {
    "headerHeightTwips": 567,
    "dataHeightTwips": 522,
    "_note": "真实报告两张表的数据行高不同：立柱表 522、横梁表 567（与表头同高）。按模板分别取值。",
    "dataHeightByTemplate": {
      "column": 522,
      "beam": 567
    }
  },
  "cell": {
    "_note": "真实表格不在单元格上设 tcMar；内边距由表级 tblCellMar（左右 57）与默认值决定。null = 不写 tcMar。",
    "marginVerticalTwips": null,
    "marginHorizontalTwips": null,
    "requirementMarginTwips": null,
    "_headerLineSpacing_note": "客户模板里表头部分单元格被手工设了固定行距（line=280 atLeast）：第一行前 2 格、第二行前 5 格，两张表一致。对视觉无影响（行高 567 已覆盖 2×14pt），但为逐属性一致而照抄。",
    "headerLineSpacing": {
      "line": 280,
      "lineRule": "atLeast",
      "row0Cells": [
        0,
        1
      ],
      "row1Cells": [
        0,
        1,
        2,
        3,
        4
      ]
    }
  },
  "fonts": {
    "_note": "字体不在本次对齐范围（按约定以样例为准）。真实报告为 eastAsia=SimSun、Normal 10.5pt、两端对齐；真实表格的单元格一律不显式设字号，故 requirementPt 为 null = 继承。",
    "inheritedTablePt": 10,
    "requirementPt": null,
    "bodyPt": 11,
    "titlePt": 16
  },
  "paragraphSpacing": {
    "_note": "保留我们自己的段落骨架（客户端那部分结构不在范围内）。",
    "infoAfter": 100,
    "titleBefore": 300,
    "titleAfter": 200,
    "spacerBefore": 200,
    "spacerAfter": 200,
    "noteBefore": 300
  },
  "headers": {
    "_note": "表头文案实测自真实报告。用 \\n 表示真实表格里的多段落换行（如「检测构件」/「位置」是两段，不是自动折行）。",
    "fixed": [
      "楼层",
      "检测构件\n位置",
      "尺寸检测结果m×n\n（mm×mm）"
    ],
    "thickness": "厚度检测结果（mm）",
    "thicknessSub": [
      "检测面",
      "1",
      "2",
      "3",
      "4",
      "5",
      "最小值"
    ]
  },
  "spans": {
    "thickness": 7
  },
  "_attachment_note": "缺陷报告附页（M3）所需的渲染参数。两列信息表的宽度来自需求报告 4.4（标签列约 1600 twips）；图片压缩参数属渲染参数，不落库，导出时现压。换对拍基准时这些值不随检测表变化，故 extract_layout_spec.py 不比对本段。",
  "attachment": {
    "labelColumnTwips": 1600,
    "valueColumnTwips": 7200,
    "rowHeightTwips": 400,
    "imageLabel": "隐患图片",
    "imageMaxWidthTwips": 8800,
    "imageMaxHeightTwips": 8000,
    "imageMaxPixels": 1600,
    "imageJpegQuality": 80
  }
});

export default SPEC;
