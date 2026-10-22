import asyncio
import dataclasses
import io
import re

import pytest
from PIL import Image, ImageCms
from starlette.datastructures import UploadFile

from app import images
from app.config import settings
from app.images import (
    ALLOWED_FORMATS,
    MAX_BYTES,
    InvalidImage,
    delete_media,
    media_url,
    process_image,
    save_image,
)

UNSUPPORTED = "只支持 JPG、PNG、GIF、WebP 图片"
TOO_LARGE = "图片不能超过 10MB"
SVG = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8">'
    b'<rect width="8" height="8" fill="red"/></svg>'
)


def make_image(fmt, size=(8, 8), **save_kwargs) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "red").save(buffer, fmt, **save_kwargs)
    return buffer.getvalue()


def noisy_image(fmt) -> bytes:
    buffer = io.BytesIO()
    Image.effect_noise((64, 64), 64).convert("RGB").save(buffer, fmt, quality=100)
    return buffer.getvalue()


def animated_image(fmt) -> bytes:
    frames = [Image.new("RGB", (8, 8), color) for color in ("red", "blue")]
    buffer = io.BytesIO()
    frames[0].save(buffer, fmt, save_all=True, append_images=frames[1:], duration=100, loop=0)
    return buffer.getvalue()


def gps_exif() -> Image.Exif:
    exif = Image.Exif()
    # 顶层没有标签时 Exif 对象为假值，PNG 保存会忽略它
    exif[0x010F] = "Phone Maker"
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (31.0, 14.0, 0.0)
    gps[3] = "E"
    gps[4] = (121.0, 28.0, 0.0)
    return exif


def padded_gif(total: int) -> bytes:
    # 真实的 GIF 后面补零到指定大小，解码器忽略结束符之后的数据
    gif = make_image("GIF")
    return gif + b"\0" * (total - len(gif))


def save(data: bytes, filename="a.jpg", kind="covers") -> str:
    return asyncio.run(save_image(UploadFile(io.BytesIO(data), filename=filename), kind))


def saved_files() -> list:
    return [path for path in settings.media_root.rglob("*") if path.is_file()]


def rejection(data: bytes) -> str:
    with pytest.raises(InvalidImage) as excinfo:
        save(data)
    assert saved_files() == []
    return str(excinfo.value)


def test_constants():
    assert MAX_BYTES == 10 * 1024 * 1024
    assert ALLOWED_FORMATS == {"JPEG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}


# 图片校验


def test_text_file_named_jpg_rejected():
    """Scenario: 伪装成图片的文本文件"""
    assert rejection(b"just some text, not an image\n") == UNSUPPORTED


def test_svg_rejected():
    """Scenario: 拒绝 SVG"""
    assert rejection(SVG) == UNSUPPORTED


def test_over_size_limit_rejected():
    """Scenario: 超过大小限制"""
    assert rejection(padded_gif(MAX_BYTES + 1)) == TOO_LARGE


def test_exactly_size_limit_accepted():
    rel = save(padded_gif(MAX_BYTES))

    assert (settings.media_root / rel).stat().st_size == MAX_BYTES


def test_reads_at_most_limit_plus_one_byte():
    file = io.BytesIO(b"\0" * (MAX_BYTES * 2))

    with pytest.raises(InvalidImage):
        asyncio.run(save_image(UploadFile(file, filename="a.gif"), "uploads"))

    assert file.tell() == MAX_BYTES + 1


def test_empty_file_rejected():
    assert rejection(b"") == UNSUPPORTED


def test_unsupported_image_format_rejected():
    assert rejection(make_image("BMP")) == UNSUPPORTED


def test_corrupted_png_rejected():
    data = bytearray(make_image("PNG", size=(16, 16)))
    data[data.index(b"IDAT") + 6] ^= 0xFF

    assert rejection(bytes(data)) == UNSUPPORTED


def test_corrupted_animated_png_rejected():
    # 动图原样保存、不会解码，只能靠 verify() 发现校验和错误
    data = bytearray(animated_image("PNG"))
    data[data.index(b"IDAT") + 6] ^= 0xFF

    assert rejection(bytes(data)) == UNSUPPORTED


def test_truncated_jpeg_rejected():
    data = noisy_image("JPEG")

    assert rejection(data[: len(data) // 2]) == UNSUPPORTED


# 超过 MAX_IMAGE_PIXELS 时 Pillow 只发警告；全局忽略该警告时也必须拒绝
@pytest.mark.filterwarnings("ignore::PIL.Image.DecompressionBombWarning")
@pytest.mark.parametrize("size", [(12, 10), (20, 20)], ids=["warning", "error"])
def test_decompression_bomb_rejected(monkeypatch, size):
    data = make_image("PNG", size=size)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)

    assert rejection(data) == UNSUPPORTED


def test_saved_name_is_random_with_extension_from_content():
    first = save(make_image("PNG"), filename="photo.jpg", kind="uploads")
    second = save(make_image("PNG"), filename="photo.jpg", kind="uploads")

    for rel in (first, second):
        assert re.fullmatch(r"uploads/\d{4}/\d{2}/[0-9a-f]{32}\.png", rel)
        assert (settings.media_root / rel).is_file()
    assert first != second


@pytest.mark.parametrize("fmt, ext", ALLOWED_FORMATS.items())
def test_extension_from_format(fmt, ext):
    assert process_image(make_image(fmt))[1] == ext


# 去除照片元数据


def test_gps_exif_removed_from_jpeg():
    """Scenario: 带 GPS 的手机照片"""
    data = make_image("JPEG", exif=gps_exif())
    with Image.open(io.BytesIO(data)) as image:
        assert image.getexif().get_ifd(0x8825)

    saved = (settings.media_root / save(data)).read_bytes()

    with Image.open(io.BytesIO(saved)) as image:
        assert len(image.getexif()) == 0
    assert b"Exif" not in saved


@pytest.mark.parametrize("fmt, ext, chunk", [("PNG", "png", b"eXIf"), ("WEBP", "webp", b"EXIF")])
def test_png_and_webp_reencoded_without_exif(fmt, ext, chunk):
    data = make_image(fmt, exif=gps_exif())
    with Image.open(io.BytesIO(data)) as image:
        assert image.getexif().get_ifd(0x8825)

    output, got_ext = process_image(data)

    assert got_ext == ext
    with Image.open(io.BytesIO(output)) as image:
        assert image.format == fmt
        assert len(image.getexif()) == 0
    assert chunk not in output


def test_multi_picture_jpeg_saved_as_first_frame_without_exif():
    # 多图 JPEG（MPO）：Pillow 识别为 MPO 动图，应按静态 JPEG 只保存第一张
    frames = [Image.new("RGB", (40, 20), color) for color in ("red", "blue")]
    buffer = io.BytesIO()
    frames[0].save(buffer, "MPO", save_all=True, append_images=frames[1:], exif=gps_exif())
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as image:
        assert (image.format, image.n_frames) == ("MPO", 2)
        assert image.getexif().get_ifd(0x8825)

    rel = save(data)

    assert rel.endswith(".jpg")
    saved = (settings.media_root / rel).read_bytes()
    with Image.open(io.BytesIO(saved)) as image:
        assert image.format == "JPEG"
        assert image.size == (40, 20)
        assert len(image.getexif()) == 0
        red, green, blue = image.getpixel((20, 10))
        assert red > 200 and green < 50 and blue < 50
    assert b"Exif" not in saved
    assert b"MPF" not in saved


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_icc_profile_kept_while_exif_removed(fmt):
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    data = make_image(fmt, icc_profile=icc, exif=gps_exif())

    output, _ = process_image(data)

    with Image.open(io.BytesIO(output)) as image:
        assert image.info.get("icc_profile") == icc
        assert len(image.getexif()) == 0


def test_jpeg_comment_removed():
    data = make_image("JPEG", comment=b"secret note")

    output, _ = process_image(data)

    assert b"secret note" not in output


def test_jpeg_orientation_applied():
    exif = Image.Exif()
    exif[0x0112] = 6  # 需要顺时针旋转 90 度显示
    data = make_image("JPEG", size=(40, 20), exif=exif)

    output, _ = process_image(data)

    with Image.open(io.BytesIO(output)) as image:
        assert image.size == (20, 40)
        assert 0x0112 not in image.getexif()


@pytest.mark.parametrize("fmt", ["JPEG", "WEBP"])
def test_reencoded_with_quality_90(fmt):
    data = noisy_image(fmt)
    expected = io.BytesIO()
    with Image.open(io.BytesIO(data)) as image:
        image.save(expected, fmt, quality=90)

    output, _ = process_image(data)

    assert output == expected.getvalue()


def test_static_gif_saved_as_is():
    data = make_image("GIF", comment=b"kept")

    assert process_image(data) == (data, "gif")


@pytest.mark.parametrize("fmt, ext", [("GIF", "gif"), ("PNG", "png"), ("WEBP", "webp")])
def test_animated_image_saved_as_is(fmt, ext):
    data = animated_image(fmt)
    with Image.open(io.BytesIO(data)) as image:
        assert image.is_animated

    assert process_image(data) == (data, ext)


# 地址与删除


def test_media_url():
    assert media_url("covers/2026/10/abc.jpg") == "/media/covers/2026/10/abc.jpg"


def test_delete_media_removes_file():
    rel = save(make_image("PNG"))

    delete_media(rel)

    assert not (settings.media_root / rel).exists()


def test_delete_media_ignores_none_and_missing_file():
    delete_media(None)
    delete_media("covers/2026/10/missing.png")


def test_delete_media_refuses_paths_outside_media_root(tmp_path):
    beside = settings.media_root.parent / "beside.txt"
    beside.write_text("x")
    absolute = tmp_path / "absolute.txt"
    absolute.write_text("x")
    try:
        delete_media("../beside.txt")
        delete_media(str(absolute))
        delete_media("covers/../../beside.txt")

        assert beside.exists()
        assert absolute.exists()
    finally:
        beside.unlink()


def test_delete_media_with_symlinked_media_root(tmp_path, monkeypatch):
    # macOS 的临时目录 /var/folders 就是指向 /private/var 的符号链接
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    monkeypatch.setattr(images, "settings", dataclasses.replace(settings, media_root=link))
    (real / "a.png").write_bytes(b"x")

    delete_media("a.png")

    assert not (real / "a.png").exists()
