# -*- coding: utf-8 -*-
"""全局配置：路径、业务预置选项、Word 版式基准常量。

约定：
- 业务预置选项集中在这里，路由/服务不散落硬编码字符串；
- Word 版式常量全部实测自对拍基准 ``tests/fixtures/金骐智谷_金骐_检测报告.docx``，
  M2 拼装立柱/横梁表时直接引用，避免"凭肉眼调格式"。
"""

from pathlib import Path

# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent        # 项目根目录
WEBAPP_DIR = Path(__file__).resolve().parent             # webapp 包
RESOURCE_DIR = WEBAPP_DIR / "resources"

DB_PATH = BASE_DIR / "defects.db"
REPORTS_DIR = BASE_DIR / "reports"                       # 导出的 .docx
UPLOADS_DIR = BASE_DIR / "uploads" / "defects"           # 隐患图片

# 报告底座模板（由样例派生：保留其 theme/styles/sectPr，清空正文）
REPORT_BASE_TEMPLATE = RESOURCE_DIR / "report_base.docx"
# 对拍基准样例（勿删、勿改动）
GOLDEN_SAMPLE = BASE_DIR / "tests" / "fixtures" / "金骐智谷_金骐_检测报告.docx"

# --------------------------------------------------------------------------
# 缺陷检测填报（需求报告 3.3）
# --------------------------------------------------------------------------
CUSTOM_DEFECT_OPTION = "其他（自定义输入）"

DEFECT_TYPES = (
    "玻璃面板碎裂缺失",
    "密封胶开裂",
    "幕墙面板缺陷（玻璃）",
    "幕墙面板缺陷（石材）",
    "幕墙面板缺陷（铝板）",
    "半隐框外表面损伤",
    "明框外框外表面损伤",
    "广告立牌缺陷",
    "红外热成像异常",
    CUSTOM_DEFECT_OPTION,
)

RISK_LEVELS = ("高", "中", "低")
DEFAULT_RISK_LEVEL = "中"

MAX_IMAGE_BYTES = 20 * 1024 * 1024                      # 单张隐患图片 ≤20MB

# 登录功能不在本期范围，报告人/部门先取配置常量（将来接入登录再替换）
DEFAULT_REPORTER = {
    "name": "Zeyu Jin",
    "department": "结构工程部",
}

# --------------------------------------------------------------------------
# 检测记录模板（立柱 / 横梁共用一张表，template_type 区分）
# --------------------------------------------------------------------------
TEMPLATE_COLUMN = "column"
TEMPLATE_BEAM = "beam"
TEMPLATE_TYPES = (TEMPLATE_COLUMN, TEMPLATE_BEAM)

TEMPLATE_NAMES = {
    TEMPLATE_COLUMN: "幕墙立柱",
    TEMPLATE_BEAM: "幕墙横梁",
}

# Word 章节标题（实测自样例正文）
TEMPLATE_TITLES = {
    TEMPLATE_COLUMN: "幕墙立柱截面尺寸检测结果",
    TEMPLATE_BEAM: "幕墙横梁截面尺寸检测结果",
}

# 表头最后一列的列名（实测自样例表头）
REQUIREMENT_LABELS = {
    TEMPLATE_COLUMN: "立柱截面尺寸要求",
    TEMPLATE_BEAM: "横梁截面尺寸要求",
}

# 检测面标签：短文本，允许自由输入，这里只作为下拉建议值。
# 已确认：立柱真实数据出现 B / H，横梁出现 t；不使用 CHECK 枚举约束。
FACE_SUGGESTIONS = {
    TEMPLATE_COLUMN: ("B", "H"),
    TEMPLATE_BEAM: ("t",),
}

THICKNESS_VALUE_COUNT = 5        # 每个检测面固定 5 个厚度读数
FACE_MAX_COUNT = 6               # 单个构件最多 6 个检测面

# 截面尺寸要求预置条文（需求报告 3.5.2）
REQUIREMENT_OPTIONS = {
    TEMPLATE_COLUMN: (
        "立柱铝型材开口部位的厚度不应小于3.0mm，闭口部位的厚度不应小于2.5mm",
        "立柱铝型材开口部位的厚度不应小于5.0mm，闭口部位的厚度不应小于3mm",
    ),
    TEMPLATE_BEAM: (
        "当横梁跨度不大于1.2m时，铝型材截面主要受力部位的厚度不应小于2.0mm",
        "当横梁跨度大于1.2m时，其截面主要受力部位的厚度不应小于2.5mm",
    ),
}

# --------------------------------------------------------------------------
# Word 报告文案（需求报告第四章）
# --------------------------------------------------------------------------
PROJECT_INFO_FIELDS = (
    ("project_no", "项目编号"),
    ("house_name", "房屋名称"),
    ("house_address", "房屋地点"),
    ("client_org", "委托单位"),
    ("test_date", "检测日期"),
)

NOTE_TEXT = "备注：检测构件位置详见检测工作内容附件 18。"
REPORT_FILENAME = "{project_no}_{house_name}_检测报告.docx"
ATTACHMENT_TITLE = "检测报告附页（{index}/{total}）"
EMPTY_TEXT = "无"                # 截面尺寸要求/选填字段为空时的占位
