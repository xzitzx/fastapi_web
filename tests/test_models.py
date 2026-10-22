from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.db import Base, SessionLocal, engine, get_db, init_db
from app.models import STATUS_DRAFT, STATUS_PUBLISHED, Comment, Post

T1 = datetime(2025, 1, 1, tzinfo=timezone.utc)


def test_init_db_creates_tables():
    Base.metadata.drop_all(engine)

    init_db()

    assert set(inspect(engine).get_table_names()) == {"posts", "comments"}
    indexed = [i["column_names"] for i in inspect(engine).get_indexes("comments")]
    assert ["post_id"] in indexed


def test_get_db_yields_and_closes_session(make_post):
    make_post()
    gen = get_db()
    session = next(gen)

    assert session.scalars(select(Post)).one().title == "标题"
    gen.close()
    assert not session.in_transaction()


def test_create_post_defaults(db):
    post = Post(title="新文章")
    db.add(post)
    db.commit()

    assert post.id is not None
    assert post.body == ""
    assert post.cover is None
    assert post.status == STATUS_DRAFT
    assert not post.is_published
    assert post.published_at is None
    assert post.created_at.tzinfo is timezone.utc
    assert post.updated_at.tzinfo is timezone.utc


def test_create_comment(db, make_post):
    post = make_post()
    db.add(Comment(post=post, name="访客", body="你好"))
    db.commit()

    with SessionLocal() as other:
        comment = other.scalars(select(Comment)).one()
        assert comment.post_id == post.id
        assert comment.post.title == "标题"
        assert comment.created_at is not None


def test_updated_at_changes_on_update(db):
    post = Post(title="旧标题", created_at=T1, updated_at=T1)
    db.add(post)
    db.commit()

    post.title = "新标题"
    db.commit()

    assert post.updated_at > T1
    assert post.created_at == T1


def test_deleted_ids_are_not_reused(db, make_post):
    # 否则删掉最新一篇后，旧链接 /post/<id>/ 会指向新文章
    first = make_post()
    latest = make_post()
    old_comment = Comment(post=first, name="a", body="b")
    db.add(old_comment)
    db.commit()
    latest_id, comment_id = latest.id, old_comment.id
    db.delete(latest)
    db.delete(old_comment)
    db.commit()

    new_post = make_post()
    new_comment = Comment(post=first, name="a", body="b")
    db.add(new_comment)
    db.commit()

    assert new_post.id > latest_id
    assert new_comment.id > comment_id


def test_comments_ordered_by_created_at_then_id(db, make_post):
    post = make_post()
    later = Comment(post=post, name="a", body="晚", created_at=T1 + timedelta(hours=1))
    first = Comment(post=post, name="b", body="早", created_at=T1)
    second = Comment(post=post, name="c", body="同时", created_at=T1)
    db.add_all([later, first, second])
    db.commit()

    with SessionLocal() as other:
        bodies = [c.body for c in other.get(Post, post.id).comments]
    assert bodies == ["早", "同时", "晚"]
    # SQLite 按 rowid 扫描，行为上难以区分是否按 id 排序，所以直接检查排序定义
    assert [c.name for c in Post.comments.property.order_by] == ["created_at", "id"]


def test_delete_post_deletes_comments(db, make_post):
    post = make_post()
    db.add_all([Comment(post=post, name="a", body="1"), Comment(post=post, name="b", body="2")])
    db.commit()

    db.delete(post)
    db.commit()

    assert db.scalar(select(Post).where(Post.id == post.id)) is None
    assert db.scalars(select(Comment)).all() == []


def test_foreign_key_cascade_in_database(db, make_post):
    post = make_post()
    db.add(Comment(post=post, name="a", body="1"))
    db.commit()

    assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1
    db.execute(delete(Post).where(Post.id == post.id))
    db.commit()

    assert db.execute(text("SELECT COUNT(*) FROM comments")).scalar() == 0


def test_invalid_status_rejected(db):
    db.add(Post(title="x", status="archived"))

    with pytest.raises(IntegrityError, match="ck_posts_status"):
        db.commit()


def test_publish_sets_published_at_first_time():
    post = Post(title="x")
    before = datetime.now(timezone.utc)

    post.publish()

    assert post.status == STATUS_PUBLISHED
    assert post.is_published
    assert post.published_at >= before


def test_publish_keeps_existing_published_at():
    post = Post(title="x", status=STATUS_DRAFT, published_at=T1)

    post.publish()

    assert post.status == STATUS_PUBLISHED
    assert post.published_at == T1


def test_make_post_fixture(make_post):
    published = make_post()
    draft = make_post(status=STATUS_DRAFT)

    assert published.published_at is not None
    assert draft.published_at is None
