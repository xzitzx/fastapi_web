import gc
import io
import re

import pytest
from PIL import Image

from app.config import settings
from app.images import MAX_BYTES
from tests.conftest import csrf_from

# 未关闭的上传临时文件会产生 ResourceWarning，测试末尾 gc.collect() 让它在本测试内暴露
pytestmark = pytest.mark.filterwarnings("error")

UNSUPPORTED = "只支持 JPG、PNG、GIF、WebP 图片"


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, "PNG")
    return buffer.getvalue()


def upload(client, files=None, data=None):
    token = csrf_from(client.get("/write").text)
    return client.post(
        "/uploads", data=data, files=files, headers={"X-CSRF-Token": token}, follow_redirects=False
    )


def saved_files() -> list:
    return [path for path in settings.media_root.rglob("*") if path.is_file()]


def test_upload_image(admin_client, client):
    """Scenario: 上传插图"""
    response = upload(admin_client, {"file": ("截图.png", png(), "image/png")})

    assert response.status_code == 200
    url = response.json()["url"]
    assert re.fullmatch(r"/media/uploads/\d{4}/\d{2}/[0-9a-f]{32}\.png", url)
    image = client.get(url)
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert len(saved_files()) == 1
    gc.collect()


@pytest.mark.parametrize(
    "file, message",
    [
        (("a.jpg", b"just some text\n", "image/jpeg"), UNSUPPORTED),
        (("a.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml"), UNSUPPORTED),
        (("big.gif", b"GIF89a" + b"\0" * MAX_BYTES, "image/gif"), "图片不能超过 10MB"),
    ],
    ids=["text-as-jpg", "svg", "too-large"],
)
def test_upload_invalid_image(admin_client, file, message):
    """Scenario: 上传无效插图"""
    response = upload(admin_client, {"file": file})

    assert response.status_code == 400
    assert response.json() == {"error": message}
    assert saved_files() == []
    gc.collect()


def test_upload_accepts_csrf_field(admin_client):
    token = csrf_from(admin_client.get("/write").text)

    response = admin_client.post(
        "/uploads", data={"csrf_token": token}, files={"file": ("a.png", png(), "image/png")}
    )

    assert response.status_code == 200
    assert len(saved_files()) == 1
    gc.collect()


@pytest.mark.parametrize(
    "data, files",
    [({}, None), ({"file": "a.png"}, None), ({}, {"other": ("a.png", png(), "image/png")})],
    ids=["missing", "text-field", "wrong-field"],
)
def test_upload_without_file(admin_client, data, files):
    response = upload(admin_client, files, data)

    assert response.status_code == 400
    assert response.json() == {"error": "没有收到文件"}
    assert saved_files() == []
    gc.collect()
