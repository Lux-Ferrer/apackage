# M5 移植验收对拍（JS 生成物 vs 期望文件）

> 这份文件是**闸门 A 的归档报告**。它记录"JS 引擎的产物与 Python 引擎冻结的产物
> 逐属性比到了什么程度"，以及**这个闸门自己可不可信**。
> 命令与设计见 `README.md`「测试」一节与 `docs/management/M5-设计.md` 第 4 节。

## 1. 结论

| 产物 | 期望文件 | 结果 |
| --- | --- | --- |
| `_work/js_generated.docx`（无附页，M2 路径） | `tests/fixtures/generated_baseline.docx` | **全部一致 ✅**（0 差异） |
| `_work/js_generated_attachments.docx`（含附页，M3 路径） | `tests/fixtures/attachment_baseline.docx` | **全部一致 ✅**（0 差异） |

比对项：正文序列、表格级属性、行级属性、单元格级属性、合并网格、**嵌入图片**。

差异收敛过程（M5-2 记录，留作过程证据）：**201 → 33 → 2 → 0**。

M5-3 的附页是**首次跑闸门就是 0 差异**的 —— 因为附页接进引擎时沿用同一套原语
（`paragraph` / `tableCell` / `Table` / 11 个后处理补丁），没有引入新的、未经验证的写法。

## 2. 闸门本身可信吗（这一节比上一节重要）

**闸门绿了，先问"这个属性到底有没有被比"。** 相等有两种来源：两边真的对，或者这个属性
根本没进比对。后者更危险，因为它伪装成前者 —— M5-3 加附页时正好撞上：

> 段落指纹里原本**完全没有图片**（只看 `text / jc / spacing / run_props`，而图片在 `w:drawing` 里）。
> 也就是说：一张图**漏嵌、嵌错文件、尺寸算错、方向没摆正**，闸门都会照样报"全部一致"。

补法（纯加法，不改既有口径）：段落指纹加 `images`（取 `wp:extent` 显示尺寸，EMU），
文档指纹加 `media`（从 `word/media/*` 读**实际像素尺寸**，排序后按多重集比较）。

补完之后用 `tools/verify_gate_sensitivity.py` 做了**阴性 + 阳性对照**：

- 阴性：原样的一对文件必须 0 差异（排除"绿得没意义"的假阳性）；
- 阳性：往产物里逐个下毒，每一项都必须被抓到，且落在**预期的那一类路径**上。

实测结果（7 项全部被抓到）：

| 毒 | 说明 | 闸门报出的路径 |
| --- | --- | --- |
| `image_extent` | 图片显示尺寸改小 | `body[15].images[0][0]` |
| `drop_drawing` | 删掉一个 drawing（漏嵌） | `body[15].images.length` |
| `image_media` | 媒体部件换成 320×200 的图（嵌错文件） | `media` |
| `table_text` | 表格文本改一个字 | `table[2].rows[0].cells[1].paragraphs[0].text` |
| `table_merge` | 破坏一个 `vMerge` 续格 | `grid[0]` |
| `row_height` | 行高 400 → 500 | `table[2].rows[0].trHeight` |
| `bold_label` | 附页标签去掉加粗 | `table[2].rows[0].cells[0].paragraphs[0].run_props[0]` |

复现：`python tools/verify_gate_sensitivity.py`（退出码 0 = 全部抓到）。

## 3. 附页的期望产物从哪来

对拍基准（真实客户报告裁剪版）只含立柱/横梁两张检测表，**没有附页**。
所以附页的期望产物由 `tools/build_attachment_baseline.py` 用 **Python 引擎**单独冻结，
数据定义在 `tools/attachment_fixture.py`（三份缺陷报告覆盖：正常 / 带 EXIF 方向的竖拍 / 图片缺失降级）。

```powershell
python tools/build_attachment_baseline.py          # 生成夹具图片 + 冻结附页基线
python tools/build_attachment_baseline.py --check  # 只检查基线与当前引擎是否一致
```

## 4. Node 里没有 canvas —— 附页图片怎么验

闸门 A 在 Node 里跑，而 Node 里 `createImageBitmap` / `OffscreenCanvas` 都是 `undefined`
（本机实测 Node 25）。这里**没有走"跳过图片验证"那条路**，而是在"编解码"这个接缝上把管线切开：
尺寸与方向的计算走**产品代码**，只有"重采样像素"换成替身（用夹具旁边那份 Pillow 生成的
`_摆正` 副本）。

替身有三道自锁，保证它不会祝福假产物：

1. 要求"画布尺寸 == 可用字节的尺寸"，**对不上直接抛错**；
2. 需要缩放时必然对不上（字节没缩）→ 于是**缩放路径在闸门 A 里是硬的**，
   所以夹具图片一律 ≤1600px。缩放路径由 `web/tests/image_pipeline.test.mjs` 的尺寸断言
   + `docs/management/M5-真机验证checklist.md` 的 B4/B5 覆盖；
3. 闸门的 `media` 检查再独立核对一次"嵌进去的字节到底多大"。

细节见 `docs/management/M5-设计.md` 4.7。
