import re
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models import STATUS_DRAFT, Comment
from tests.conftest import csrf_from


def comment_count(db) -> int:
    return db.scalar(select(func.count()).select_from(Comment))


def submit(client, post_id, token, name="小李", body="写得好"):
    data = {"name": name, "body": body}
    if token is not None:
        data["csrf_token"] = token
    return client.post(f"/post/{post_id}/", data=data, follow_redirects=False)


def page_token(client, post) -> str:
    return csrf_from(client.get(f"/post/{post.id}/").text)


def comment_form(html: str) -> str:
    match = re.search(r'<form\b[^>]*class="comment-form"[^>]*>.*?</form>', html, re.S)
    assert match, "没有评论表单"
    return match.group(0)


# 评论展示


def test_two_comments(client, make_post, make_comment, db):
    """Scenario: 两条评论"""
    post = make_post()
    # 先插入的一条时间更晚，确认按评论时间而不是 id 排序
    later = make_comment(post, name="后来者", body="晚一些的评论")
    earlier = make_comment(post, name="先到者", body="早一些的评论")
    later.created_at = datetime(2025, 10, 22, 2, 0, tzinfo=timezone.utc)
    earlier.created_at = datetime(2025, 10, 21, 16, 30, tzinfo=timezone.utc)
    db.commit()

    html = client.get(f"/post/{post.id}/").text

    assert re.search(r'<h2\b[^>]*>评论 <span class="comments-count">2</span></h2>', html)
    assert html.index("早一些的评论") < html.index("晚一些的评论")
    assert '<span class="comment-name">先到者</span>' in html
    assert '<span class="comment-time">2025-10-22 00:30</span>' in html
    assert '<span class="comment-time">2025-10-22 10:00</span>' in html
    assert "还没有评论" not in html


def test_multiline_comment(client, make_post, make_comment):
    """Scenario: 多行内容"""
    post = make_post()
    make_comment(post, body="第一行\n第二行")

    html = client.get(f"/post/{post.id}/").text

    # 换行原样输出，由 CSS white-space: pre-line 显示为两行
    assert '<p class="comment-body">第一行\n第二行</p>' in html
    assert "<br" not in html
    css = client.get("/static/css/site.css").text
    assert re.search(r"\.comment-body \{[^}]*white-space: pre-line", css)


def test_no_comments(client, make_post):
    post = make_post()

    html = client.get(f"/post/{post.id}/").text

    assert '<span class="comments-count">0</span>' in html
    assert "还没有评论" in html


# 发表评论


def test_comment_form_fields(client, make_post):
    post = make_post()

    form = comment_form(client.get(f"/post/{post.id}/").text)

    assert 'method="post"' in form
    assert re.search(rf'action="/post/{post.id}/(#[^"]*)?"', form)
    assert "发表评论" in form
    assert re.search(r'<input[^>]*type="hidden"[^>]*name="csrf_token"', form)
    assert re.search(r'<label for="comment-name">昵称</label>', form)
    assert re.search(r'<input[^>]*id="comment-name"[^>]*name="name"', form)
    assert re.search(r'<label for="comment-body">内容</label>', form)
    assert re.search(r'<textarea[^>]*id="comment-body"[^>]*name="body"', form)
    assert re.search(r"<button\b[^>]*>提交评论</button>", form)


def test_submit_comment(client, make_post, db):
    """Scenario: 提交成功"""
    post = make_post()
    token = page_token(client, post)

    response = submit(client, post.id, token, name="小李", body="写得好")

    assert response.status_code == 303
    assert response.headers["location"] == f"/post/{post.id}/"
    saved = db.scalars(select(Comment)).all()
    assert [(c.post_id, c.name, c.body) for c in saved] == [(post.id, "小李", "写得好")]
    html = client.get(f"/post/{post.id}/").text
    assert '<span class="comment-name">小李</span>' in html
    assert '<p class="comment-body">写得好</p>' in html
    assert '<span class="comments-count">1</span>' in html


def test_submit_strips_and_normalizes_newlines(client, make_post, db):
    post = make_post()
    token = page_token(client, post)

    response = submit(client, post.id, token, name="  小李　", body="\r\n第一行\r\n第二行  \r\n")

    assert response.status_code == 303
    saved = db.scalar(select(Comment))
    assert (saved.name, saved.body) == ("小李", "第一行\n第二行")


@pytest.mark.parametrize("with_token", [True, False], ids=["valid-token", "no-token"])
def test_comment_on_missing_post(client, db, with_token):
    """Scenario: 文章不存在"""
    token = csrf_from(client.get("/login").text) if with_token else None

    response = submit(client, 999, token)

    assert response.status_code == 404
    assert comment_count(db) == 0


def test_comment_on_huge_post_id(client, db):
    token = csrf_from(client.get("/login").text)

    response = submit(client, 99999999999999999999, token)

    assert response.status_code == 404
    assert comment_count(db) == 0


@pytest.mark.parametrize("who", ["guest", "admin"])
@pytest.mark.parametrize("with_token", [True, False], ids=["valid-token", "no-token"])
def test_comment_on_draft(client, admin_client, make_post, db, who, with_token):
    """Scenario: 向草稿提交评论"""
    draft = make_post(status=STATUS_DRAFT)
    c = admin_client if who == "admin" else client
    token = csrf_from(c.get("/blog/" if who == "admin" else "/login").text) if with_token else None

    response = submit(c, draft.id, token)

    assert response.status_code == 404
    assert comment_count(db) == 0


# 评论校验


def test_blank_name(client, make_post, db):
    """Scenario: 昵称为空"""
    post = make_post()
    token = page_token(client, post)

    response = submit(client, post.id, token, name="   ", body="写得好")

    assert response.status_code == 400
    assert re.search(r'<p class="form-error"[^>]*>昵称不能为空</p>', response.text)
    assert comment_count(db) == 0


def test_body_too_long(client, make_post, db):
    """Scenario: 内容过长"""
    post = make_post(title="原文标题")
    token = page_token(client, post)
    body = "字" * 2001

    response = submit(client, post.id, token, name="小李", body=body)

    assert response.status_code == 400
    assert "原文标题" in response.text
    assert re.search(r'<p class="form-error"[^>]*>内容过长，最多 2000 个字符</p>', response.text)
    form = comment_form(response.text)
    assert re.search(r'<input[^>]*name="name"[^>]*value="小李"', form)
    assert re.search(rf'<textarea[^>]*name="body"[^>]*>{body}</textarea>', form)
    assert comment_count(db) == 0
    # 重新渲染的表单仍可提交
    assert csrf_from(form) == token


@pytest.mark.parametrize(
    "name, body, errors",
    [
        ("字" * 81, "写得好", ["昵称不能超过 80 个字符"]),
        ("小李", " \n ", ["内容不能为空"]),
        ("", "", ["昵称不能为空", "内容不能为空"]),
    ],
    ids=["name-too-long", "blank-body", "both-blank"],
)
def test_invalid_comment(client, make_post, db, name, body, errors):
    post = make_post()
    token = page_token(client, post)

    response = submit(client, post.id, token, name=name, body=body)

    assert response.status_code == 400
    assert re.findall(r'<p class="form-error"[^>]*>(.*?)</p>', response.text) == errors
    assert comment_count(db) == 0


def test_length_limits_are_inclusive(client, make_post, db):
    post = make_post()
    token = page_token(client, post)

    response = submit(client, post.id, token, name=" " + "名" * 80 + " ", body="字" * 2000 + "\n")

    assert response.status_code == 303
    assert comment_count(db) == 1


@pytest.mark.parametrize(
    "data, files",
    [
        ({"name": "小李"}, None),
        ({"body": "写得好"}, None),
        ({"body": "写得好"}, {"name": ("a.txt", b"x", "text/plain")}),
    ],
    ids=["missing-body", "missing-name", "name-as-file"],
)
def test_malformed_comment_request(client, make_post, db, data, files):
    post = make_post()
    data = {**data, "csrf_token": page_token(client, post)}

    response = client.post(f"/post/{post.id}/", data=data, files=files, follow_redirects=False)

    assert response.status_code == 400
    assert comment_count(db) == 0


# 已解析表单中的上传文件要关闭，否则出现 ResourceWarning
@pytest.mark.filterwarnings("error")
@pytest.mark.parametrize("body, status", [("写得好", 303), ("", 400)], ids=["saved", "invalid"])
def test_multipart_comment_closes_files(client, make_post, body, status):
    post = make_post()
    data = {"csrf_token": page_token(client, post), "name": "小李", "body": body}
    files = {"extra": ("a.bin", b"x" * (2 * 1024 * 1024), "application/octet-stream")}

    response = client.post(f"/post/{post.id}/", data=data, files=files, follow_redirects=False)

    assert response.status_code == status


# CSRF 防护


def test_comment_without_token(client, make_post, db):
    """Scenario: 缺少令牌"""
    post = make_post()
    page_token(client, post)

    response = submit(client, post.id, None)

    assert response.status_code == 403
    assert comment_count(db) == 0


def test_comment_with_wrong_token(client, make_post, db):
    """Scenario: 令牌不匹配"""
    post = make_post()
    token = page_token(client, post)

    response = submit(client, post.id, token + "x")

    assert response.status_code == 403
    assert comment_count(db) == 0


def test_csrf_checked_before_validation(client, make_post, db):
    post = make_post()
    page_token(client, post)

    response = submit(client, post.id, "wrong", name="", body="")

    assert response.status_code == 403


# 内容转义


def test_script_tag_is_escaped(client, make_post):
    """Scenario: 提交脚本标签"""
    post = make_post()
    token = page_token(client, post)

    submit(client, post.id, token, name="<b>小李</b>", body="<script>alert(1)</script>")
    html = client.get(f"/post/{post.id}/").text

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;b&gt;小李&lt;/b&gt;" in html
    assert "<b>小李</b>" not in html


def test_rerendered_form_is_escaped(client, make_post):
    post = make_post()
    token = page_token(client, post)

    body = "</textarea><script>y()</script>" + "长" * 2000
    response = submit(client, post.id, token, name='"><script>x()</script>', body=body)

    assert response.status_code == 400
    assert "<script>x()</script>" not in response.text
    assert "&#34;&gt;&lt;script&gt;x()&lt;/script&gt;" in response.text
    assert "</textarea><script>y()</script>" not in response.text
    assert "&lt;/textarea&gt;&lt;script&gt;y()&lt;/script&gt;" in response.text


# 删除评论


def test_delete_comment(admin_client, make_post, make_comment, db):
    """Scenario: 删除垃圾评论"""
    post = make_post()
    spam = make_comment(post, body="垃圾广告")
    make_comment(post, body="正常评论")
    token = page_token(admin_client, post)

    response = admin_client.post(
        f"/comments/{spam.id}/delete", data={"csrf_token": token}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/post/{post.id}/"
    assert db.scalar(select(Comment).where(Comment.id == spam.id)) is None
    html = admin_client.get(f"/post/{post.id}/").text
    assert "垃圾广告" not in html
    assert "正常评论" in html
    assert '<span class="comments-count">1</span>' in html


@pytest.mark.parametrize("comment_id", ["999", "99999999999999999999", "-99999999999999999999"])
def test_delete_missing_comment(admin_client, comment_id):
    """Scenario: 评论不存在"""
    token = csrf_from(admin_client.get("/blog/").text)

    response = admin_client.post(
        f"/comments/{comment_id}/delete", data={"csrf_token": token}, follow_redirects=False
    )

    assert response.status_code == 404


@pytest.mark.filterwarnings("error")
def test_delete_comment_closes_files(admin_client, make_post, make_comment):
    post = make_post()
    comment = make_comment(post)
    token = page_token(admin_client, post)
    files = {"extra": ("a.bin", b"x" * (2 * 1024 * 1024), "application/octet-stream")}

    response = admin_client.post(
        f"/comments/{comment.id}/delete",
        data={"csrf_token": token},
        files=files,
        follow_redirects=False,
    )

    assert response.status_code == 303


def test_delete_comment_requires_csrf(admin_client, make_post, make_comment, db):
    post = make_post()
    comment = make_comment(post)

    response = admin_client.post(f"/comments/{comment.id}/delete", follow_redirects=False)

    assert response.status_code == 403
    assert comment_count(db) == 1


def test_guest_cannot_delete_comment(client, make_post, make_comment, db):
    post = make_post()
    comment = make_comment(post)
    token = page_token(client, post)

    response = client.post(
        f"/comments/{comment.id}/delete", data={"csrf_token": token}, follow_redirects=False
    )

    assert response.status_code == 403
    assert comment_count(db) == 1
