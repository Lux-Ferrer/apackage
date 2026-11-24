#!/usr/bin/env node
/* 把 docs/release/用户操作手册.md 排成 PDF（Playwright 打开本地 HTML，再 page.pdf()）。
 *
 * 为什么不用 pandoc / docx：
 *   - 手册里全是**图片 + 表格**，pandoc 得装、中文字体还得配；
 *   - 我们已经有 Playwright + Edge，用它渲染 HTML 打印最稳（和浏览器"另存为 PDF"同一套排版引擎）。
 *
 * Markdown 子集（手写解析，够手册用）：
 *   # / ## / ### 标题、段落、- 列表、1. 有序列表、| 表格 |、```代码```、> 引用、--- 分隔线、
 *   ![alt](src) 图片、**粗体**、`行内代码`、[文字](链接)
 *
 * 用法：
 *   node tools/make_manual_pdf.mjs                 # 出 docs/release/用户操作手册.pdf
 *   node tools/make_manual_pdf.mjs --html          # 顺便留一份 .html 便于调样式
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { chromium } from '@playwright/test';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SRC = resolve(ROOT, 'docs/release/用户操作手册.md');
const OUT_PDF = resolve(ROOT, 'docs/release/用户操作手册.pdf');
const OUT_HTML = resolve(ROOT, 'docs/release/用户操作手册.html');

const KEEP_HTML = process.argv.includes('--html');

/* ---------------- 行内标记 ---------------- */
const escapeHtml = (text) => text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function inline(text) {
    let html = escapeHtml(text);
    html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img alt="$1" src="$2">');
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    return html;
}

/* ---------------- 块级解析 ---------------- */
function parse(markdown) {
    const lines = markdown.split(/\r?\n/);
    const html = [];
    let index = 0;

    const flushList = (tag, items) => {
        if (!items.length) return;
        html.push(`<${tag}>${items.map((item) => `<li>${inline(item)}</li>`).join('')}</${tag}>`);
        items.length = 0;
    };

    while (index < lines.length) {
        const line = lines[index];

        // 代码块
        if (line.startsWith('```')) {
            const body = [];
            index += 1;
            while (index < lines.length && !lines[index].startsWith('```')) {
                body.push(lines[index]);
                index += 1;
            }
            index += 1;
            html.push(`<pre><code>${escapeHtml(body.join('\n'))}</code></pre>`);
            continue;
        }

        // 标题
        const heading = /^(#{1,4})\s+(.*)$/.exec(line);
        if (heading) {
            const level = heading[1].length;
            const text = heading[2];
            const id = `h-${html.length}`;
            html.push(`<h${level} id="${id}">${inline(text)}</h${level}>`);
            index += 1;
            continue;
        }

        // 分隔线
        if (/^---+$/.test(line.trim())) {
            html.push('<hr>');
            index += 1;
            continue;
        }

        // 引用（> 开头的连续行，并支持表格/图片等块内容）
        if (line.startsWith('>')) {
            const body = [];
            while (index < lines.length && lines[index].startsWith('>')) {
                body.push(lines[index].replace(/^>\s?/, ''));
                index += 1;
            }
            // 引用块里一行一条：并成一段会把「适用版本 / 适用对象 / 配套文档」挤成一行
            const inner = body
                .map((item) => (item.trim() ? `<p>${inline(item)}</p>` : ''))
                .join('');
            html.push(`<blockquote>${inner}</blockquote>`);
            continue;
        }

        // 表格
        if (line.trim().startsWith('|') && /^\|[\s:|-]+\|$/.test((lines[index + 1] ?? '').trim())) {
            const cells = (row) => row.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim());
            const headers = cells(line);
            index += 2;
            const rows = [];
            while (index < lines.length && lines[index].trim().startsWith('|')) {
                rows.push(cells(lines[index]));
                index += 1;
            }
            html.push('<table>'
                + `<thead><tr>${headers.map((cell) => `<th>${inline(cell)}</th>`).join('')}</tr></thead>`
                + `<tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${inline(cell)}</td>`).join('')}</tr>`).join('')}</tbody>`
                + '</table>');
            continue;
        }

        // 列表
        if (/^[-*]\s+/.test(line)) {
            const items = [];
            while (index < lines.length && /^[-*]\s+/.test(lines[index])) {
                items.push(lines[index].replace(/^[-*]\s+/, ''));
                index += 1;
            }
            flushList('ul', items);
            continue;
        }
        if (/^\d+\.\s+/.test(line)) {
            const items = [];
            while (index < lines.length && /^\d+\.\s+/.test(lines[index])) {
                items.push(lines[index].replace(/^\d+\.\s+/, ''));
                index += 1;
            }
            flushList('ol', items);
            continue;
        }

        // 空行
        if (!line.trim()) {
            index += 1;
            continue;
        }

        // 段落（连续非空行合并）
        const paragraph = [];
        while (index < lines.length && lines[index].trim()
            && !/^(#{1,4}\s|[-*]\s|\d+\.\s|>|\||```|---+$)/.test(lines[index])) {
            paragraph.push(lines[index]);
            index += 1;
        }
        if (paragraph.length) {
            html.push(`<p>${inline(paragraph.join(''))}</p>`);
        } else {
            index += 1;                    // 兜底，避免死循环
        }
    }
    return html.join('\n');
}

const CSS = `
@page { size: A4; margin: 18mm 16mm 16mm; }
* { box-sizing: border-box; }
body {
  font: 10.5pt/1.75 "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
  color: #1f2937; margin: 0;
}
h1 { font-size: 22pt; color: #1f4e79; margin: 0 0 6mm; }
h2 { font-size: 15pt; color: #1f4e79; margin: 9mm 0 3mm; padding-bottom: 1.5mm;
     border-bottom: 1px solid #d6dee8; page-break-after: avoid; }
h3 { font-size: 12pt; color: #111827; margin: 6mm 0 2mm; page-break-after: avoid; }
p { margin: 0 0 2.5mm; }
ul, ol { margin: 0 0 3mm; padding-left: 6mm; }
li { margin-bottom: 1mm; }
strong { color: #111827; }
code { font-family: Consolas, "Courier New", monospace; background: #f1f5f9;
       padding: 0.3mm 1.2mm; border-radius: 1mm; font-size: 9.5pt; }
pre { background: #f8fafc; border: 1px solid #e2e8f0; border-left: 3px solid #1f4e79;
      padding: 2.5mm 3mm; overflow-x: auto; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
blockquote { margin: 0 0 3mm; padding: 2mm 3mm; background: #f7fafc;
             border-left: 3px solid #94a3b8; color: #334155; }
blockquote p { margin: 0 0 1mm; }
table { width: 100%; border-collapse: collapse; margin: 0 0 4mm;
        font-size: 9.5pt; page-break-inside: avoid; }
th, td { border: 1px solid #c9d3de; padding: 1.5mm 2mm; text-align: left; vertical-align: top; }
th { background: #eef3f9; color: #1f4e79; font-weight: 600; }
tbody tr:nth-child(even) td { background: #fafbfd; }
img { display: block; max-width: 56%; margin: 2mm auto 5mm; border: 1px solid #dde3ea;
      border-radius: 2mm; page-break-inside: avoid; }
/* 连续的几张截图并排两列：一张占大半页太浪费，两列既省页数又还看得清 */
.shots { display: flex; gap: 4mm; margin: 2mm 0 5mm; page-break-inside: avoid; }
.shots img { max-width: 49%; margin: 0; }
hr { border: none; border-top: 1px solid #e2e8f0; margin: 6mm 0; }
a { color: #1f4e79; text-decoration: none; }
.cover { text-align: center; padding: 60mm 0 0; }
.cover h1 { font-size: 26pt; margin-bottom: 10mm; }
.cover .meta { color: #475569; font-size: 11pt; line-height: 2; }
`;

async function main() {
    const markdown = readFileSync(SRC, 'utf8');
    let body = parse(markdown);

    // 连续 2 张及以上的截图并成一行（两列）：一张占大半页太浪费
    body = body.replace(/(?:<p><img [^>]+><\/p>\s*){2,}/g, (run) => {
        const images = [...run.matchAll(/<p>(<img [^>]+>)<\/p>/g)].map((match) => match[1]);
        return `<div class="shots">${images.join('')}</div>`;
    });

    const html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>建筑幕墙检测报告工具 · 用户操作手册</title>
<style>${CSS}</style></head>
<body>${body}</body></html>`;

    mkdirSync(dirname(OUT_HTML), { recursive: true });
    writeFileSync(OUT_HTML, html, 'utf8');

    const browser = await chromium.launch({ channel: 'msedge' });
    const page = await browser.newPage();
    await page.goto(pathToFileURL(OUT_HTML).href, { waitUntil: 'load' });
    await page.waitForTimeout(400);
    await page.pdf({
        path: OUT_PDF,
        format: 'A4',
        printBackground: true,
        displayHeaderFooter: true,
        headerTemplate: '<div></div>',
        footerTemplate: '<div style="width:100%;font:8pt sans-serif;color:#94a3b8;'
            + 'padding:0 16mm;display:flex;justify-content:space-between;">'
            + '<span>建筑幕墙检测报告工具 · 用户操作手册</span>'
            + '<span>第 <span class="pageNumber"></span> / <span class="totalPages"></span> 页</span></div>',
        margin: { top: '16mm', bottom: '16mm', left: '16mm', right: '16mm' },
    });
    await browser.close();

    if (!KEEP_HTML) {
        // 不留 html 时删掉（PDF 已生成）
        try { (await import('node:fs')).unlinkSync(OUT_HTML); } catch { /* ignore */ }
    }

    console.log(`✅ PDF: ${OUT_PDF}`);
    console.log(`   源文件: ${SRC}`);
}

await main();
