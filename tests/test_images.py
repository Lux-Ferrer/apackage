# -*- coding: utf-8 -*-
"""隐患图片：上传校验、落盘命名、导出时派生压缩副本。"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from webapp import config
from webapp.services import images


def _fake_upload(data: bytes, filename: str):
    """构造一个最小的 FileStorage 替身（validate_upload 只用到 filename 与 stream）。"""

    class _Storage:
        def __init__(self):
            self.filename = filename
            self.stream = io.BytesIO(data)

    return _Storage()


def _png_bytes(size=(8, 8), image_format="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buffer, image_format)
    return buffer.getvalue()


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------
def test_validate_requires_a_file():
    assert "请上传" in images.validate_upload(None)
    assert "请上传" in images.validate_upload(_fake_upload(b"", ""))


def test_validate_rejects_unsupported_extension():
    error = images.validate_upload(_fake_upload(_png_bytes(), "note.txt"))
    assert error and "格式只支持" in error


def test_validate_rejects_disguised_file():
    """扩展名是 .png 但内容不是图片 —— 必须靠 Pillow 真实识别拦下。"""
    error = images.validate_upload(_fake_upload(b"not an image at all", "fake.png"))
    assert error and "不是有效的图片" in error


def test_validate_rejects_oversized(monkeypatch):
    monkeypatch.setattr(config, "MAX_IMAGE_BYTES", 100)
    error = images.validate_upload(_fake_upload(_png_bytes((64, 64)), "big.png"))
    assert error and "不能超过" in error


def test_validate_accepts_real_image():
    assert images.validate_upload(_fake_upload(_png_bytes(), "photo.png")) is None
    assert images.validate_upload(_fake_upload(_png_bytes(image_format="JPEG"), "photo.jpg")) is None


# --------------------------------------------------------------------------
# 文件名与原文件名追溯
# --------------------------------------------------------------------------
@pytest.mark.parametrize("raw, expected", [
    ("photo.jpg", "photo.jpg"),
    ("../../etc/passwd.png", "passwd.png"),          # 去掉路径成分
    ('a<b>:"c|d?.png', "a_b___c_d_.png"),            # 危险字符替换
    ("隐患照片.PNG", "隐患照片.png"),                  # 保留中文，扩展名统一小写
    ("", "image"),
    ("...", "image"),
])
def test_sanitize_original_name(raw, expected):
    assert images.sanitize_original_name(raw) == expected


def test_original_name_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path)
    storage = _fake_upload(_png_bytes(), "东立面隐患.jpg")
    relative = images.save_upload(storage)

    assert relative.startswith("uploads/defects/")
    assert images.original_name_from_path(relative) == "东立面隐患.jpg"
    assert (tmp_path / relative.split("/")[-1]).exists()


def test_absolute_path_never_escapes_uploads_dir(tmp_path, monkeypatch):
    """路径穿越**不可能发生**：只取文件名后拼到 UPLOADS_DIR 下。"""
    uploads = tmp_path / "uploads" / "defects"
    monkeypatch.setattr(config, "UPLOADS_DIR", uploads)

    resolved = images.absolute_path("uploads/defects/../../secret.png")
    assert resolved == (uploads / "secret.png").resolve()
    assert uploads.resolve() in resolved.parents

    # 正常路径同样成立
    assert images.absolute_path("uploads/defects/photo.jpg") == (uploads / "photo.jpg").resolve()


def test_remove_deletes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path)
    relative = images.save_upload(_fake_upload(_png_bytes(), "x.png"))
    path = tmp_path / relative.split("/")[-1]
    assert path.exists()

    images.remove(relative)
    assert not path.exists()
    images.remove(None)                     # 空值不报错


# --------------------------------------------------------------------------
# 导出时派生压缩副本
# --------------------------------------------------------------------------
def _store(tmp_path, monkeypatch, size, image_format="PNG", exif=None):
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path)
    buffer = io.BytesIO()
    image = Image.new("RGB", size, (30, 60, 90))
    if exif is None:
        image.save(buffer, image_format)
    else:
        image.save(buffer, image_format, exif=exif)
    return images.save_upload(_fake_upload(buffer.getvalue(), "shot.%s" % image_format.lower()))


def test_export_copy_downscales_to_max_pixels(tmp_path, monkeypatch):
    relative = _store(tmp_path, monkeypatch, (3000, 2000))
    result = images.export_copy(relative, tmp_path / "work", max_pixels=1600, quality=80)

    assert result is not None
    assert result["compressed"] is True
    assert max(result["width_px"], result["height_px"]) == 1600
    assert (result["width_px"], result["height_px"]) == (1600, 1067)   # 保持比例
    assert result["path"].exists()
    assert result["path"].suffix == ".jpg"


def test_export_copy_keeps_small_image_unscaled(tmp_path, monkeypatch):
    relative = _store(tmp_path, monkeypatch, (400, 300))
    result = images.export_copy(relative, tmp_path / "work", max_pixels=1600, quality=80)

    assert result["compressed"] is False
    assert (result["width_px"], result["height_px"]) == (400, 300)


def test_export_copy_applies_exif_orientation(tmp_path, monkeypatch):
    """手机竖拍：像素是横的 + EXIF Orientation=6，导出必须摆正。"""
    exif = Image.Exif()
    exif[274] = 6                                       # Orientation = 旋转 90°
    relative = _store(tmp_path, monkeypatch, (400, 200), image_format="JPEG", exif=exif)

    result = images.export_copy(relative, tmp_path / "work", max_pixels=1600, quality=80)
    assert (result["width_px"], result["height_px"]) == (200, 400)     # 宽高互换


def test_export_copy_flattens_transparency_to_white(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path)
    buffer = io.BytesIO()
    Image.new("RGBA", (50, 50), (255, 0, 0, 0)).save(buffer, "PNG")     # 全透明
    relative = images.save_upload(_fake_upload(buffer.getvalue(), "alpha.png"))

    result = images.export_copy(relative, tmp_path / "work", max_pixels=1600, quality=80)
    assert result is not None
    with Image.open(result["path"]) as exported:
        assert exported.mode == "RGB"
        assert exported.getpixel((5, 5)) == (255, 255, 255)             # 白底而非黑底


def test_export_copy_returns_none_when_missing_or_broken(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path)
    assert images.export_copy(None, tmp_path) is None
    assert images.export_copy("uploads/defects/不存在.png", tmp_path) is None

    broken = tmp_path / "broken.png"
    broken.write_bytes(b"garbage")
    assert images.export_copy(images.stored_path("broken.png"), tmp_path) is None
