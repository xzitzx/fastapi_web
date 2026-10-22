from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint(
            f"status IN ('{STATUS_DRAFT}', '{STATUS_PUBLISHED}')", name="ck_posts_status"
        ),
        # 删除后 id 不复用，旧链接不会指向新文章
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    cover: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(10), default=STATUS_DRAFT)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    published_at: Mapped[datetime | None]

    comments: Mapped[list["Comment"]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="Comment.created_at, Comment.id",
    )

    @property
    def is_published(self) -> bool:
        return self.status == STATUS_PUBLISHED

    def publish(self) -> None:
        self.status = STATUS_PUBLISHED
        if self.published_at is None:
            self.published_at = utcnow()


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    post: Mapped[Post] = relationship(back_populates="comments")
