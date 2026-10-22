import io
import secrets
import warnings
from datetime import datetime, timezone
from typing import Literal

from PIL import Image, ImageOps
from starlette.datastructures import UploadFile

from app.config import settings

MAX_BYTES = 10 * 1024 * 1024
ALLOWED_FORMATS = {"JPEG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}


class InvalidImage(Exception):
    """消息即界面上显示的错误提示。"""


def process_image(data: bytes) -> tuple[bytes, str]:
    if len(data) > MAX_BYTES:
        raise InvalidImage("图片不能超过 10MB")
    try:
        with warnings.catch_warnings():
            # 像素数超限时 Pillow 只发警告，同样按解压炸弹拒绝
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=list(ALLOWED_FORMATS)) as image:
                image.verify()
            # verify() 之后对象不能再用，重新打开
            with Image.open(io.BytesIO(data), formats=list(ALLOWED_FORMATS)) as image:
                # 多图 JPEG（MPO）只保存第一张，按静态 JPEG 处理
                fmt = "JPEG" if image.format == "MPO" else image.format
                ext = ALLOWED_FORMATS[fmt]
                # 普通 JPEG 没有 is_animated 属性，PNG、GIF、WebP 都有
                if fmt == "GIF" or (fmt != "JPEG" and image.is_animated):
                    return data, ext
                upright = ImageOps.exif_transpose(image)
        # 只有 save() 的参数才会写入 EXIF；JPEG 注释却默认沿用原图，一并去掉
        upright.info.pop("comment", None)
        # ICC 颜色配置不涉及隐私，保留以免广色域照片颜色变淡；JPEG、WebP 不会自动沿用原图的配置
        options = {"icc_profile": upright.info.get("icc_profile")}
        if fmt in ("JPEG", "WEBP"):
            options["quality"] = 90
        output = io.BytesIO()
        upright.save(output, fmt, **options)
    except Exception as exc:
        raise InvalidImage("只支持 JPG、PNG、GIF、WebP 图片") from exc
    return output.getvalue(), ext


async def save_image(upload: UploadFile, kind: Literal["covers", "uploads"]) -> str:
    data, ext = process_image(await upload.read(MAX_BYTES + 1))
    rel = f"{kind}/{datetime.now(timezone.utc):%Y/%m}/{secrets.token_hex(16)}.{ext}"
    path = settings.media_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel


def media_url(rel: str) -> str:
    return "/media/" + rel


def delete_media(rel: str | None) -> None:
    if not rel:
        return
    # 两边都先 resolve：MEDIA_ROOT 可能经过符号链接（如 macOS 的 /var → /private/var）
    root = settings.media_root.resolve()
    path = (root / rel).resolve()
    if root in path.parents:
        path.unlink(missing_ok=True)
