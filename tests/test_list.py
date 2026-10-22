import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app.db import engine
from app.models import STATUS_DRAFT

BASE = datetime(2025, 1, 1, 4, 0, tzinfo=timezone.utc)


def publish_many(make_post, count):
    # 按发布时间从早到晚创建
    return [make_post(title=f"文章{i:02d}", published_at=BASE + timedelta(days=i)) for i in range(count)]


def ids(posts) -> list[int]:
    return [post.id for post in posts]


def listed_ids(html: str) -> list[int]:
    return [int(post_id) for post_id in re.findall(r'href="/post/(\d+)/"', html)]


def articles(html: str) -> list[str]:
    return re.findall(r'<article class="post-item">(.*?)</article>', html, re.S)


def test_first_page(client, make_post):
    """Scenario: 第一页"""
    posts = publish_many(make_post, 12)

    html = client.get("/blog/").text

    assert listed_ids(html) == ids(posts[::-1][:5])
    assert "1 / 3" in html
    assert re.search(r'<a\b[^>]*href="/blog/\?page=2"[^>]*>下一页</a>', html)
    assert "上一页" not in html


def test_middle_page_has_both_links(client, make_post):
    posts = publish_many(make_post, 12)

    html = client.get("/blog/?page=2").text

    assert listed_ids(html) == ids(posts[::-1][5:10])
    assert "2 / 3" in html
    assert re.search(r'<a\b[^>]*href="/blog/\?page=1"[^>]*>上一页</a>', html)
    assert re.search(r'<a\b[^>]*href="/blog/\?page=3"[^>]*>下一页</a>', html)


@pytest.mark.parametrize("page", ["abc", "", "1.5", "1_0", " 2 ", "２"])
def test_page_not_integer(client, make_post, page):
    """Scenario: 页码不是整数"""
    posts = publish_many(make_post, 12)

    response = client.get("/blog/", params={"page": page})

    assert response.status_code == 200
    assert listed_ids(response.text) == ids(posts[::-1][:5])
    assert "1 / 3" in response.text


@pytest.mark.parametrize("page", ["99", "0", "-1", "9" * 5000], ids=["99", "0", "-1", "huge"])
def test_page_out_of_range(client, make_post, page):
    """Scenario: 页码超出范围"""
    posts = publish_many(make_post, 12)

    response = client.get("/blog/", params={"page": page})

    assert response.status_code == 200
    assert listed_ids(response.text) == ids(posts[1::-1])
    assert "3 / 3" in response.text
    assert "下一页" not in response.text


def test_comment_count(client, make_post, make_comment):
    """Scenario: 评论数"""
    commented = make_post(title="有评论的文章", published_at=BASE)
    make_post(title="没有评论的文章", published_at=BASE + timedelta(days=1))
    for _ in range(3):
        make_comment(commented)

    blocks = articles(client.get("/blog/").text)

    by_title = {re.search(r'href="/post/\d+/">([^<]*)</a>', b).group(1): b for b in blocks}
    assert "3 条评论" in by_title["有评论的文章"]
    assert "0 条评论" in by_title["没有评论的文章"]


def select_statements(client, path: str) -> list[str]:
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        assert client.get(path).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return statements


def test_comment_counts_fetched_in_one_query(client, make_post, make_comment):
    def add_posts_with_comments(count):
        for _ in range(count):
            post = make_post()
            make_comment(post)
            make_comment(post)

    add_posts_with_comments(1)
    few = select_statements(client, "/blog/")
    add_posts_with_comments(4)
    many = select_statements(client, "/blog/")

    # 查询次数与文章数无关，评论数只来自一条查询
    assert len(many) == len(few)
    assert sum("comments" in statement for statement in many) == 1


def test_guest_does_not_see_drafts(client, make_post):
    """Scenario: 访客看不到草稿"""
    make_post(title="一篇草稿", status=STATUS_DRAFT)
    published = [
        make_post(title="已发布一", published_at=BASE),
        make_post(title="已发布二", published_at=BASE + timedelta(days=1)),
    ]

    html = client.get("/blog/").text

    assert listed_ids(html) == ids(published[::-1])
    assert "草稿" not in html


def test_admin_sees_drafts(admin_client, make_post, db):
    """Scenario: 登录后看到草稿"""
    first = make_post(title="先建的草稿", status=STATUS_DRAFT)
    second = make_post(title="后建的草稿", status=STATUS_DRAFT)
    published = make_post(title="已发布")
    # 先建的草稿后保存，应排在前面
    first.updated_at = datetime(2025, 10, 21, 16, 30, tzinfo=timezone.utc)
    second.updated_at = datetime(2025, 10, 2, 2, 0, tzinfo=timezone.utc)
    db.commit()

    html = admin_client.get("/blog/").text

    section = re.search(r'<section class="drafts"[^>]*>(.*?)</section>', html, re.S)
    assert section, "没有草稿区"
    assert re.search(r"<h2\b[^>]*>草稿</h2>", section.group(1))
    links = re.findall(r'<a href="/post/(\d+)/edit">([^<]*)</a>', section.group(1))
    assert links == [(str(first.id), "先建的草稿"), (str(second.id), "后建的草稿")]
    assert "最后保存于 2025-10-22 00:30" in section.group(1)
    assert "最后保存于 2025-10-02 10:00" in section.group(1)
    assert html.index('<section class="drafts"') < html.index(f'href="/post/{published.id}/"')
    assert listed_ids(html) == [published.id]


def test_admin_without_drafts_has_no_draft_section(admin_client, make_post):
    make_post()

    assert "草稿" not in admin_client.get("/blog/").text


@pytest.mark.parametrize("body, minutes", [("字" * 1000, 3), ("一二三四五 六七八九十", 1)])
def test_list_shows_reading_time(client, make_post, body, minutes):
    """Scenario: 1000 字正文 / 极短正文（列表页显示阅读时长）"""
    make_post(body=body)

    assert f"约 {minutes} 分钟" in articles(client.get("/blog/").text)[0]


def test_list_shows_excerpt_and_date(client, make_post):
    """Scenario: 跨日的时间（列表页显示北京时间的日期）"""
    make_post(
        body="## 小节\n\n" + "长" * 200,
        published_at=datetime(2025, 10, 21, 16, 30, tzinfo=timezone.utc),
    )

    block = articles(client.get("/blog/").text)[0]

    assert "小节 " + "长" * 97 + "…" in block
    assert "##" not in block
    assert "2025-10-22" in block


def test_list_without_published_posts(client, make_post):
    make_post(status=STATUS_DRAFT)

    html = client.get("/blog/").text

    assert "还没有文章" in html
    assert 'aria-label="分页"' not in html
