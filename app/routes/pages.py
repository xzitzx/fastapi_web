import math
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.db import get_db
from app.models import STATUS_DRAFT, STATUS_PUBLISHED, Comment, Post
from app.rendering import excerpt, reading_minutes, render_markdown
from app.routes import DbId
from app.security import is_admin, require_csrf
from app.templating import render

router = APIRouter()

PER_PAGE = 5
HOME_LIMIT = 5

PUBLISHED = Post.status == STATUS_PUBLISHED
NEWEST_FIRST = (Post.published_at.desc(), Post.id.desc())


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    posts = db.scalars(select(Post).where(PUBLISHED).order_by(*NEWEST_FIRST).limit(HOME_LIMIT)).all()
    return render(request, "home.html", {"posts": posts})


@router.get("/blog/")
def post_list(request: Request, page: str = "1", db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(Post).where(PUBLISHED))
    pages = max(1, math.ceil(total / PER_PAGE))
    if not re.fullmatch(r"-?[0-9]+", page):
        number = 1
    elif len(page) > 18:
        # 位数过多必然越界，同时避开 int() 的位数上限
        number = pages
    else:
        number = int(page)
    if not 1 <= number <= pages:
        number = pages

    rows = db.execute(
        select(Post, func.count(Comment.id))
        .outerjoin(Post.comments)
        .where(PUBLISHED)
        .group_by(Post.id)
        .order_by(*NEWEST_FIRST)
        .limit(PER_PAGE)
        .offset((number - 1) * PER_PAGE)
    ).all()
    items = [
        {
            "post": post,
            "comment_count": comment_count,
            "excerpt": excerpt(post.body),
            "minutes": reading_minutes(post.body),
        }
        for post, comment_count in rows
    ]
    drafts = []
    if is_admin(request):
        drafts = db.scalars(
            select(Post)
            .where(Post.status == STATUS_DRAFT)
            .order_by(Post.updated_at.desc(), Post.id.desc())
        ).all()
    context = {"items": items, "drafts": drafts, "page": number, "pages": pages}
    return render(request, "post_list.html", context)


@router.get("/post/{post_id}/")
def post_detail(request: Request, post_id: DbId, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if post is None or not (post.is_published or is_admin(request)):
        raise HTTPException(status_code=404)
    return render_detail(request, db, post)


@router.post("/post/{post_id}/")
async def add_comment(request: Request, post_id: DbId, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if post is None or not post.is_published:
        raise HTTPException(status_code=404)
    await require_csrf(request)
    async with request.form() as form:
        name = form.get("name")
        body = form.get("body")
    # 浏览器总会提交这两个字段，缺失或以文件形式提交只可能是构造的请求
    if not isinstance(name, str) or not isinstance(body, str):
        raise HTTPException(status_code=400)
    name = name.strip()
    # 浏览器把换行提交为 \r\n，统一成 \n 后再计算长度
    body = body.replace("\r\n", "\n").strip()

    errors = []
    if not name:
        errors.append("昵称不能为空")
    elif len(name) > 80:
        errors.append("昵称不能超过 80 个字符")
    if not body:
        errors.append("内容不能为空")
    elif len(body) > 2000:
        errors.append("内容过长，最多 2000 个字符")
    if errors:
        return render_detail(
            request, db, post, 400, errors=errors, comment_name=name, comment_body=body
        )

    db.add(Comment(post_id=post.id, name=name, body=body))
    db.commit()
    return RedirectResponse(f"/post/{post.id}/", status_code=303)


def render_detail(
    request: Request, db: Session, post: Post, status_code: int = 200, **form_state
) -> Response:
    context = {
        "post": post,
        "body_html": render_markdown(post.body),
        "minutes": reading_minutes(post.body),
        "comments": post.comments,
        **form_state,
    }
    if post.is_published:
        # 在 SQL 中比较 (published_at, id)，发布时间相同时以 id 决定先后
        key = tuple_(Post.published_at, Post.id)
        current = (post.published_at, post.id)
        published = select(Post).where(PUBLISHED)
        context["prev_post"] = db.scalars(
            published.where(key < current).order_by(*NEWEST_FIRST).limit(1)
        ).first()
        context["next_post"] = db.scalars(
            published.where(key > current).order_by(Post.published_at, Post.id).limit(1)
        ).first()
    return render(request, "post_detail.html", context, status_code)
