import atexit
import os
import re
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.passwords import hash_password

TEST_PASSWORD = "test-password"

# 必须在 import app.main 之前设置
_tmp = Path(tempfile.mkdtemp())
atexit.register(shutil.rmtree, _tmp, ignore_errors=True)
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD_HASH"] = hash_password(TEST_PASSWORD)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["MEDIA_ROOT"] = str(_tmp / "media")

from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import STATUS_PUBLISHED, Comment, Post, utcnow  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_state():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    shutil.rmtree(settings.media_root, ignore_errors=True)
    settings.media_root.mkdir(parents=True)


def csrf_from(html: str) -> str:
    match = re.search(r'<input[^>]*name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match, "页面中没有 CSRF 隐藏字段"
    return match.group(1)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_client():
    # 独立的 TestClient，同一测试里 client 仍是未登录的访客
    with TestClient(app) as c:
        token = csrf_from(c.get("/login").text)
        response = c.post(
            "/login",
            data={"csrf_token": token, "username": "admin", "password": TEST_PASSWORD},
            follow_redirects=False,
        )
        assert response.status_code == 303
        yield c


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def make_post(db):
    def make(title="标题", body="正文", status=STATUS_PUBLISHED, published_at=None, created_at=None):
        if status == STATUS_PUBLISHED and published_at is None:
            published_at = utcnow()
        post = Post(
            title=title, body=body, status=status, published_at=published_at, created_at=created_at
        )
        db.add(post)
        db.commit()
        return post

    return make


@pytest.fixture
def make_comment(db):
    def make(post, name="访客", body="评论"):
        comment = Comment(post_id=post.id, name=name, body=body)
        db.add(comment)
        db.commit()
        return comment

    return make
