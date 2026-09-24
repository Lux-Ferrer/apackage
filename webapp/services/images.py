# -*- coding: utf-8 -*-
"""隐患图片：上传校验、落盘命名、导出时派生压缩副本。

三条原则
--------
1. **原图是证据**：上传时只做校验与落盘，不做任何有损处理；
2. **压缩副本是渲染产物，不落库**：像"最小厚度值"一样在导出时现算 ——
   参数改了历史报告立即跟随，也不需要第二种存储状态或 schema 变更；
3. **原文件名可追溯且不需要额外字段**：落盘名为 ``<uuid>_<清洗后的原名>.<ext>``，
   从路径即可反推原名（uuid 前缀同时防重名与路径穿越）。
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from PIL import Image, ImageOps

from .. import config

# Windows/POSIX 下的非法文件名字符（保留中文，去掉分隔符与控制字符）
_UNSAFE_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_NAME_MAX_LENGTH = 60


def uploads_dir() -> Path:
    """上传目录：**优先取应用配置**，没有应用上下文时退回模块常量。

    单一真相源：路由与服务都在应用里跑，`app.config["UPLOADS_DIR"]` 才是权威
    （部署可改、测试可隔离）；模块常量只是脚本/工具无应用上下文时的兜底。
    """
    try:
        from flask import current_app
        configured = current_app.config.get("UPLOADS_DIR")
    except RuntimeError:                      # 没有应用上下文
        configured = None
    return Path(configured) if configured else config.UPLOADS_DIR


def sanitize_original_name(name: str | None) -> str:
    """清洗上传时的原始文件名，保留可读性（含中文），去掉危险字符。"""
    text = Path(name or "").name                      # 去掉任何路径成分
    text = _UNSAFE_NAME_CHARS.sub("_", text).strip().strip(".")
    if not text:
        return "image"
    stem, dot, suffix = text.rpartition(".")
    if not dot:
        return text[:_NAME_MAX_LENGTH]
    stem = (stem or "image")[:_NAME_MAX_LENGTH]
    return "%s.%s" % (stem, suffix.lower())


def original_name_from_path(relative_path: str | None) -> str:
    """从落盘路径反推原始文件名：``<uuid>_<原名>`` → ``<原名>``。"""
    if not relative_path:
        return ""
    name = Path(relative_path).name
    stem, dot, suffix = name.rpartition(".")
    prefix, separator, rest = stem.partition("_")
    if separator and rest:
        return "%s.%s" % (rest, suffix) if dot else rest
    return name


def stored_path(filename: str) -> str:
    """落盘文件的**相对路径**（入库用相对路径，避免绑定机器）。"""
    return str(Path("uploads") / "defects" / filename).replace("\\", "/")


def absolute_path(relative_path: str) -> Path:
    """相对路径 → 绝对路径。

    只取文件名后拼到 ``config.UPLOADS_DIR`` 下：入库的一律是
    ``uploads/defects/<文件名>``，取 basename 既等价又天然杜绝路径穿越；
    末尾的包含性检查是额外的防守与意图声明。
    """
    uploads = uploads_dir().resolve()
    candidate = (uploads / Path(relative_path).name).resolve()
    if candidate != uploads and uploads not in candidate.parents:
        raise ValueError("图片路径越界：%s" % relative_path)
    return candidate


# --------------------------------------------------------------------------
# 上传校验与落盘
# --------------------------------------------------------------------------
def validate_upload(storage) -> str | None:
    """校验上传文件，返回错误信息（None = 通过）。"""
    if storage is None or not (storage.filename or "").strip():
        return "请上传隐患图片（拍照或从相册选择）"

    extension = Path(storage.filename).suffix.lower()
    if extension not in config.ALLOWED_IMAGE_EXTENSIONS:
        return "图片格式只支持 %s" % "、".join(config.ALLOWED_IMAGE_EXTENSIONS)

    stream = storage.stream
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    if size == 0:
        return "图片文件是空的，请重新选择"
    if size > config.MAX_IMAGE_BYTES:
        return "图片不能超过 %d MB（当前 %.1f MB）" % (
            config.MAX_IMAGE_BYTES // (1024 * 1024), size / (1024 * 1024))

    try:                                   # 真实格式校验：防"改扩展名的假图片"
        with Image.open(stream) as image:
            if image.format not in config.ALLOWED_IMAGE_FORMATS:
                return "图片内容不是支持的格式（识别为 %s）" % (image.format or "未知")
            image.verify()
    except Exception:
        return "这个文件不是有效的图片"
    finally:
        stream.seek(0)
    return None


def save_upload(storage) -> str:
    """保存原图，返回入库用的相对路径。"""
    target_dir = uploads_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    original = sanitize_original_name(storage.filename)
    extension = Path(storage.filename).suffix.lower() or Path(original).suffix or ".jpg"
    filename = "%s_%s" % (uuid.uuid4().hex, Path(original).stem)
    filename = "%s%s" % (filename[:_NAME_MAX_LENGTH + 40], extension)

    storage.stream.seek(0)
    (target_dir / filename).write_bytes(storage.stream.read())
    return stored_path(filename)


def remove(relative_path: str | None) -> None:
    """删除已落盘的图片（用于数据库写入失败后的补偿）。"""
    if not relative_path:
        return
    try:
        absolute_path(relative_path).unlink(missing_ok=True)
    except (ValueError, OSError):
        pass


# --------------------------------------------------------------------------
# 导出时派生压缩副本
# --------------------------------------------------------------------------
def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    """转成 RGB：JPEG 不支持透明通道，透明区域用白底合成而不是留黑。"""
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return image.convert("RGB")


def export_copy(relative_path: str | None, workdir: Path,
                max_pixels: int = 1600, quality: int = 80) -> dict | None:
    """生成导出用的压缩副本，返回 ``{path, width_px, height_px, compressed}``。

    压缩参数由调用方从版式规格传入（属渲染参数，不落库）。
    任何一步失败都返回 None —— 一张图坏掉不能让整份报告导不出来。
    """
    if not relative_path:
        return None
    try:
        source = absolute_path(relative_path)
        if not source.exists():
            return None

        with Image.open(source) as raw:
            oriented = ImageOps.exif_transpose(raw)        # 手机竖拍必须按 EXIF 摆正
            was_large = max(oriented.size) > max_pixels
            if was_large:
                oriented = oriented.copy()
                oriented.thumbnail((max_pixels, max_pixels), Image.LANCZOS)
            rgb = _flatten_to_rgb(oriented)

        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        target = workdir / (Path(relative_path).stem + ".jpg")
        rgb.save(target, "JPEG", quality=int(quality), optimize=True)
        return {
            "path": target,
            "width_px": rgb.width,
            "height_px": rgb.height,
            "compressed": was_large,
        }
    except Exception:
        return None
