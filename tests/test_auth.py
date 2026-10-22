import base64
import gc
import io
import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import select
from starlette.requests import Request

from app import security
from app.config import settings
from app.models import Post
from app.security import log_in, safe_next
from app.templating import render, templates
from tests.conftest import TEST_PASSWORD, csrf_from

POST_ROUTES = [
    "/write",
    "/post/1/edit",
    "/post/1/delete",
    "/comments/1/delete",
    "/preview",
    "/uploads",
]


def session_of(client) -> dict:
    # Starlette 会话 cookie 的格式为 "<base64 JSON>.<时间戳>.<签名>"
    return json.loads(base64.b64decode(client.cookies["session"].split(".")[0]))


def login(client, next_path=None, username="admin", password=TEST_PASSWORD):
    token = csrf_from(client.get("/login").text)
    return client.post(
        "/login",
        params={"next": next_path} if next_path is not None else None,
        data={"csrf_token": token, "username": username, "password": password},
        follow_redirects=False,
    )


def input_tag(html: str, name: str) -> str:
    match = re.search(rf'<input[^>]*name="{name}"[^>]*>', html)
    assert match, f"页面中没有 {name} 输入框"
    return match.group(0)


def assert_redirects_to_login(client, path="/write"):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/login?next={path}"


# 登录


def test_login_page_has_form(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert csrf_from(response.text)
    assert 'type="text"' in input_tag(response.text, "username")
    assert 'type="password"' in input_tag(response.text, "password")
    assert '<label for="login-username">用户名</label>' in response.text
    assert '<label for="login-password">密码</label>' in response.text
    assert session_of(client).keys() == {"csrf"}


def test_login_success(client):
    """Scenario: 登录成功"""
    response = login(client)

    assert response.status_code == 303
    assert response.headers["location"] == "/write"
    assert client.get("/write", follow_redirects=False).status_code == 200


def test_login_wrong_password(client):
    """Scenario: 密码错误"""
    response = login(client, password="wrong-secret")

    assert response.status_code == 400
    assert "用户名或密码错误" in response.text
    assert 'value="admin"' in input_tag(response.text, "username")
    assert "value=" not in input_tag(response.text, "password")
    assert "wrong-secret" not in response.text
    assert_redirects_to_login(client)


@pytest.mark.parametrize("username", ["nobody", "管理员"])
def test_login_wrong_username_still_verifies_password(client, monkeypatch, username):
    calls = []
    real_verify = security.verify_password
    monkeypatch.setattr(
        security, "verify_password", lambda p, e: calls.append(p) or real_verify(p, e)
    )

    response = login(client, username=username)

    assert response.status_code == 400
    assert "用户名或密码错误" in response.text
    assert calls == [TEST_PASSWORD]
    assert_redirects_to_login(client)


def test_login_redirects_to_next(client):
    """Scenario: 登录后回到原页面"""
    response = login(client, next_path="/post/3/edit")

    assert response.status_code == 303
    assert response.headers["location"] == "/post/3/edit"


@pytest.mark.parametrize(
    "next_path", ["//evil.example", "/\\evil.example", "https://evil.example", "evil.example", ""]
)
def test_login_rejects_offsite_next(client, next_path):
    """Scenario: 拒绝站外跳转"""
    response = login(client, next_path=next_path)

    assert response.status_code == 303
    assert response.headers["location"] == "/write"


@pytest.mark.parametrize(
    "value, expected",
    [
        ("/post/3/edit", "/post/3/edit"),
        ("/write?a=1", "/write?a=1"),
        ("//evil.example", "/write"),
        ("/\\evil.example", "/write"),
        ("https://evil.example", "/write"),
        ("evil.example", "/write"),
        ("", "/write"),
        (None, "/write"),
        ("/\t/evil.example", "/write"),
        ("/\n/evil.example", "/write"),
    ],
)
def test_safe_next(value, expected):
    assert safe_next(value) == expected


def test_login_page_when_logged_in(admin_client):
    """Scenario: 已登录访问登录页"""
    response = admin_client.get("/login", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/write"


@pytest.mark.parametrize("token", [None, "wrong", "令牌"])
def test_login_requires_csrf(client, token):
    client.get("/login")
    data = {"username": "admin", "password": TEST_PASSWORD}
    if token is not None:
        data["csrf_token"] = token

    response = client.post("/login", data=data, follow_redirects=False)

    assert response.status_code == 403
    assert_redirects_to_login(client)


def test_login_rotates_csrf_token(client):
    old_token = csrf_from(client.get("/login").text)
    client.post(
        "/login",
        data={"csrf_token": old_token, "username": "admin", "password": TEST_PASSWORD},
        follow_redirects=False,
    )

    session = session_of(client)
    assert session.keys() == {"csrf", "admin"}
    assert session["admin"] is True
    assert session["csrf"] != old_token
    # 登录前的令牌不再有效
    response = client.post("/logout", data={"csrf_token": old_token}, follow_redirects=False)
    assert response.status_code == 403
    assert client.get("/write", follow_redirects=False).status_code == 200


def test_log_in_clears_session():
    request = SimpleNamespace(session={"csrf": "old", "stale": 1})

    log_in(request)

    assert request.session.keys() == {"csrf", "admin"}
    assert request.session["admin"] is True
    assert request.session["csrf"] != "old"


def test_login_returns_to_protected_page_with_query(client):
    location = client.get("/write?a=1&b=x%20y", follow_redirects=False).headers["location"]
    assert location == "/login?next=/write%3Fa%3D1%26b%3Dx%2520y"

    # 登录表单提交到当前地址，next 随之保留
    token = csrf_from(client.get(location).text)
    response = client.post(
        location,
        data={"csrf_token": token, "username": "admin", "password": TEST_PASSWORD},
        follow_redirects=False,
    )

    assert response.headers["location"] == "/write?a=1&b=x%20y"


# 退出登录


def test_logout(admin_client):
    """Scenario: 退出"""
    token = csrf_from(admin_client.get("/blog/").text)

    response = admin_client.post("/logout", data={"csrf_token": token}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert_redirects_to_login(admin_client)


@pytest.mark.filterwarnings("error")
def test_login_and_logout_close_uploaded_files(client):
    # 自己解析的表单不会被 FastAPI 自动关闭，附带的上传文件要显式关闭
    files = {"extra": ("a.txt", b"x" * 1024, "text/plain")}
    token = csrf_from(client.get("/login").text)
    data = {"csrf_token": token, "username": "admin", "password": TEST_PASSWORD}

    assert client.post("/login", data=data, files=files, follow_redirects=False).status_code == 303
    token = csrf_from(client.get("/blog/").text)
    response = client.post("/logout", data={"csrf_token": token}, files=files, follow_redirects=False)
    assert response.status_code == 303
    gc.collect()


def test_get_logout_does_not_log_out(admin_client):
    """Scenario: GET 请求不能退出"""
    response = admin_client.get("/logout", follow_redirects=False)

    assert response.status_code == 405
    assert admin_client.get("/write", follow_redirects=False).status_code == 200


@pytest.mark.parametrize("token", [None, "wrong"])
def test_logout_requires_csrf(admin_client, token):
    data = {} if token is None else {"csrf_token": token}

    response = admin_client.post("/logout", data=data, follow_redirects=False)

    assert response.status_code == 403
    assert admin_client.get("/write", follow_redirects=False).status_code == 200


# 受保护操作的访问控制


def test_write_page_requires_login(client):
    """Scenario: 未登录打开写作页"""
    assert_redirects_to_login(client, "/write")


def test_edit_page_requires_login(client):
    assert_redirects_to_login(client, "/post/3/edit")


def test_protected_pages_open_for_admin(admin_client, make_post):
    post = make_post()

    for path in ["/write", f"/post/{post.id}/edit"]:
        assert admin_client.get(path, follow_redirects=False).status_code == 200


@pytest.mark.parametrize("path", POST_ROUTES)
def test_protected_post_forbidden_without_login(client, path):
    # 带上有效令牌也不能代替登录
    token = csrf_from(client.get("/login").text)

    response = client.post(
        path, data={"csrf_token": token}, headers={"X-CSRF-Token": token}, follow_redirects=False
    )

    assert response.status_code == 403


@pytest.mark.parametrize("path", POST_ROUTES)
def test_protected_post_checks_login_before_parsing_body(client, monkeypatch, path):
    # 未登录时必须在解析请求体（含上传文件）之前拒绝
    def fail(*args, **kwargs):
        raise AssertionError("未登录时不应解析表单")

    monkeypatch.setattr(Request, "form", fail)

    response = client.post(
        path, files={"file": ("a.png", b"x" * 1024, "image/png")}, follow_redirects=False
    )

    assert response.status_code == 403


@pytest.mark.parametrize("path", POST_ROUTES)
def test_wrong_csrf_header_rejected_before_parsing_body(admin_client, monkeypatch, path):
    # CSRF 未通过时必须在解析请求体（含上传文件）之前拒绝
    def fail(*args, **kwargs):
        raise AssertionError("CSRF 未通过时不应解析表单")

    monkeypatch.setattr(Request, "form", fail)

    response = admin_client.post(
        path,
        headers={"X-CSRF-Token": "wrong"},
        files={"file": ("a.png", b"x" * 1024, "image/png")},
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_login_without_session_token_is_rejected(client):
    # 不先打开登录页，会话里没有令牌
    response = client.post(
        "/login",
        data={"csrf_token": "x", "username": "admin", "password": TEST_PASSWORD},
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_csrf_header_takes_precedence_over_field(admin_client):
    token = csrf_from(admin_client.get("/blog/").text)

    response = admin_client.post(
        "/preview",
        data={"csrf_token": token},
        headers={"X-CSRF-Token": "wrong"},
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_delete_post_requires_login(client, make_post, db):
    """Scenario: 未登录删除文章"""
    post = make_post()

    response = client.post(f"/post/{post.id}/delete", follow_redirects=False)

    assert response.status_code == 403
    assert db.scalar(select(Post).where(Post.id == post.id)) is not None


def test_upload_requires_login(client):
    """Scenario: 未登录上传图片"""
    token = csrf_from(client.get("/login").text)
    image = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(image, "PNG")

    response = client.post(
        "/uploads",
        headers={"X-CSRF-Token": token},
        files={"file": ("a.png", image.getvalue(), "image/png")},
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert list(settings.media_root.rglob("*")) == []


# 带完整合法表单和图片的请求，未登录或缺 CSRF 时同样不能写库、不能存文件
@pytest.mark.filterwarnings("error")
@pytest.mark.parametrize("who", ["guest", "admin-without-csrf"])
@pytest.mark.parametrize("path", ["/write", "/uploads"])
def test_rejected_post_with_valid_form_changes_nothing(client, admin_client, db, path, who):
    image = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(image, "PNG")
    files = {"cover" if path == "/write" else "file": ("a.png", image.getvalue(), "image/png")}
    data = {"title": "标题", "body": "正文", "action": "publish"}
    headers = {}
    if who == "guest":
        sender = client
        token = csrf_from(client.get("/login").text)
        data["csrf_token"] = token
        headers["X-CSRF-Token"] = token
    else:
        sender = admin_client

    response = sender.post(path, data=data, files=files, headers=headers, follow_redirects=False)

    assert response.status_code == 403
    assert db.scalars(select(Post)).all() == []
    assert list(settings.media_root.rglob("*")) == []
    gc.collect()


def test_delete_post_without_csrf(admin_client, make_post, db):
    """Scenario: 登录后缺少 CSRF 令牌"""
    post = make_post()

    response = admin_client.post(f"/post/{post.id}/delete", follow_redirects=False)

    assert response.status_code == 403
    assert db.scalar(select(Post).where(Post.id == post.id)) is not None


@pytest.mark.parametrize("path", POST_ROUTES)
@pytest.mark.parametrize(
    "data, headers",
    [({}, {}), ({"csrf_token": "wrong"}, {}), ({}, {"X-CSRF-Token": "wrong"})],
    ids=["missing", "wrong-field", "wrong-header"],
)
def test_protected_post_forbidden_with_bad_csrf(admin_client, path, data, headers):
    response = admin_client.post(path, data=data, headers=headers, follow_redirects=False)

    assert response.status_code == 403


# 拒绝时要关闭已解析表单里的临时文件，否则出现 ResourceWarning
@pytest.mark.filterwarnings("error")
@pytest.mark.parametrize(
    "data, files",
    [
        ({}, {"csrf_token": ("t.txt", b"x")}),
        ({"csrf_token": "wrong"}, {"cover": ("a.png", b"x" * 1024, "image/png")}),
    ],
    ids=["token-as-file", "wrong-token-with-file"],
)
def test_multipart_with_bad_csrf_is_rejected(admin_client, data, files):
    response = admin_client.post("/write", data=data, files=files, follow_redirects=False)

    assert response.status_code == 403


@pytest.mark.parametrize("path", POST_ROUTES)
@pytest.mark.parametrize("via", ["field", "header"])
def test_protected_post_passes_checks_with_csrf(admin_client, path, via):
    token = csrf_from(admin_client.get("/blog/").text)
    if via == "field":
        response = admin_client.post(path, data={"csrf_token": token}, follow_redirects=False)
    else:
        response = admin_client.post(path, headers={"X-CSRF-Token": token}, follow_redirects=False)

    assert response.status_code != 403


# 模板渲染


def make_request(session: dict) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [],
        "session": session,
    }
    return Request(scope)


def test_render_creates_csrf_token_only_when_used():
    request = make_request({})

    body = render(request, "base.html").body.decode()

    assert request.session == {}
    assert "csrf_token" not in body
    assert "/logout" not in body


def test_render_injects_admin_state_and_csrf_token():
    request = make_request({"admin": True})

    response = render(request, "base.html", status_code=201)
    body = response.body.decode()

    assert response.status_code == 201
    assert 'action="/logout"' in body
    assert csrf_from(body) == request.session["csrf"]


def test_date_filters_registered():
    dt = datetime(2025, 10, 21, 16, 30, tzinfo=timezone.utc)
    template = templates.env.from_string("{{ d|date }}|{{ d|date_cn }}|{{ d|datetime_local }}")

    assert template.render(d=dt) == "2025-10-22|2025年10月22日|2025-10-22 00:30"
