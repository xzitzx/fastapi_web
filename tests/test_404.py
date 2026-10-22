import re

import pytest


def test_missing_post(client):
    """Scenario: 文章不存在"""
    response = client.get("/post/999999/")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert "页面不存在" in response.text
    assert re.search(r'<a\b[^>]*href="/"[^>]*>返回首页</a>', response.text)
    assert '<nav class="site-nav"' in response.text
    assert '<footer class="site-footer">' in response.text


@pytest.mark.parametrize("path", ["/register/", "/accounts/login/", "/admin/"])
def test_removed_routes(client, path):
    """Scenario: 已删除的旧路由"""
    response = client.get(path)

    assert response.status_code == 404
    assert "页面不存在" in response.text


def test_other_http_errors_use_default_handler(client):
    response = client.get("/logout")

    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed"}
