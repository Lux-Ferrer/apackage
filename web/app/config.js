/* 本文件为构建产物，请勿手改（改了下次构建会被覆盖）。
 * 内容：业务预置数据（模板 / 条文 / 字段上限…）
 *
 * 要换默认报告人/部门：改 app/product.js 里的 DEFAULT_PROFILE，
 * 或者直接用界面「我的 → 个人信息配置」填一次（保存在本机，优先级更高）。
 */

export const CONFIG = Object.freeze({
  "TEMPLATE_COLUMN": "column",
  "TEMPLATE_BEAM": "beam",
  "TEMPLATE_TYPES": [
    "column",
    "beam"
  ],
  "TEMPLATE_NAMES": {
    "column": "幕墙立柱",
    "beam": "幕墙横梁"
  },
  "TEMPLATE_TITLES": {
    "column": "幕墙立柱截面尺寸检测结果",
    "beam": "幕墙横梁截面尺寸检测结果"
  },
  "TEMPLATE_SHORT_NAMES": {
    "column": "立柱",
    "beam": "横梁"
  },
  "REQUIREMENT_LABELS": {
    "column": "立柱截面尺寸截面要求（mm）",
    "beam": "横梁截面尺寸截面\n要求（mm）"
  },
  "REQUIREMENT_OPTIONS": {
    "column": [
      "立柱铝型材开口部位的厚度不应小于3.0mm，闭口部位的厚度不应小于2.5mm",
      "立柱铝型材开口部位的厚度不应小于5.0mm，闭口部位的厚度不应小于3mm"
    ],
    "beam": [
      "当横梁跨度不大于1.2m时，铝型材截面主要受力部位的厚度不应小于2.0mm",
      "当横梁跨度大于1.2m时，其截面主要受力部位的厚度不应小于2.5mm",
      "当横梁跨度不大于1.2m时，铝型材截面主要受力部位的厚度不应小于2.0mm；当横梁跨度大于1.2m时，其截面主要受力部位的厚度不应小于2.5mm"
    ]
  },
  "FACE_SUGGESTIONS": {
    "column": [
      "B",
      "H"
    ],
    "beam": [
      "t"
    ]
  },
  "THICKNESS_VALUE_COUNT": 5,
  "FACE_MAX_COUNT": 6,
  "RISK_LEVELS": [
    "高",
    "中",
    "低"
  ],
  "DEFAULT_RISK_LEVEL": "中",
  "DEFECT_TYPES": [
    "玻璃面板碎裂缺失",
    "密封胶开裂",
    "幕墙面板缺陷（玻璃）",
    "幕墙面板缺陷（石材）",
    "幕墙面板缺陷（铝板）",
    "半隐框外表面损伤",
    "明框外框外表面损伤",
    "广告立牌缺陷",
    "红外热成像异常",
    "其他（自定义输入）"
  ],
  "CUSTOM_DEFECT_OPTION": "其他（自定义输入）",
  "RISK_BADGE_CLASSES": {
    "高": "high",
    "中": "medium",
    "低": "low"
  },
  "EMPTY_TEXT": "无",
  "NOTE_TEXT": "备注：检测构件位置详见检测工作内容附件 18。",
  "PROJECT_INFO_FIELDS": [
    [
      "project_no",
      "项目编号"
    ],
    [
      "house_name",
      "房屋名称"
    ],
    [
      "house_address",
      "房屋地点"
    ],
    [
      "client_org",
      "委托单位"
    ],
    [
      "test_date",
      "检测日期"
    ]
  ],
  "REPORT_FILENAME": "{project_no}_{house_name}_检测报告.docx",
  "ATTACHMENT_LABELS": {
    "defect_type": "缺陷类型",
    "project_part": "工程部位",
    "risk_level": "隐患等级",
    "rectification_plan": "整改方案",
    "extra_advice": "补充建议",
    "related_standards": "相关规范",
    "reporter": "报告人",
    "reported_at": "报告时间",
    "image_file": "图片文件"
  },
  "ATTACHMENT_ORDER": [
    "defect_type",
    "project_part",
    "risk_level",
    "rectification_plan",
    "extra_advice",
    "related_standards",
    "reporter",
    "reported_at",
    "image_file"
  ],
  "ATTACHMENT_EMPTY_FIELDS": [
    "extra_advice",
    "related_standards",
    "image_file"
  ],
  "ATTACHMENT_TITLE": "检测报告附页（{index}/{total}）",
  "DEFAULT_REPORTER": {
    "name": "Zeyu Jin",
    "department": "结构工程部",
    "department_code": "KJGL",
    "employee_no": ""
  },
  "APP_INFO": {
    "name": "建筑幕墙检测报告生成工具",
    "name_en": "Existing Curtain Wall Inspection Data Recording and Report Generation Tool",
    "version": "1.0.0",
    "org": "NYU MS in Management and Systems · Capstone",
    "client": "中冶建筑研究总院（深圳）有限公司"
  },
  "MAX_IMAGE_BYTES": 20971520,
  "ALLOWED_IMAGE_EXTENSIONS": [
    ".jpg",
    ".jpeg",
    ".png"
  ],
  "ALLOWED_IMAGE_FORMATS": [
    "JPEG",
    "PNG"
  ],
  "THUMBNAIL_MAX_PIXELS": 240,
  "THUMBNAIL_JPEG_QUALITY": 75,
  "PROJECT_FIELD_LIMITS": {
    "project_no": [
      50,
      "项目编号"
    ],
    "house_name": [
      100,
      "房屋名称"
    ],
    "house_address": [
      200,
      "房屋地点"
    ],
    "client_org": [
      100,
      "委托单位"
    ]
  }
});

export default CONFIG;
