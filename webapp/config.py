# -*- coding: utf-8 -*-
"""全局配置：路径、业务预置选项、Word 版式基准常量。

约定：
- 业务预置选项集中在这里，路由/服务不散落硬编码字符串；
- **版式**常量实测自对拍基准 ``tests/fixtures/检测表_真实裁剪.docx``（真实客户报告裁剪版），
  由 ``webapp/resources/report_layout.json`` 承载，M2/M3 拼装时直接引用；
- **字体/主题**仍以 ``tests/fixtures/金骐智谷_金骐_检测报告.docx`` 为准（本次不改字体）。
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
# 对拍基准（勿删、勿改动）：由真实报告第 12-13 页裁剪而成，只保留两张检测表
# 生成方式：python tools/build_fixture.py
GOLDEN_SAMPLE = BASE_DIR / "tests" / "fixtures" / "检测表_真实裁剪.docx"
# 字体/主题基准：真实报告的 docDefaults 是 SimSun/10.5pt，本次范围不采纳；
# 底座的 theme（等线）与 styles 仍从这份样例派生。改字体时才动它。
FONT_SAMPLE = BASE_DIR / "tests" / "fixtures" / "金骐智谷_金骐_检测报告.docx"
# 回归基线：M2 验收通过后冻结的生成物，用来捕捉后续改动的意外偏差
# （重新祝福：python tools/compare_report_with_sample.py --bless）
GENERATED_BASELINE = BASE_DIR / "tests" / "fixtures" / "generated_baseline.docx"
# 交付物：5 份样例报告与对拍报告
DELIVERABLES_DIR = BASE_DIR / "deliverables"

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

# 隐患图片上传白名单（扩展名 + Pillow 识别出的真实格式，双重校验）
ALLOWED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")
ALLOWED_IMAGE_FORMATS = ("JPEG", "PNG")

# 登录功能不在本期范围，报告人/部门先取配置常量（将来接入登录再替换）
DEFAULT_REPORTER = {
    "name": "Zeyu Jin",
    "department": "结构工程部",
    "department_code": "KJGL",      # 供 M5「我的」用户卡显示
    "employee_no": "",
}

# 检测报告附页（需求报告 4.4）的字段顺序与标签
# 末尾的「图片文件」是为追溯原文件名而追加的（4.4 的清单里没有它）
ATTACHMENT_LABELS = {
    "defect_type": "缺陷类型",
    "project_part": "工程部位",
    "risk_level": "隐患等级",
    "rectification_plan": "整改方案",
    "extra_advice": "补充建议",
    "related_standards": "相关规范",
    "reporter": "报告人",
    "reported_at": "报告时间",
    "image_file": "图片文件",
}
ATTACHMENT_ORDER = (
    "defect_type", "project_part", "risk_level", "rectification_plan",
    "extra_advice", "related_standards", "reporter", "reported_at", "image_file",
)
# 附页中为空时显示「无」的字段（需求报告 4.4）
ATTACHMENT_EMPTY_FIELDS = ("extra_advice", "related_standards", "image_file")

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

# 短名，用于项目详情/列表的紧凑展示
TEMPLATE_SHORT_NAMES = {
    TEMPLATE_COLUMN: "立柱",
    TEMPLATE_BEAM: "横梁",
}

# Word 章节标题（实测自样例正文）
TEMPLATE_TITLES = {
    TEMPLATE_COLUMN: "幕墙立柱截面尺寸检测结果",
    TEMPLATE_BEAM: "幕墙横梁截面尺寸检测结果",
}

# 表头最后一列的列名（实测自真实报告表2-4/2-5）
# ⚠️ 客户模板里「截面」重复了（截面尺寸**截面**要求）——验收标准是与模板一致，故照抄、不修正
# ⚠️ 横梁表的要求列表头在真实表格里是**两段**（「横梁截面尺寸截面」/「要求（mm）」），用 \n 表示
REQUIREMENT_LABELS = {
    TEMPLATE_COLUMN: "立柱截面尺寸截面要求（mm）",
    TEMPLATE_BEAM: "横梁截面尺寸截面\n要求（mm）",
}

# 检测面标签：短文本，允许自由输入，这里只作为下拉建议值。
# 已确认：立柱真实数据出现 B / H，横梁出现 t；不使用 CHECK 枚举约束。
FACE_SUGGESTIONS = {
    TEMPLATE_COLUMN: ("B", "H"),
    TEMPLATE_BEAM: ("t",),
}

THICKNESS_VALUE_COUNT = 5        # 每个检测面固定 5 个厚度读数
FACE_MAX_COUNT = 6               # 单个构件最多 6 个检测面

# 截面尺寸要求预置条文（需求报告 3.5.2；标点按需求报告走全角）
#
# ⚠️ 只允许**追加**，不要改动/重排已有项：记录里存的是选择时的文案快照，
#    索引一旦错位，历史记录的编辑页就会落到"（历史条文）"分支。
REQUIREMENT_OPTIONS = {
    TEMPLATE_COLUMN: (
        "立柱铝型材开口部位的厚度不应小于3.0mm，闭口部位的厚度不应小于2.5mm",
        "立柱铝型材开口部位的厚度不应小于5.0mm，闭口部位的厚度不应小于3mm",
    ),
    TEMPLATE_BEAM: (
        "当横梁跨度不大于1.2m时，铝型材截面主要受力部位的厚度不应小于2.0mm",
        "当横梁跨度大于1.2m时，其截面主要受力部位的厚度不应小于2.5mm",
        # 追加项（索引 2）：需求报告表 2-5 的"两句合并"写法
        "当横梁跨度不大于1.2m时，铝型材截面主要受力部位的厚度不应小于2.0mm；"
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
