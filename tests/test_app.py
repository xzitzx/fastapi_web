import pytest

from app.config import settings


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_docs_disabled(client, path):
    """Scenario: 请求接口文档"""
    assert client.get(path).status_code == 404


def test_media_served_from_media_root(client):
    (settings.media_root / "hello.txt").write_text("hi")

    response = client.get("/media/hello.txt")

    assert response.status_code == 200
    assert response.text == "hi"
