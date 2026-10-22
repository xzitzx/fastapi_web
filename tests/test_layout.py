import re
from datetime import datetime, timezone

import pytest
from starlette.requests import Request

from app import rendering
from app.templating import render

FORBIDDEN = ["我的博客", "WELCOME", "Powered by", "注册", "登录", "/login"]
FONT_STACK = (
    '-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", '
    '"Microsoft YaHei", sans-serif'
)
NAV_ITEM = re.compile(
    r'<a\b[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
    r'|<form\b[^>]*action="([^"]*)"[^>]*>.*?<button\b[^>]*>(.*?)</button>',
    re.S,
)


def main_nav(html: str) -> str:
    match = re.search(r'<nav class="site-nav"[^>]*>(.*?)</nav>', html, re.S)
    assert match, "页面中没有主导航"
    return match.group(1)


def nav_items(html: str) -> list[tuple[str, str]]:
    # 按顺序返回 (文字, 目标地址)；按钮的目标地址取所在表单的 action
    return [(m[2] or m[4], m[1] or m[3]) for m in NAV_ITEM.finditer(main_nav(html))]


def test_guest_nav_has_two_links(client, make_post):
    """Scenario: 未登录时导航只有两个链接"""
    post = make_post()

    for path in ["/", "/blog/", f"/post/{post.id}/"]:
        html = client.get(path).text

        assert nav_items(html) == [("首页", "/"), ("文章", "/blog/")], path
        assert "<button" not in main_nav(html), path


def test_admin_nav(admin_client):
    """Scenario: 登录后导航"""
    html = admin_client.get("/blog/").text

    assert nav_items(html) == [
        ("首页", "/"),
        ("文章", "/blog/"),
        ("写文章", "/write"),
        ("退出", "/logout"),
    ]
    logout_form = re.search(r'<form\b[^>]*action="/logout"[^>]*>', main_nav(html)).group(0)
    assert 'method="post"' in logout_form


class NewYearInBeijing(datetime):
    # UTC 2025-12-31 16:30 即北京时间 2026-01-01 00:30
    @classmethod
    def now(cls, tz=None):
        return datetime(2025, 12, 31, 16, 30, tzinfo=timezone.utc).astimezone(tz)


def test_footer_shows_year_only(client, monkeypatch):
    """Scenario: 页脚只显示年份"""
    monkeypatch.setattr(rendering, "datetime", NewYearInBeijing)

    html = client.get("/").text

    footer = re.search(r"<footer\b[^>]*>(.*?)</footer>", html, re.S).group(1)
    assert footer.strip() == "© 2026"


def test_no_forbidden_text_for_guest(client, make_post):
    """Scenario: 不出现被禁止的文案"""
    post = make_post()

    for path in ["/", "/blog/", f"/post/{post.id}/", "/no-such-page/"]:
        html = client.get(path).text
        for text in FORBIDDEN:
            assert text not in html, (path, text)


def request_for(path: str) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "session": {"admin": True},
    }
    return Request(scope)


@pytest.mark.parametrize(
    "path, current",
    [
        ("/", ["首页"]),
        ("/blog/", ["文章"]),
        ("/post/3/", ["文章"]),
        ("/write", ["写文章"]),
        ("/post/3/edit", ["写文章"]),
        ("/login", []),
    ],
)
def test_nav_marks_current_section(path, current):
    html = render(request_for(path), "base.html").body.decode()

    assert re.findall(r"<a\b[^>]*aria-current=[^>]*>(.*?)</a>", main_nav(html)) == current


def test_hero_focus_outline_is_white(client):
    # 视频上的强调色焦点框对比度不足，必须改成白色
    css = client.get("/static/css/site.css").text

    assert re.search(r"\.has-hero[^{]*:focus-visible[^{]*\{[^}]*outline-color:\s*#FFFFFF", css)


def test_site_css_uses_design_values(client):
    assert '<link rel="stylesheet" href="/static/css/site.css">' in client.get("/blog/").text

    response = client.get("/static/css/site.css")

    assert response.status_code == 200
    for value in [
        "#FFFFFF",
        "#1C1C1C",
        "#6B6B6B",
        "#EEEEEE",
        "#0F766E",
        "#8F8F8F",
        "#F6F6F6",
        "max-width: 720px",
        "min-height: 44px",
        "white-space: pre-line",
        FONT_STACK,
    ]:
        assert value in response.text, value
