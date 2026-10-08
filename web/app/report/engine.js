/* 导出引擎：数据 → docx（M5 移植边界的**内侧**）。
 *
 * 与 `webapp/services/word_report.py` 一一对应。边界见 docs/management/M5-设计.md 第 1 节：
 *   - 本文只负责"数据 → 库能表达的结构"；
 *   - 库表达不了的细节由 `postprocess.js` 补（11 个补丁）；
 *   - "从文档里认表"那一半不在这里（那是测试设施，见 tools/export_fixture_data.py）。
 *
 * 覆盖范围：信息段 + 立柱/横梁检测表 + 备注 + **缺陷报告附页** + 文末空段。
 * 附页里的图片由 `attachments.js` 在**导出时现压**（不落库），本模块只负责嵌入。
 */

import {
    AlignmentType, BorderStyle, Document, HeightRule, ImageRun, LineRuleType, Packer, Paragraph,
    Table, TableCell, TableRow, TableLayoutType, TextRun, VerticalAlign, WidthType,
} from 'docx';

import { CONFIG } from '../config.js';
import { SPEC } from './spec.js';
import {
    ATTACHMENT, NATIVE_TWIPS_PER_PIXEL, attachmentRows, fitImageTwips,
} from './attachments.js';
import { postprocess } from './postprocess.js';

/* ---- 规格常量（全部来自 spec，不在代码里写死数值）---- */
const PAGE = SPEC.page;
const TABLE_SPEC = SPEC.table;
const GRID_COLS = SPEC.columns.widths;
const INDEX = SPEC.columns.index;
const HEADER_ROW_TWIPS = SPEC.rows.headerHeightTwips;
const DATA_ROW_TWIPS = SPEC.rows.dataHeightTwips;
const BODY_HALF_POINTS = Math.round(SPEC.fonts.bodyPt * 2);
const TITLE_HALF_POINTS = Math.round(SPEC.fonts.titlePt * 2);
const SPACING = SPEC.paragraphSpacing;
const HEADER_FIXED = SPEC.headers.fixed;
const HEADER_THICKNESS = SPEC.headers.thickness;
const HEADER_THICKNESS_SUB = SPEC.headers.thicknessSub;
const THICKNESS_FIRST_COL = INDEX.face;
const THICKNESS_SPAN = SPEC.spans.thickness;
const HEADER_LINE_SPACING = SPEC.cell.headerLineSpacing ?? {};

/** 行高为"至少"语义：库的 ATLEAST 会写 hRule，由补丁③删掉。 */
const ROW_HEIGHT_RULE = HeightRule.ATLEAST;

/** 边框：外框粗（outerSz）、内线细（innerSz）；补丁⑩补 `w:space`。两张表共用。 */
function tableBorders() {
    const outer = { style: BorderStyle.SINGLE, size: TABLE_SPEC.border.outerSz, color: TABLE_SPEC.border.color };
    const inner = { style: BorderStyle.SINGLE, size: TABLE_SPEC.border.innerSz, color: TABLE_SPEC.border.color };
    return {
        top: outer, bottom: outer, left: outer, right: outer,
        insideHorizontal: inner, insideVertical: inner,
    };
}

/** tblLook：补丁②把布尔的 false/true 归一成 0/1 并补上 w:val。 */
function tableLook() {
    return {
        firstRow: false, lastRow: false, firstColumn: false,
        lastColumn: false, noHBand: false, noVBand: false,
    };
}

export function dataRowHeight(templateType) {
    return SPEC.rows.dataHeightByTemplate?.[templateType] ?? DATA_ROW_TWIPS;
}

/* --------------------------------------------------------------------------
 * 段落
 * ------------------------------------------------------------------------ */

function paragraph(text, { bold = false, halfPoints = null, align = null,
    before = null, after = null, line = null, pageBreakBefore = false } = {}) {
    const spacing = {};
    if (before !== null) spacing.before = before;
    if (after !== null) spacing.after = after;
    if (line !== null) {
        spacing.line = line;
        spacing.lineRule = LineRuleType.AT_LEAST;
    }
    // ⚠️ bold / size 只在**真需要**时才传：库对 bold:false 会写出 `<w:b w:val="0"/>`，
    // 而闸门只看"有没有 w:b 元素"（`rpr.find(W+"b") is not None`）—— 传 false 就会被判成加粗。
    // 表格里的 run 一律不带 rPr（与基线一致），所以这两个字段必须**省略**而不是设 false。
    const runOptions = { text };
    if (bold) runOptions.bold = true;
    if (halfPoints) runOptions.size = halfPoints;

    const options = {
        children: text ? [new TextRun(runOptions)] : [],
        alignment: align ?? undefined,
        ...(Object.keys(spacing).length ? { spacing } : {}),
        ...(pageBreakBefore ? { pageBreakBefore: true } : {}),
    };
    return new Paragraph(options);
}

/** 项目信息段：加粗 11pt，段后 infoAfter，**左对齐（不写 jc）**。 */
function infoLine(text) {
    return paragraph(text, { bold: true, halfPoints: BODY_HALF_POINTS, after: SPACING.infoAfter });
}

/** 章节标题：居中加粗 16pt，段前 300 段后 200。 */
function sectionTitle(text) {
    return paragraph(text, {
        bold: true, halfPoints: TITLE_HALF_POINTS, align: AlignmentType.CENTER,
        before: SPACING.titleBefore, after: SPACING.titleAfter,
    });
}

/** 表格之后的空段。 */
function spacer() {
    return paragraph('', { before: SPACING.spacerBefore, after: SPACING.spacerAfter });
}

/** 备注段：常规 11pt，段前 300。 */
function note(text) {
    return paragraph(text, { halfPoints: BODY_HALF_POINTS, before: SPACING.noteBefore });
}

/** 文末空段（sectPr 之前那个）。 */
function trailingEmpty() {
    return paragraph('');
}

export function infoLines(project) {
    return CONFIG.PROJECT_INFO_FIELDS.map(
        ([field, label]) => `${label}：${project[field] ?? ''}`);
}

/* --------------------------------------------------------------------------
 * 单元格
 *
 * `text` 里的 `\n` 是**多段落**（真实表格里「检测构件」/「位置」是两段，不是自动折行）。
 * 表格内一律：不写字号（继承）、不加粗、无 tcMar、vAlign=center、段落居中。
 * ------------------------------------------------------------------------ */

function cellParagraphs(text, { align = AlignmentType.CENTER, line = null, bold = false } = {}) {
    const lines = text === null || text === undefined || text === '' ? [''] : String(text).split('\n');
    return lines.map((one) => paragraph(one, { align, line, bold }));
}

function tableCell(definition) {
    const {
        text = '', width, columnSpan, rowSpan,
        align = AlignmentType.CENTER, line = null, bold = false,
    } = definition;
    return new TableCell({
        children: cellParagraphs(text, { align, line, bold }),
        width: { size: width, type: WidthType.DXA },
        verticalAlign: VerticalAlign.CENTER,
        ...(columnSpan && columnSpan > 1 ? { columnSpan } : {}),
        ...(rowSpan && rowSpan > 1 ? { rowSpan } : {}),
    });
}

/* --------------------------------------------------------------------------
 * 表头两行
 *
 * 表头**不加粗**；第一行 5 个 tc（第 4 个跨 7 列），第一行前 3 格与最后一格纵向跨 2 行；
 * 第二行只剩 7 个子表头（其余位置由库按 rowSpan 自动补续格）。
 * ------------------------------------------------------------------------ */

export function headerRows(templateType) {
    const requirementLabel = CONFIG.REQUIREMENT_LABELS[templateType];
    const lineFor = (row, index) => (
        (row === 0 ? HEADER_LINE_SPACING.row0Cells : HEADER_LINE_SPACING.row1Cells) ?? []
    ).includes(index) ? HEADER_LINE_SPACING.line : null;

    const first = [
        { text: HEADER_FIXED[0], width: GRID_COLS[0], rowSpan: 2, line: lineFor(0, 0) },
        { text: HEADER_FIXED[1], width: GRID_COLS[1], rowSpan: 2, line: lineFor(0, 1) },
        { text: HEADER_FIXED[2], width: GRID_COLS[2], rowSpan: 2 },
        {
            text: HEADER_THICKNESS,
            width: GRID_COLS.slice(THICKNESS_FIRST_COL, THICKNESS_FIRST_COL + THICKNESS_SPAN)
                .reduce((sum, value) => sum + value, 0),
            columnSpan: THICKNESS_SPAN,
        },
        { text: requirementLabel, width: GRID_COLS[INDEX.requirement], rowSpan: 2 },
    ];

    const second = HEADER_THICKNESS_SUB.map((label, offset) => ({
        text: label,
        width: GRID_COLS[THICKNESS_FIRST_COL + offset],
        line: lineFor(1, THICKNESS_FIRST_COL + offset),
    }));

    return [
        new TableRow({
            children: first.map(tableCell),
            height: { value: HEADER_ROW_TWIPS, rule: ROW_HEIGHT_RULE },
        }),
        new TableRow({
            children: second.map(tableCell),
            height: { value: HEADER_ROW_TWIPS, rule: ROW_HEIGHT_RULE },
        }),
    ];
}

/* --------------------------------------------------------------------------
 * 数据行
 *
 * 两类纵向合并的**粒度不同**（实测自真实报告，最容易做错的一处）：
 *   - 楼层 / 构件位置 / 尺寸结果：按**构件**合并（多面构件的其余面留空并被合并覆盖）；
 *   - 截面尺寸要求：按**连续相同条文**合并 —— 同一条文横跨多个构件时也只写一次。
 * 单面构件不写纵向合并（与基线一致）。
 * ------------------------------------------------------------------------ */

/**
 * 把分组摊平成"一行一个检测面"，并标注每一列的合并块。
 *
 * 两类合并**粒度不同**（最容易做错的一处）：
 *   - 楼层 / 构件位置 / 尺寸结果：按**构件**合并（`memberStartRow` + `memberFaceCount`）；
 *   - 截面尺寸要求：按**连续相同条文**合并（`requirementStart` + `requirementSpan`）——
 *     同一条文横跨多个构件时也只写一次。
 * 单面构件不写纵向合并（span=null），与基线一致。
 */
export function flattenRows(records) {
    const flat = [];
    for (const item of records) {
        const faces = item.faces ?? [];
        const requirement = item.record.requirement_text || CONFIG.EMPTY_TEXT;
        const memberStartRow = flat.length;
        faces.forEach((face) => {
            flat.push({
                record: item.record,
                face,
                requirement,
                memberStartRow,
                memberFaceCount: faces.length,
                requirementStart: false,
                requirementSpan: null,
            });
        });
    }

    let blockStart = 0;
    for (let index = 0; index <= flat.length; index += 1) {
        const ended = index === flat.length
            || flat[index].requirement !== flat[blockStart].requirement;
        if (!ended) continue;
        const length = index - blockStart;
        if (length > 0) {
            flat[blockStart].requirementStart = true;
            flat[blockStart].requirementSpan = length > 1 ? length : null;
        }
        blockStart = index;
    }
    return flat;
}

/** 一张检测表（表头 2 行 + 每个检测面 1 行）。 */
export function buildDetectionTable(group) {
    const templateType = group.template_type;
    const height = dataRowHeight(templateType);
    const rows = headerRows(templateType);

    flattenRows(group.records).forEach((row, index) => {
        const cells = [];

        if (index === row.memberStartRow) {
            const span = row.memberFaceCount > 1 ? row.memberFaceCount : null;
            cells.push(tableCell({ text: row.record.floor, width: GRID_COLS[0], rowSpan: span }));
            cells.push(tableCell({
                text: row.record.member_position, width: GRID_COLS[1], rowSpan: span,
            }));
            cells.push(tableCell({
                text: row.record.size_result ?? '', width: GRID_COLS[2], rowSpan: span,
            }));
        }

        cells.push(tableCell({ text: row.face.face, width: GRID_COLS[THICKNESS_FIRST_COL] }));
        (row.face.readings_text ?? []).forEach((text, offset) => {
            cells.push(tableCell({ text, width: GRID_COLS[THICKNESS_FIRST_COL + 1 + offset] }));
        });
        cells.push(tableCell({ text: row.face.min_text, width: GRID_COLS[INDEX.minimum] }));

        if (row.requirementStart) {
            cells.push(tableCell({
                text: row.requirement,
                width: GRID_COLS[INDEX.requirement],
                rowSpan: row.requirementSpan,
            }));
        }

        rows.push(new TableRow({
            children: cells,
            height: { value: height, rule: ROW_HEIGHT_RULE },
        }));
    });

    return new Table({
        rows,
        columnWidths: [...GRID_COLS],
        width: { size: TABLE_SPEC.widthTwips, type: WidthType.DXA },
        layout: TableLayoutType.FIXED,
        alignment: AlignmentType.CENTER,
        margins: {
            marginUnitType: WidthType.DXA,
            top: 0,
            bottom: 0,
            left: TABLE_SPEC.tableCellMargin.left,
            right: TABLE_SPEC.tableCellMargin.right,
        },
        borders: tableBorders(),
        tableLook: tableLook(),
    });
}

/* --------------------------------------------------------------------------
 * 附页（缺陷报告，M3/M5-3）
 *
 * 一份附页 = 标题（前加分页）→ 两列信息表（9 行）→ 「隐患图片」标签 + 居中图片；
 * 图片缺失时降级成一行「（图片缺失：原名）」，整份报告照样导得出来。
 * ------------------------------------------------------------------------ */

/** 附页标题：`检测报告附页（1/3）`，居中加粗 16pt，**带 pageBreakBefore**（每份独立成页）。 */
function attachmentTitle(index, total) {
    return paragraph(
        CONFIG.ATTACHMENT_TITLE.replace('{index}', index).replace('{total}', total),
        {
            bold: true,
            halfPoints: TITLE_HALF_POINTS,
            align: AlignmentType.CENTER,
            before: SPACING.titleBefore,
            after: SPACING.titleAfter,
            pageBreakBefore: true,
        },
    );
}

/** 两列信息表：标签列加粗居中（1600）、内容列左对齐（7200），行高 400。 */
export function attachmentTable(view) {
    const rows = attachmentRows(view).map((row) => new TableRow({
        children: [
            tableCell({ text: row.label, width: ATTACHMENT.labelColumnTwips, bold: true }),
            tableCell({
                text: row.value,
                width: ATTACHMENT.valueColumnTwips,
                align: AlignmentType.LEFT,
            }),
        ],
        height: { value: row.height, rule: ROW_HEIGHT_RULE },
    }));

    return new Table({
        rows,
        columnWidths: [ATTACHMENT.labelColumnTwips, ATTACHMENT.valueColumnTwips],
        width: {
            size: ATTACHMENT.labelColumnTwips + ATTACHMENT.valueColumnTwips,
            type: WidthType.DXA,
        },
        layout: TableLayoutType.FIXED,
        alignment: AlignmentType.CENTER,
        margins: {
            marginUnitType: WidthType.DXA,
            top: 0,
            bottom: 0,
            left: TABLE_SPEC.tableCellMargin.left,
            right: TABLE_SPEC.tableCellMargin.right,
        },
        borders: tableBorders(),
        tableLook: tableLook(),
    });
}

/**
 * 居中嵌入一张图片。
 *
 * `ImageRun` 的 `transformation` 单位是 **96 DPI 像素**（不是 EMU），而 twips 与 EMU 的换算是
 * `1 twip = 635 EMU`、与像素是 `1 px = 15 twips`，所以传 `twips / 15` 后由库
 * `Math.round(px * 9525)` 得到 `twips * 635`——与 Python 侧 `Twips(...)` 的结果**逐 EMU 相同**。
 * （`fitImageTwips` 已经取整成整数 twips，故这里的小数不会引入误差。）
 */
function picture(imageBytes, widthTwips, heightTwips) {
    return new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new ImageRun({
            data: imageBytes,
            type: imageType(imageBytes),
            transformation: {
                width: widthTwips / NATIVE_TWIPS_PER_PIXEL,
                height: heightTwips / NATIVE_TWIPS_PER_PIXEL,
            },
        })],
    });
}

/** 按文件头判断图片类型（库需要它来写 [Content_Types].xml 与关系类型）。 */
function imageType(bytes) {
    if (bytes && bytes[0] === 0x89 && bytes[1] === 0x50) return 'png';
    if (bytes && bytes[0] === 0x47 && bytes[1] === 0x49) return 'gif';
    if (bytes && bytes[0] === 0x42 && bytes[1] === 0x4d) return 'bmp';
    return 'jpg';
}

/** 一份附页的全部块（标题 + 信息表 + 图片/降级行）。 */
export function buildAttachment(view, index, total) {
    const blocks = [attachmentTitle(index, total), attachmentTable(view)];

    if (view.image_bytes?.length) {
        const [widthTwips, heightTwips] = fitImageTwips(
            view.image_width_px, view.image_height_px);
        blocks.push(paragraph(ATTACHMENT.imageLabel, {
            halfPoints: BODY_HALF_POINTS,
            align: AlignmentType.LEFT,
            before: SPACING.titleBefore,
            after: SPACING.titleAfter,
        }));
        blocks.push(picture(view.image_bytes, widthTwips, heightTwips));
    } else if (view.original_name) {
        // 降级：图片读不出来也要把附页导出去
        blocks.push(paragraph(`（图片缺失：${view.original_name}）`, {
            halfPoints: BODY_HALF_POINTS,
            align: AlignmentType.LEFT,
            before: SPACING.titleBefore,
        }));
    }
    return blocks;
}

/* --------------------------------------------------------------------------
 * 文档装配
 * ------------------------------------------------------------------------ */

function sectionProperties() {
    return {
        page: {
            size: { width: PAGE.widthTwips, height: PAGE.heightTwips },
            margin: {
                top: PAGE.marginTwips,
                bottom: PAGE.marginBottomTwips ?? PAGE.marginTwips,
                left: PAGE.marginHorizontalTwips,
                right: PAGE.marginHorizontalTwips,
                header: PAGE.headerFooterTwips,
                footer: PAGE.footerTwips ?? PAGE.headerFooterTwips,
                gutter: 0,
            },
        },
    };
}

/**
 * 项目级报告：信息段 →（章节标题 + 表 + 空段）×N → 备注 → 附页×N → 文末空段。
 * 只输出有记录的章节（立柱 / 横梁各自判断）。
 */
export function buildProjectReport(project, groups, attachments = []) {
    const children = [];
    for (const line of infoLines(project)) children.push(infoLine(line));

    for (const group of groups) {
        if (!group.records?.length) continue;
        children.push(sectionTitle(CONFIG.TEMPLATE_TITLES[group.template_type]));
        children.push(buildDetectionTable(group));
        children.push(spacer());
    }

    children.push(note(CONFIG.NOTE_TEXT));

    const views = [...(attachments ?? [])];
    views.forEach((view, offset) => {
        for (const block of buildAttachment(view, offset + 1, views.length)) children.push(block);
    });

    children.push(trailingEmpty());

    return new Document({ sections: [{ properties: sectionProperties(), children }] });
}

/** 生成 docx（经后处理补齐 7 个补丁），返回字节。 */
export async function renderDocx(project, groups, options = {}) {
    const doc = buildProjectReport(project, groups, options.attachments ?? []);
    const raw = await Packer.toBuffer(doc);
    const { bytes } = await postprocess(new Uint8Array(raw), {
        baseDocxBytes: options.baseDocxBytes,
        spec: options.spec,
    });
    return bytes;
}

export { Packer };
