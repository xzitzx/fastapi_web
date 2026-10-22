import re
from datetime import datetime, timedelta, timezone

import pytest

from app.models import STATUS_DRAFT

T = datetime(2025, 10, 1, 4, 0, tzinfo=timezone.utc)


def nav_block(html: str, side: str) -> str:
    match = re.search(rf'<div class="post-nav-{side}">(.*?)</div>', html, re.S)
    assert match, f"没有 post-nav-{side}"
    return match.group(1)


def test_markdown_rendering(client, make_post):
    """Scenario: Markdown 渲染"""
    body = (
        "## 小节\n\n```python\nprint('hi')\n```\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\n正文[^1]\n\n[^1]: 脚注内容\n"
    )
    post = make_post(body=body)

    html = client.get(f"/post/{post.id}/").text

    assert re.search(r'<h2 id="[^"]+">小节</h2>', html)
    assert re.search(r'<div class="codehilite"><pre>.*?print', html, re.S)
    assert "<table>" in html
    assert 'class="footnote"' in html
    assert '<link rel="stylesheet" href="/static/css/code.css">' in html
    css = client.get("/static/css/code.css")
    assert css.status_code == 200
    assert ".codehilite" in css.text


def test_previous_and_next(client, make_post):
    """Scenario: 上一篇和下一篇"""
    a = make_post(title="A", published_at=T)
    b = make_post(title="B", published_at=T + timedelta(days=1))
    c = make_post(title="C", published_at=T + timedelta(days=3))
    make_post(title="D", status=STATUS_DRAFT, published_at=T + timedelta(days=2))

    html = client.get(f"/post/{b.id}/").text

    prev, nxt = nav_block(html, "prev"), nav_block(html, "next")
    assert "上一篇" in prev and f'href="/post/{a.id}/"' in prev
    assert "下一篇" in nxt and f'href="/post/{c.id}/"' in nxt


def test_previous_skips_unpublished(client, make_post):
    a = make_post(title="A", published_at=T)
    make_post(title="E", status=STATUS_DRAFT, published_at=T + timedelta(hours=12))
    b = make_post(title="B", published_at=T + timedelta(days=1))

    html = client.get(f"/post/{b.id}/").text

    assert f'href="/post/{a.id}/"' in nav_block(html, "prev")


@pytest.mark.parametrize("post_id", ["99999999999999999999", "-99999999999999999999", "0"])
def test_huge_post_id_is_404(client, post_id):
    response = client.get(f"/post/{post_id}/")

    assert response.status_code == 404
    assert "页面不存在" in response.text


def test_latest_post(client, make_post):
    """Scenario: 最新一篇"""
    older = make_post(title="较早", published_at=T)
    latest = make_post(title="最新", published_at=T + timedelta(days=1))

    html = client.get(f"/post/{latest.id}/").text

    nxt = nav_block(html, "next")
    assert "没有了" in nxt
    assert "<a" not in nxt
    assert f'href="/post/{older.id}/"' in nav_block(html, "prev")


def test_oldest_post_has_no_previous(client, make_post):
    oldest = make_post(title="最早", published_at=T)
    newer = make_post(title="较新", published_at=T + timedelta(days=1))

    html = client.get(f"/post/{oldest.id}/").text

    prev = nav_block(html, "prev")
    assert "没有了" in prev
    assert "<a" not in prev
    assert f'href="/post/{newer.id}/"' in nav_block(html, "next")


def test_same_publish_time_ordered_by_id(client, make_post):
    first, second, third = (make_post(title=t, published_at=T) for t in "一二三")

    html = client.get(f"/post/{second.id}/").text

    assert f'href="/post/{first.id}/"' in nav_block(html, "prev")
    assert f'href="/post/{third.id}/"' in nav_block(html, "next")


def test_guest_opens_draft(client, make_post):
    """Scenario: 访客打开草稿"""
    draft = make_post(title="草稿标题", status=STATUS_DRAFT)

    response = client.get(f"/post/{draft.id}/")

    assert response.status_code == 404
    assert "草稿标题" not in response.text


def test_admin_opens_draft(admin_client, make_post):
    """Scenario: 站长打开草稿"""
    draft = make_post(title="草稿标题", status=STATUS_DRAFT)

    response = admin_client.get(f"/post/{draft.id}/")

    assert response.status_code == 200
    assert "草稿标题" in response.text
    assert '<span class="badge">草稿</span>' in response.text
    assert "最后保存于" in response.text
    assert "发表评论" not in response.text
    assert 'name="body"' not in response.text
    # 对照：同一位站长打开已发布文章时有评论表单
    published = admin_client.get(f"/post/{make_post().id}/").text
    assert "发表评论" in published
    assert 'name="body"' in published


def test_admin_opens_draft_with_comments(admin_client, make_post, make_comment):
    # 发布过又转为草稿的文章：评论照常列出，但不能再发表
    draft = make_post(status=STATUS_DRAFT)
    comment = make_comment(draft, body="转草稿前的评论")

    html = admin_client.get(f"/post/{draft.id}/").text

    assert '<p class="comment-body">转草稿前的评论</p>' in html
    assert f'action="/comments/{comment.id}/delete"' in html
    assert "发表评论" not in html
    assert 'name="body"' not in html


def test_admin_sees_management_buttons(admin_client, make_post, make_comment):
    """Scenario: 登录后显示管理按钮"""
    post = make_post()
    comments = [make_comment(post, body="第一条"), make_comment(post, body="第二条")]

    html = admin_client.get(f"/post/{post.id}/").text

    assert re.search(rf'<a\b[^>]*href="/post/{post.id}/edit"[^>]*>编辑</a>', html)
    form = re.search(rf'(<form\b[^>]*action="/post/{post.id}/delete"[^>]*>)(.*?)</form>', html, re.S)
    assert form, "没有删除文章的表单"
    assert 'method="post"' in form.group(1)
    assert "return confirm(" in form.group(1)
    assert 'name="csrf_token"' in form.group(2)
    assert re.search(r"<button\b[^>]*>删除</button>", form.group(2))
    for comment in comments:
        form = re.search(
            rf'(<form\b[^>]*action="/comments/{comment.id}/delete"[^>]*>)(.*?)</form>', html, re.S
        )
        assert form, f"没有删除评论 {comment.id} 的表单"
        assert 'method="post"' in form.group(1)
        assert "onsubmit=\"return confirm('确定删除这条评论？')\"" in form.group(1)
        assert 'name="csrf_token"' in form.group(2)
        assert re.search(r"<button\b[^>]*>删除</button>", form.group(2))


def test_guest_sees_no_management_buttons(client, make_post, make_comment):
    """Scenario: 访客看不到管理按钮"""
    post = make_post()
    make_comment(post, body="一条评论")

    html = client.get(f"/post/{post.id}/").text

    # 评论本身照常显示，只是没有删除按钮
    assert '<p class="comment-body">一条评论</p>' in html
    assert "/edit" not in html
    assert "/delete" not in html
    assert "编辑" not in html


def test_detail_meta(client, make_post):
    """Scenario: 跨日的时间（详情页显示北京时间的日期）"""
    post = make_post(
        title="一篇文章",
        body="字" * 1000,
        published_at=datetime(2025, 10, 21, 16, 30, tzinfo=timezone.utc),
    )

    html = client.get(f"/post/{post.id}/").text

    assert re.search(r"<h1\b[^>]*>一篇文章</h1>", html)
    assert "2025年10月22日" in html
    assert "约 3 分钟" in html
    assert re.search(r'<a\b[^>]*href="/blog/"[^>]*>返回文章列表</a>', html)


def test_cover_shown_when_present(client, make_post, db):
    with_cover = make_post()
    with_cover.cover = "covers/2025/10/abc.jpg"
    db.commit()
    without_cover = make_post()

    assert 'src="/media/covers/2025/10/abc.jpg"' in client.get(f"/post/{with_cover.id}/").text
    assert "/media/" not in client.get(f"/post/{without_cover.id}/").text


def test_non_integer_post_id_is_404(client):
    response = client.get("/post/abc/")

    assert response.status_code == 404
    assert "页面不存在" in response.text
