import gc

import pytest

from app.rendering import render_markdown
from tests.conftest import csrf_from

pytestmark = pytest.mark.filterwarnings("error")


def preview(client, data=None, files=None):
    token = csrf_from(client.get("/write").text)
    return client.post(
        "/preview", data=data, files=files, headers={"X-CSRF-Token": token}, follow_redirects=False
    )


def test_preview_code_block(admin_client):
    """Scenario: 预览代码块"""
    body = "# 标题\n\n```python\nprint('hi')\n```\n"

    response = preview(admin_client, {"body": body})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<div class="codehilite"><pre>' in response.text
    # 与详情页同一套渲染规则，且只是片段，不带整页框架
    assert response.text.strip() == str(render_markdown(body))


@pytest.mark.parametrize("body", ["", " \r\n\t "])
def test_preview_empty_body(admin_client, body):
    """Scenario: 预览空正文"""
    response = preview(admin_client, {"body": body})

    assert response.status_code == 200
    assert "没有内容" in response.text
    assert "<html" not in response.text


def test_preview_accepts_csrf_field(admin_client):
    token = csrf_from(admin_client.get("/write").text)

    response = admin_client.post("/preview", data={"csrf_token": token, "body": "*强调*"})

    assert response.status_code == 200
    assert response.text.strip() == "<p><em>强调</em></p>"


@pytest.mark.parametrize(
    "data, files",
    [({}, None), ({}, {"body": ("a.md", b"# x", "text/markdown")})],
    ids=["missing", "file"],
)
def test_preview_malformed_request(admin_client, data, files):
    response = preview(admin_client, data, files)

    assert response.status_code == 400
    gc.collect()
