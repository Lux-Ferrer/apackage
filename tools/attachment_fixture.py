# -*- coding: utf-8 -*-
"""附页对拍夹具的**唯一定义**：三份缺陷报告 + 两张图片。

为什么要有这个模块
------------------
附页的数据**不在**对拍基准（真实报告裁剪版）里 —— 基准只含立柱/横梁两张检测表。
所以附页的"期望产物"必须由我们**自己**造一份，并遵守与检测表一样的规矩：
**期望产物由 Python 引擎生成并冻结**，JS 引擎拿同一份数据重跑，逐属性对拍（闸门 A 的第二半）。

于是这里只放"数据"，两份消费者共用：
  - ``tools/build_attachment_baseline.py``：Python 引擎 → ``tests/fixtures/attachment_baseline.docx``
  - ``tools/export_fixture_data.py``：导成 ``web/assets/fixture_data.json`` 的 ``attachments`` 段

三份报告覆盖附页的三个分支
--------------------------
1. **横拍小图**：正常路径（不缩放 → 「已压缩」不出现），且整改方案是**多段落**（含 ``\\n``）；
2. **竖拍 EXIF 图**：存储 600×800 + Orientation=6 → 摆正成 800×600。
   两个引擎若对 EXIF 处理不一致，嵌入尺寸（twips）就会不同 → 闸门立刻红；
3. **文件缺失**：图片记录在、文件不在 → 降级成「（图片缺失：原名）」，
   整份报告照样导得出来；同时覆盖"空字段显示「无」"。

⚠️ 图片一律 ≤1600px（``imageMaxPixels``），**不触发缩放** —— 这是刻意的：
Node 里没有 canvas，闸门 A 用的编解码替身（``tools/js/header-codec.mjs``）
在需要缩放时会直接抛错，从而**不允许静默祝福一个错的产物**。
需要缩放的路径由 ``web/tests/image_pipeline.test.mjs`` + 真机验证覆盖。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE_DIR = ROOT / "tests" / "fixtures" / "attachment"

# 图片文件名（也是 defects.image_path 里 <uuid>_ 之后的部分）
IMAGE_LANDSCAPE = "现场照片_横拍.jpg"
IMAGE_PORTRAIT = "现场照片_竖拍.jpg"          # EXIF Orientation=6，存储 600×800
MISSING_IMAGE = "现场照片_已删除.jpg"          # 只登记不存在的文件 → 走降级分支

# 固定的 uuid 前缀：让 image key（= 落盘名）在不同机器上可复现
UUID_LANDSCAPE = "5f3a1c7e9b2d4a6f8c0e1d2b3a4c5d6e"
UUID_PORTRAIT = "9c8b7a6d5e4f3a2b1c0d9e8f7a6b5c4d"
UUID_MISSING = "1a2b3c4d5e6f708192a3b4c5d6e7f809"

# 横拍图：800×600（宽 > 高）
LANDSCAPE_SIZE = (800, 600)
# 竖拍图：**存储** 600×800，EXIF Orientation=6 → 摆正后 800×600
PORTRAIT_STORED_SIZE = (600, 800)
PORTRAIT_EXIF_ORIENTATION = 6


def image_key(uuid_hex: str, filename: str) -> str:
    """图片 key = ``<uuid>_<清洗后的原名>``（沿用 images.py 的落盘命名，可反推原名）。"""
    return "%s_%s" % (uuid_hex, filename)


# 夹具图片**就按 key 命名落盘**（``<uuid>_现场照片_横拍.jpg``）：这既是 Python 侧的落盘命名，
# 也是 M5 里 images store 的主键。于是"从 key 反推原始文件名"这条原则在夹具里同样成立，
# 不需要任何额外的映射表。
LANDSCAPE_KEY = image_key(UUID_LANDSCAPE, IMAGE_LANDSCAPE)
PORTRAIT_KEY = image_key(UUID_PORTRAIT, IMAGE_PORTRAIT)
MISSING_KEY = image_key(UUID_MISSING, MISSING_IMAGE)


def defect_rows() -> list:
    """三份缺陷报告（字段与 defects 表一致）。

    ``image_path`` 是库里的值（相对 key，不是文件系统路径）——
    与 Python 侧 ``uploads/defects/<key>`` 同一语义，在 M5 里就是 ``images`` store 的主键。
    """
    return [
        {
            "id": 1,
            "project_id": 1,
            "defect_type": "密封胶开裂",
            "project_part": "东立面三层 1# 立柱",
            "risk_level": "高",
            "rectification_plan": "第一行：清除开裂密封胶并清理基材。\n第二行：重新注胶并复检确认无渗漏。",
            "related_standards": "GB/T 21086-2007 第 5.2 条",
            "extra_advice": "建议雨季前完成整改。",
            "reporter_name": "Zeyu Jin",
            "reporter_department": "结构工程部",
            "image_path": LANDSCAPE_KEY,
            "created_at": "2026-09-20 10:24:00",
        },
        {
            "id": 2,
            "project_id": 1,
            "defect_type": "幕墙面板缺陷（石材）",
            "project_part": "南立面五层 2# 横梁上方",
            "risk_level": "中",
            "rectification_plan": "更换受损石板并复核挂件。",
            "related_standards": "JGJ 133-2001 第 6.3 节",
            "extra_advice": None,                       # 空 → 显示「无」
            "reporter_name": "Zeyu Jin",
            "reporter_department": "结构工程部",
            "image_path": PORTRAIT_KEY,
            "created_at": "2026-09-21 14:05:00",
        },
        {
            "id": 3,
            "project_id": 1,
            "defect_type": "明框外框外表面损伤",
            "project_part": "西立面四层 3# 立柱",
            "risk_level": "低",
            "rectification_plan": "打磨后补涂氟碳漆。",
            "related_standards": None,                  # 空 → 显示「无」
            "extra_advice": None,
            "reporter_name": "Zeyu Jin",
            "reporter_department": "结构工程部",
            "image_path": MISSING_KEY,
            "created_at": "2026-09-22 09:41:00",
        },
    ]


def image_sources() -> dict:
    """key → 源图文件（**绝对路径**；缺失的那份指向不存在的文件）。

    "缺失"这一项**故意**指向一个不存在的路径：两个引擎都必须降级，
    而不是抛错或静默丢页。
    """
    return {
        LANDSCAPE_KEY: IMAGE_DIR / LANDSCAPE_KEY,
        PORTRAIT_KEY: IMAGE_DIR / PORTRAIT_KEY,
        MISSING_KEY: IMAGE_DIR / MISSING_KEY,          # 故意不存在
    }


def relative_sources() -> dict:
    """同 :func:`image_sources`，但路径相对仓库根（写进 JSON 用正斜杠）。"""
    return {
        key: str(path.relative_to(ROOT)).replace("\\", "/")
        for key, path in image_sources().items()
    }


def relative_oriented_sources() -> dict:
    """带 EXIF 方向的那张图的**摆正副本**路径（只给 Node 端替身用，见 :func:`make_images`）。"""
    path = IMAGE_DIR / oriented_name(PORTRAIT_KEY)
    return {PORTRAIT_KEY: str(path.relative_to(ROOT)).replace("\\", "/")}


def make_images(directory: Path = IMAGE_DIR) -> list:
    """生成夹具图片（确定性：同样的输入 → 同样的像素）。

    内容是可辨认的几何图形而不是纯色块：将来人工看图时能一眼看出有没有被镜像/旋转。
    竖拍图额外写 EXIF Orientation=6，并**同时产出一份摆正副本**（见下）。
    """
    from PIL import Image, ImageDraw, ImageOps

    directory.mkdir(parents=True, exist_ok=True)
    written = []

    def draw(size, accent):
        image = Image.new("RGB", size, (232, 236, 240))
        pen = ImageDraw.Draw(image)
        width, height = size
        pen.rectangle([4, 4, width - 5, height - 5], outline=(32, 64, 112), width=6)
        # 不对称的标记：左上角一个实心方块 + 两条对角线，镜像/旋转一眼可辨
        pen.rectangle([24, 24, width // 4, height // 5], fill=accent)
        pen.line([0, 0, width - 1, height - 1], fill=(180, 48, 48), width=5)
        pen.line([0, height - 1, width - 1, 0], fill=(48, 140, 88), width=3)
        return image

    landscape = directory / LANDSCAPE_KEY
    draw(LANDSCAPE_SIZE, (200, 140, 40)).save(landscape, "JPEG", quality=88, optimize=True)
    written.append(landscape)

    portrait = directory / PORTRAIT_KEY
    stored = draw(PORTRAIT_STORED_SIZE, (40, 120, 200))
    exif = Image.Exif()
    exif[0x0112] = PORTRAIT_EXIF_ORIENTATION
    stored.save(portrait, "JPEG", quality=88, optimize=True, exif=exif)
    written.append(portrait)

    # ⚠️ 摆正副本：**只给 Node 端的闸门替身用**（Node 里没有 canvas，没法真的旋转像素）。
    # 浏览器管线不需要它 —— canvas 画一遍再编码就得到同样的结果。
    # 不做这一步的话，替身会把"未旋转的像素 + 已摆正的尺寸"嵌进产物，
    # 那就是一个**我们不会真的交付**的假产物（Word 里会被拉伸）。宁可多一个文件。
    oriented = directory / oriented_name(PORTRAIT_KEY)
    # 从**已落盘的字节**重新打开再摆正：`stored` 对象本身不带刚写进去的 EXIF
    # （EXIF 是通过 save(exif=...) 写的），直接用它会得到一份"没转"的副本。
    with Image.open(portrait) as reopened:
        if reopened.size == PORTRAIT_STORED_SIZE and not reopened.getexif().get(0x0112):
            raise RuntimeError("竖拍图的 EXIF Orientation 没写进去，夹具自检失败")
        ImageOps.exif_transpose(reopened).save(oriented, "JPEG", quality=88, optimize=True)
    written.append(oriented)

    # 缺失图片的那一项**不生成文件** —— 但要保证残留文件被清掉，否则夹具会自相矛盾
    stale = directory / MISSING_KEY
    if stale.exists():
        stale.unlink()

    return written


def oriented_name(filename: str) -> str:
    """摆正副本的文件名：``x.jpg`` → ``x_摆正.jpg``。"""
    stem, dot, suffix = filename.rpartition(".")
    return "%s_摆正.%s" % (stem, suffix) if dot else "%s_摆正" % filename


def describe() -> str:
    return "\n".join(
        "  #%s %s / %s / %s → %s" % (row["id"], row["defect_type"], row["project_part"],
                                     row["risk_level"], row["image_path"])
        for row in defect_rows())
