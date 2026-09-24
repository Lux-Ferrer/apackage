-- 建筑幕墙检测报告生成工具 —— 数据库结构
--
-- 范围依据：03 ProjectCharter 3.0（In/Out of scope）
-- 本期只建 4 张表：projects / measurement_records / thickness_readings / defects
--   * 不建 users  —— 登录功能不在范围内（报告人先取 config.DEFAULT_REPORTER）
--   * 不建 notes  —— 速记不在范围内
--   将来若要启用，按 user_version 走迁移脚本追加，不改动既有表。
--
-- 设计要点：
--   1. 立柱/横梁共用 measurement_records，用 template_type 区分；
--   2. thickness_readings.face 为短文本，允许自由输入（真实数据为 B/H/t，不用 CHECK 枚举）；
--   3. 最小值不落库，展示/导出时由 5 个读数计算（services/thickness.py）；
--   4. 删除项目 -> 级联删除检测记录；关联缺陷报告置空保留（ON DELETE SET NULL）。

PRAGMA foreign_keys = ON;

-- 项目 ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_no    TEXT NOT NULL UNIQUE,          -- 项目编号
    house_name    TEXT NOT NULL,                 -- 房屋名称
    house_address TEXT,                          -- 房屋地点（选填）
    client_org    TEXT,                          -- 委托单位（选填）
    test_date     TEXT,                          -- 检测日期（选填，YYYY-MM-DD）
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 立柱/横梁检测记录 ---------------------------------------------------------
-- 一条记录 = 一个构件（楼层 + 构件位置），其下挂 1~6 个检测面的厚度读数。
-- 编辑时 template_type 不可切换（业务约束，在表单层保证）。
CREATE TABLE IF NOT EXISTS measurement_records (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    template_type    TEXT NOT NULL CHECK (template_type IN ('column','beam')),
    floor            TEXT NOT NULL,              -- 楼层，如"六层"
    member_position  TEXT NOT NULL,              -- 构件位置，如"1" / "6°"
    size_result      TEXT,                       -- 尺寸检测结果 m×n，如"82×76"
    requirement_text TEXT,                       -- 截面尺寸要求（保存选择时的文案快照）
    sort_order       INTEGER NOT NULL DEFAULT 0, -- 维持录入顺序
    created_at       TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_measure_records_project
    ON measurement_records(project_id, template_type, sort_order);

-- 每个检测面的 5 个厚度读数 -------------------------------------------------
-- 读数允许留空（现场可能只测 3 个点）；最小值由非空值计算，不冗余存储。
CREATE TABLE IF NOT EXISTS thickness_readings (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL REFERENCES measurement_records(id) ON DELETE CASCADE,
    face      TEXT NOT NULL,                     -- 检测面标签，短文本，如 B / H / t
    value_1   REAL,
    value_2   REAL,
    value_3   REAL,
    value_4   REAL,
    value_5   REAL,
    UNIQUE (record_id, face)
);

CREATE INDEX IF NOT EXISTS idx_thickness_record ON thickness_readings(record_id);

-- 缺陷检测报告 -------------------------------------------------------------
-- project_id 可为空：缺陷报告可以不绑定项目；
-- 删除项目时置空保留（不级联删除报告）。
CREATE TABLE IF NOT EXISTS defects (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    defect_type         TEXT NOT NULL,
    project_part        TEXT NOT NULL,           -- 工程部位
    risk_level          TEXT NOT NULL CHECK (risk_level IN ('高','中','低')),
    rectification_plan  TEXT NOT NULL,           -- 整改方案
    related_standards   TEXT,                    -- 相关规范（多行，选填）
    extra_advice        TEXT,                    -- 补充建议（选填）
    reporter_name       TEXT NOT NULL DEFAULT '',-- 报告人（快照）
    reporter_department TEXT NOT NULL DEFAULT '',-- 部门（快照）
    image_path          TEXT,                    -- 隐患图片相对路径 uploads/defects/xxx
    created_at          TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_defects_project ON defects(project_id);
CREATE INDEX IF NOT EXISTS idx_defects_risk    ON defects(risk_level);
CREATE INDEX IF NOT EXISTS idx_defects_created ON defects(created_at DESC);
