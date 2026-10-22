import gc
import io
import re
from datetime import datetime, timezone

import pytest
from markupsafe import escape
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.images import MAX_BYTES, media_url
from app.models import STATUS_DRAFT, STATUS_PUBLISHED, Comment, Post
from app.rendering import to_local
from tests.conftest import csrf_from

# 未关闭的上传临时文件会产生 ResourceWarning，测试末尾 gc.collect() 让它在本测试内暴露
pytestmark = pytest.mark.filterwarnings("error")

ACCEPT = "image/jpeg,image/png,image/gif,image/webp"
UTC = timezone.utc


def image(fmt="JPEG", color="red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, fmt)
    return buffer.getvalue()


def save(client, url="/write", title="标题", body="正文", action="draft", files=None, **fields):
    token = csrf_from(client.get("/write").text)
    data = {"csrf_token": token, "title": title, "body": body, "action": action, **fields}
    return client.post(url, data=data, files=files, follow_redirects=False)


def browser_save(client, url, cover_filename, cover_data, **fields):
    # 浏览器在未选文件时也会提交 cover，文件名为空；httpx 无法构造这种请求，手工拼 multipart
    boundary = "----FormBoundaryTest"
    fields = {"csrf_token": csrf_from(client.get("/write").text), **fields}
    body = b"".join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, value in fields.items()
    )
    body += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="cover"; filename="{cover_filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    body += cover_data + f"\r\n--{boundary}--\r\n".encode()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    return client.post(url, content=body, headers=headers, follow_redirects=False)


def post_count(db) -> int:
    return db.scalar(select(func.count()).select_from(Post))


def only_post(db) -> Post:
    return db.scalars(select(Post)).one()


def saved_files() -> list:
    return [path for path in settings.media_root.rglob("*") if path.is_file()]


def input_tag(html: str, name: str) -> str:
    match = re.search(rf'<input\b[^>]*\bname="{name}"[^>]*>', html)
    assert match, f"页面中没有 {name} 输入框"
    return match.group(0)


def element(html: str, element_id: str) -> str:
    match = re.search(rf'<\w+\b[^>]*\bid="{element_id}"[^>]*>', html)
    assert match, f"页面中没有 #{element_id}"
    return match.group(0)


def textarea(html: str) -> str:
    match = re.search(r'<textarea\b[^>]*\bname="body"[^>]*>(.*?)</textarea>', html, re.S)
    assert match, "页面中没有正文框"
    # HTML 解析器会丢弃开始标签后的第一个换行，模板在那里多放一个，正文才不会少换行
    assert match.group(1).startswith("\n")
    return match.group(1)[1:]


def buttons(html: str) -> list[tuple[str, str]]:
    pattern = r'<button\b[^>]*\bname="action"[^>]*\bvalue="([^"]*)"[^>]*>([^<]*)</button>'
    return re.findall(pattern, html)


def errors(html: str) -> list[str]:
    return re.findall(r'<p class="form-error" role="alert">([^<]*)</p>', html)


def cover_img(html: str) -> list[str]:
    return re.findall(r'<img class="post-cover" src="([^"]*)"', html)


# 写作页


def test_new_page(admin_client):
    """Scenario: 新建页"""
    response = admin_client.get("/write")

    assert response.status_code == 200
    html = response.text
    assert 'value=""' in input_tag(html, "title")
    assert textarea(html) == ""
    assert buttons(html) == [("draft", "保存草稿"), ("publish", "发布")]
    assert "移除封面" not in html
    assert "最后保存于" not in html


def test_write_form_elements(admin_client):
    html = admin_client.get("/write").text

    form = re.search(r"<form\b[^>]*\benctype=[^>]*>", html).group(0)
    assert 'method="post"' in form
    assert 'enctype="multipart/form-data"' in form
    assert csrf_from(html)
    assert 'type="text"' in input_tag(html, "title")
    cover = input_tag(html, "cover")
    assert 'type="file"' in cover
    assert f'accept="{ACCEPT}"' in cover
    assert 'id="post-body"' in re.search(r'<textarea\b[^>]*name="body"[^>]*>', html).group(0)
    for text in [
        ">标题</label>",
        ">封面图（可选）</label>",
        ">正文</label>",
        "JPG、PNG、GIF、WebP，不超过 10MB",
        '支持 Markdown。图片可以点"插入图片"上传，也可以直接粘贴到正文里。',
    ]:
        assert text in html, text

    assert " hidden" in element(html, "preview")
    assert re.search(
        r'<button\b[^>]*data-mode="edit"[^>]*aria-pressed="true"[^>]*>编辑</button>', html
    )
    assert re.search(
        r'<button\b[^>]*data-mode="preview"[^>]*aria-pressed="false"[^>]*>预览</button>', html
    )
    insert = re.search(r'<button\b[^>]*id="insert-image"[^>]*>(.*?)</button>', html, re.S)
    assert insert and 'type="button"' in insert.group(0) and "插入图片" in insert.group(1)
    image_file = element(html, "image-file")
    assert 'type="file"' in image_file
    assert f'accept="{ACCEPT}"' in image_file
    assert " hidden" in image_file
    assert "name=" not in image_file
    assert 'aria-live="polite"' in element(html, "editor-message")
    assert '<link rel="stylesheet" href="/static/css/code.css">' in html
    assert re.search(r'<script src="/static/js/write.js"></script>\s*</body>', html)
    assert admin_client.get("/static/js/write.js").status_code == 200


def test_published_edit_page(admin_client, make_post, db):
    """Scenario: 已发布文章的编辑页"""
    body = "第一段 <b>粗体</b> & 'x'\n\n```python\nprint(\"hi\")\n```"
    post = make_post(title='原标题 "引号" <b>', body=body)
    post.updated_at = datetime(2025, 10, 21, 2, 24, tzinfo=UTC)
    db.commit()

    response = admin_client.get(f"/post/{post.id}/edit")

    assert response.status_code == 200
    html = response.text
    assert f'value="{escape(post.title)}"' in input_tag(html, "title")
    assert textarea(html) == escape(body)
    assert buttons(html) == [("publish", "更新"), ("draft", "转为草稿")]
    assert "已发布 · 最后保存于 2025-10-21 10:24" in html


def test_draft_edit_page(admin_client, make_post, db):
    post = make_post(title="草稿标题", body="", status=STATUS_DRAFT)
    post.updated_at = datetime(2025, 10, 21, 16, 5, tzinfo=UTC)
    db.commit()

    html = admin_client.get(f"/post/{post.id}/edit").text

    assert 'value="草稿标题"' in input_tag(html, "title")
    assert buttons(html) == [("draft", "保存草稿"), ("publish", "发布")]
    assert "草稿 · 最后保存于 2025-10-22 00:05" in html


def test_edit_page_shows_current_cover(admin_client, make_post, db):
    post = make_post()
    post.cover = "covers/2025/10/abc.jpg"
    db.commit()

    html = admin_client.get(f"/post/{post.id}/edit").text

    assert 'src="/media/covers/2025/10/abc.jpg"' in html
    checkbox = input_tag(html, "remove_cover")
    assert 'type="checkbox"' in checkbox
    assert 'value="1"' in checkbox
    assert "checked" not in checkbox
    assert "移除封面" in html


def test_body_with_leading_newlines_round_trips(admin_client, make_post):
    body = "\n\n第一段"
    post = make_post(body=body)

    html = admin_client.get(f"/post/{post.id}/edit").text

    assert textarea(html) == body


def test_edit_missing_post(admin_client, db):
    """Scenario: 编辑不存在的文章"""
    assert admin_client.get("/post/999999/edit").status_code == 404

    files = {"cover": ("a.jpg", image(), "image/jpeg")}
    response = save(admin_client, "/post/999999/edit", files=files)

    assert response.status_code == 404
    assert post_count(db) == 0
    assert saved_files() == []
    gc.collect()


@pytest.mark.parametrize("post_id", ["0", "-1", str(2**63), "abc"])
def test_edit_invalid_post_id(admin_client, post_id):
    assert admin_client.get(f"/post/{post_id}/edit").status_code == 404
    assert save(admin_client, f"/post/{post_id}/edit").status_code == 404


# 保存草稿


def test_create_draft(admin_client, client, db):
    """Scenario: 新建草稿"""
    response = save(admin_client, title="未完成", body="", action="draft")

    post = only_post(db)
    assert response.status_code == 303
    assert response.headers["location"] == f"/post/{post.id}/edit"
    assert (post.title, post.body, post.status) == ("未完成", "", STATUS_DRAFT)
    assert post.published_at is None
    assert "未完成" not in client.get("/").text
    assert "未完成" not in client.get("/blog/").text


def test_title_is_stripped(admin_client, db):
    save(admin_client, title="  \t前后有空白 \n", body="  正文保持原样  ")

    post = only_post(db)
    assert post.title == "前后有空白"
    assert post.body == "  正文保持原样  "


def test_unpublish(admin_client, client, make_post, db):
    """Scenario: 已发布文章转为草稿"""
    post = make_post(title="上线文章", body="正文")
    published_at = post.published_at

    response = save(admin_client, f"/post/{post.id}/edit", title="上线文章", body="正文", action="draft")

    assert response.status_code == 303
    assert response.headers["location"] == f"/post/{post.id}/edit"
    db.refresh(post)
    assert post.status == STATUS_DRAFT
    assert to_local(post.published_at) == to_local(published_at)
    assert client.get(f"/post/{post.id}/").status_code == 404


def test_edit_draft_updates_content(admin_client, make_post, db):
    post = make_post(title="旧标题", body="旧正文", status=STATUS_DRAFT)

    response = save(admin_client, f"/post/{post.id}/edit", title="新标题", body="", action="draft")

    assert response.status_code == 303
    db.refresh(post)
    assert (post.title, post.body, post.status) == ("新标题", "", STATUS_DRAFT)
    assert post_count(db) == 1


# 发布


def test_publish_new_post(admin_client, client, make_post, db):
    """Scenario: 直接发布"""
    older = make_post(title="旧文章", published_at=datetime(2025, 1, 1, tzinfo=UTC))

    response = save(admin_client, title="新文章", body="新正文", action="publish")

    post = db.scalar(select(Post).where(Post.title == "新文章"))
    assert response.status_code == 303
    assert response.headers["location"] == f"/post/{post.id}/"
    assert post.status == STATUS_PUBLISHED
    assert post.published_at is not None
    html = client.get("/blog/").text
    listed = re.findall(r'<article class="post-item">\s*<h2><a href="/post/(\d+)/">', html)
    assert listed == [str(post.id), str(older.id)]


def test_publish_draft(admin_client, make_post, db):
    """Scenario: 草稿转为发布"""
    post = make_post(status=STATUS_DRAFT)
    before = datetime.now(UTC)

    response = save(admin_client, f"/post/{post.id}/edit", action="publish")

    after = datetime.now(UTC)
    assert response.status_code == 303
    assert response.headers["location"] == f"/post/{post.id}/"
    db.refresh(post)
    assert post.status == STATUS_PUBLISHED
    assert before <= to_local(post.published_at) <= after


def test_republish_keeps_published_at(admin_client, make_post, db):
    """Scenario: 重新发布保留原发布时间"""
    post = make_post()
    t1 = datetime(2025, 3, 1, 8, 0, tzinfo=UTC)
    post.published_at = t1
    db.commit()
    url = f"/post/{post.id}/edit"

    assert save(admin_client, url, action="draft").status_code == 303
    assert save(admin_client, url, action="publish").status_code == 303
    # 已发布文章点"更新"同样不改发布时间
    assert save(admin_client, url, title="改过的标题", action="publish").status_code == 303

    db.refresh(post)
    assert post.status == STATUS_PUBLISHED
    assert post.title == "改过的标题"
    assert to_local(post.published_at) == to_local(t1)


def test_every_save_updates_updated_at(admin_client, make_post, db):
    post = make_post(title="标题", body="正文")
    old = datetime(2025, 1, 1, tzinfo=UTC)
    post.updated_at = old
    db.commit()

    # 内容没有任何变化也算一次保存
    response = save(admin_client, f"/post/{post.id}/edit", title="标题", body="正文", action="publish")

    assert response.status_code == 303
    db.refresh(post)
    assert to_local(post.updated_at) > to_local(old)


def test_publish_with_blank_body(admin_client, db):
    """Scenario: 发布时正文为空"""
    response = save(admin_client, title="有标题", body=" \r\n\t ", action="publish")

    assert response.status_code == 400
    assert errors(response.text) == ["正文不能为空"]
    assert 'value="有标题"' in input_tag(response.text, "title")
    assert post_count(db) == 0


def test_publish_existing_with_blank_body_keeps_post(admin_client, make_post, db):
    post = make_post(title="原标题", body="原正文", status=STATUS_DRAFT)
    post.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
    db.commit()

    url = f"/post/{post.id}/edit"
    response = save(admin_client, url, title="新标题", body="   ", action="publish")

    assert response.status_code == 400
    assert errors(response.text) == ["正文不能为空"]
    db.refresh(post)
    assert (post.title, post.body, post.status) == ("原标题", "原正文", STATUS_DRAFT)
    assert post.published_at is None
    assert to_local(post.updated_at) == to_local(datetime(2025, 1, 1, tzinfo=UTC))


# 校验失败时保留输入


def test_blank_title(admin_client, db):
    """Scenario: 标题为空"""
    response = save(admin_client, title="   ", body="一段正文\n<第二行>", action="draft")

    assert response.status_code == 400
    assert errors(response.text) == ["标题不能为空"]
    assert textarea(response.text) == "一段正文\n&lt;第二行&gt;"
    assert buttons(response.text) == [("draft", "保存草稿"), ("publish", "发布")]
    assert post_count(db) == 0


def test_title_too_long(admin_client, db):
    """Scenario: 标题过长"""
    title = "长" * 201

    response = save(admin_client, title=title, body="正文", action="publish")

    assert response.status_code == 400
    assert errors(response.text) == ["标题过长，最多 200 个字符"]
    assert f'value="{title}"' in input_tag(response.text, "title")
    assert post_count(db) == 0


def test_title_of_200_characters_accepted(admin_client, db):
    response = save(admin_client, title="长" * 200)

    assert response.status_code == 303
    assert only_post(db).title == "长" * 200


def test_blank_title_and_body_on_publish(admin_client, db):
    response = save(admin_client, title="", body="", action="publish")

    assert response.status_code == 400
    assert errors(response.text) == ["标题不能为空", "正文不能为空"]


def test_failed_edit_keeps_post_and_page_state(admin_client, make_post, db):
    post = make_post(title="原标题", body="原正文")
    post.updated_at = datetime(2025, 10, 21, 2, 24, tzinfo=UTC)
    db.commit()

    response = save(admin_client, f"/post/{post.id}/edit", title="", body="改过的正文", action="publish")

    assert response.status_code == 400
    assert errors(response.text) == ["标题不能为空"]
    assert textarea(response.text) == "改过的正文"
    assert buttons(response.text) == [("publish", "更新"), ("draft", "转为草稿")]
    assert "已发布 · 最后保存于 2025-10-21 10:24" in response.text
    db.refresh(post)
    assert (post.title, post.body, post.status) == ("原标题", "原正文", STATUS_PUBLISHED)


def test_failed_edit_keeps_remove_cover_checked(admin_client, make_post, db):
    post = make_post()
    post.cover = "covers/2025/10/abc.jpg"
    db.commit()

    response = save(admin_client, f"/post/{post.id}/edit", title="", remove_cover="1")

    assert response.status_code == 400
    assert "checked" in input_tag(response.text, "remove_cover")
    db.refresh(post)
    assert post.cover == "covers/2025/10/abc.jpg"


def test_failed_save_with_cover_asks_to_reselect(admin_client, db):
    files = {"cover": ("a.jpg", image(), "image/jpeg")}

    response = save(admin_client, title="", body="正文", files=files)

    assert response.status_code == 400
    assert errors(response.text) == ["标题不能为空", "封面图需要重新选择"]
    assert post_count(db) == 0
    assert saved_files() == []
    gc.collect()


@pytest.mark.parametrize(
    "data",
    [{}, {"title": "标题", "body": "正文"}, {"title": "标题", "body": "正文", "action": "delete"}],
    ids=["no-fields", "no-action", "bad-action"],
)
def test_malformed_submission_rejected(admin_client, db, data):
    token = csrf_from(admin_client.get("/write").text)

    form = {"csrf_token": token, **data}
    response = admin_client.post("/write", data=form, follow_redirects=False)

    assert response.status_code == 400
    assert post_count(db) == 0


# 封面图


def test_upload_cover(admin_client, client, db):
    """Scenario: 上传封面"""
    files = {"cover": ("photo.jpg", image(), "image/jpeg")}

    response = save(admin_client, title="有封面", body="正文", action="publish", files=files)

    assert response.status_code == 303
    post = only_post(db)
    assert re.fullmatch(r"covers/\d{4}/\d{2}/[0-9a-f]{32}\.jpg", post.cover)
    assert cover_img(client.get(f"/post/{post.id}/").text) == [media_url(post.cover)]
    cover = client.get(media_url(post.cover))
    assert cover.status_code == 200
    assert cover.headers["content-type"] == "image/jpeg"
    gc.collect()


def test_replace_cover(admin_client, client, db):
    """Scenario: 替换封面"""
    save(admin_client, action="publish", files={"cover": ("a.jpg", image(), "image/jpeg")})
    post = only_post(db)
    old_path = settings.media_root / post.cover

    response = save(
        admin_client,
        f"/post/{post.id}/edit",
        action="publish",
        files={"cover": ("b.png", image("PNG", "blue"), "image/png")},
    )

    assert response.status_code == 303
    db.refresh(post)
    assert post.cover.endswith(".png")
    assert cover_img(client.get(f"/post/{post.id}/").text) == [media_url(post.cover)]
    assert (settings.media_root / post.cover).is_file()
    assert not old_path.exists()
    gc.collect()


def test_remove_cover(admin_client, client, db):
    """Scenario: 移除封面"""
    save(admin_client, action="publish", files={"cover": ("a.jpg", image(), "image/jpeg")})
    post = only_post(db)
    old_path = settings.media_root / post.cover

    response = save(admin_client, f"/post/{post.id}/edit", action="publish", remove_cover="1")

    assert response.status_code == 303
    db.refresh(post)
    assert post.cover is None
    assert cover_img(client.get(f"/post/{post.id}/").text) == []
    assert not old_path.exists()
    gc.collect()


def test_failed_commit_removes_new_cover_and_keeps_old(admin_client, db, monkeypatch):
    save(admin_client, action="publish", files={"cover": ("a.jpg", image(), "image/jpeg")})
    post = only_post(db)
    old_path = settings.media_root / post.cover

    def fail(self):
        raise RuntimeError("写库失败")

    monkeypatch.setattr(Session, "commit", fail)
    files = {"cover": ("b.png", image("PNG", "blue"), "image/png")}

    with pytest.raises(RuntimeError):
        save(admin_client, f"/post/{post.id}/edit", action="publish", files=files)

    assert saved_files() == [old_path]
    gc.collect()


def test_saving_without_cover_keeps_existing_cover(admin_client, db):
    save(admin_client, action="publish", files={"cover": ("a.jpg", image(), "image/jpeg")})
    post = only_post(db)
    cover = post.cover

    response = save(admin_client, f"/post/{post.id}/edit", title="新标题", action="publish")

    assert response.status_code == 303
    db.refresh(post)
    assert post.cover == cover
    assert (settings.media_root / cover).is_file()
    gc.collect()


@pytest.mark.parametrize(
    "filename, data",
    [("", b""), ("empty.jpg", b""), ("", image())],
    ids=["nothing-chosen", "empty-file", "no-filename"],
)
def test_cover_part_without_filename_or_content_is_ignored(admin_client, db, filename, data):
    fields = {"title": "标题", "body": "", "action": "draft"}
    response = browser_save(admin_client, "/write", filename, data, **fields)

    assert response.status_code == 303
    assert only_post(db).cover is None
    assert saved_files() == []
    gc.collect()


@pytest.mark.parametrize(
    "cover, message",
    [
        (("a.jpg", b"just text", "image/jpeg"), "只支持 JPG、PNG、GIF、WebP 图片"),
        (("big.gif", b"GIF89a" + b"\0" * MAX_BYTES, "image/gif"), "图片不能超过 10MB"),
    ],
    ids=["not-image", "too-large"],
)
def test_invalid_cover(admin_client, db, cover, message):
    response = save(admin_client, title="标题", body="正文内容", action="publish", files={"cover": cover})

    assert response.status_code == 400
    assert errors(response.text) == [message, "封面图需要重新选择"]
    assert 'value="标题"' in input_tag(response.text, "title")
    assert textarea(response.text) == "正文内容"
    assert post_count(db) == 0
    assert saved_files() == []
    gc.collect()


def test_invalid_cover_keeps_existing_post(admin_client, db):
    save(admin_client, action="publish", files={"cover": ("a.jpg", image(), "image/jpeg")})
    post = only_post(db)
    cover = post.cover

    response = save(
        admin_client,
        f"/post/{post.id}/edit",
        title="新标题",
        action="publish",
        remove_cover="1",
        files={"cover": ("a.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml")},
    )

    assert response.status_code == 400
    db.refresh(post)
    assert (post.title, post.cover) == ("标题", cover)
    assert saved_files() == [settings.media_root / cover]
    gc.collect()


# 删除文章


def delete(client, post_id, files=None):
    token = csrf_from(client.get("/blog/").text)
    return client.post(
        f"/post/{post_id}/delete", data={"csrf_token": token}, files=files, follow_redirects=False
    )


def test_delete_post_with_comments_and_cover(admin_client, make_post, make_comment, db):
    """Scenario: 删除有评论和封面的文章"""
    save(admin_client, action="publish", files={"cover": ("a.jpg", image(), "image/jpeg")})
    post = only_post(db)
    post_id = post.id
    cover_path = settings.media_root / post.cover
    make_comment(post, body="第一条")
    make_comment(post, body="第二条")
    other = make_post(title="另一篇")
    kept = make_comment(other, body="别的文章的评论")
    token = csrf_from(admin_client.get(f"/post/{post_id}/").text)

    response = admin_client.post(
        f"/post/{post_id}/delete", data={"csrf_token": token}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/blog/"
    db.expire_all()
    assert db.get(Post, post_id) is None
    assert db.scalars(select(Comment)).all() == [kept]
    assert not cover_path.exists()
    assert saved_files() == []
    assert admin_client.get(f"/post/{post_id}/").status_code == 404
    gc.collect()


@pytest.mark.parametrize("post_id", ["999999", "0", str(2**63), "abc"])
def test_delete_missing_post(admin_client, make_post, db, post_id):
    """Scenario: 删除不存在的文章"""
    make_post()

    response = delete(admin_client, post_id)

    assert response.status_code == 404
    assert post_count(db) == 1


def test_delete_post_closes_files(admin_client, make_post, db):
    post = make_post()
    files = {"extra": ("a.bin", b"x" * (2 * 1024 * 1024), "application/octet-stream")}

    response = delete(admin_client, post.id, files=files)

    assert response.status_code == 303
    assert post_count(db) == 0
    gc.collect()


def test_failed_delete_commit_keeps_cover(admin_client, db, monkeypatch):
    # 先提交再删封面：写库失败时文章还在，封面文件不能删
    save(admin_client, action="publish", files={"cover": ("a.jpg", image(), "image/jpeg")})
    post = only_post(db)
    cover_path = settings.media_root / post.cover
    token = csrf_from(admin_client.get("/blog/").text)

    def fail(self):
        raise RuntimeError("写库失败")

    monkeypatch.setattr(Session, "commit", fail)

    with pytest.raises(RuntimeError):
        admin_client.post(
            f"/post/{post.id}/delete", data={"csrf_token": token}, follow_redirects=False
        )

    assert post_count(db) == 1
    assert cover_path.exists()
    gc.collect()


def test_delete_post_keeps_inline_images(admin_client, db):
    # 正文插图不追踪引用，删除文章时只删封面（Non-Goals）
    token = csrf_from(admin_client.get("/write").text)
    url = admin_client.post(
        "/uploads",
        headers={"X-CSRF-Token": token},
        files={"file": ("a.png", image("PNG"), "image/png")},
    ).json()["url"]
    cover = {"cover": ("b.jpg", image(), "image/jpeg")}
    save(admin_client, body=f"![]({url})", action="publish", files=cover)
    post = only_post(db)

    response = delete(admin_client, post.id)

    assert response.status_code == 303
    assert saved_files() == [settings.media_root / url.removeprefix("/media/")]
    gc.collect()
