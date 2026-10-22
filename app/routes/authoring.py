from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.datastructures import FormData, UploadFile

from app.db import get_db
from app.images import InvalidImage, delete_media, media_url, save_image
from app.models import STATUS_DRAFT, Comment, Post, utcnow
from app.rendering import render_markdown
from app.routes import DbId
from app.security import require_admin, require_admin_page, require_csrf
from app.templating import render

router = APIRouter()


@router.get("/write")
def write_page(request: Request):
    require_admin_page(request)
    return render(request, "write.html", {"post": None, "title": "", "body": ""})


@router.post("/write")
async def create_post(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    await require_csrf(request)
    async with request.form() as form:
        return await save_post(request, db, form, None)


@router.get("/post/{post_id}/edit")
def edit_page(request: Request, post_id: DbId, db: Session = Depends(get_db)):
    require_admin_page(request)
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404)
    return render(request, "write.html", {"post": post, "title": post.title, "body": post.body})


@router.post("/post/{post_id}/edit")
async def update_post(request: Request, post_id: DbId, db: Session = Depends(get_db)):
    require_admin(request)
    await require_csrf(request)
    async with request.form() as form:
        post = db.get(Post, post_id)
        if post is None:
            raise HTTPException(status_code=404)
        return await save_post(request, db, form, post)


async def save_post(request: Request, db: Session, form: FormData, post: Post | None) -> Response:
    # 上传文件只能在表单关闭前读取，调用方须在 async with request.form() 内调用
    title = form.get("title")
    body = form.get("body")
    action = form.get("action")
    cover = form.get("cover")
    # 浏览器总会提交这些字段，缺失或取值不对只可能是构造的请求
    if not (isinstance(title, str) and isinstance(body, str) and action in ("draft", "publish")):
        raise HTTPException(status_code=400)
    title = title.strip()
    # 未选文件时浏览器也会提交一个文件名为空的 cover
    cover_chosen = isinstance(cover, UploadFile) and bool(cover.filename) and bool(cover.size)

    errors = []
    if not title:
        errors.append("标题不能为空")
    elif len(title) > 200:
        errors.append("标题过长，最多 200 个字符")
    if action == "publish" and not body.strip():
        errors.append("正文不能为空")
    new_cover = None
    if cover_chosen and not errors:
        try:
            new_cover = await save_image(cover, "covers")
        except InvalidImage as exc:
            errors.append(str(exc))
    if errors:
        if cover_chosen:
            errors.append("封面图需要重新选择")
        context = {
            "post": post,
            "title": title,
            "body": body,
            "remove_cover": form.get("remove_cover") == "1",
            "errors": errors,
        }
        return render(request, "write.html", context, 400)

    if post is None:
        post = Post()
        db.add(post)
    old_cover = post.cover
    post.title = title
    post.body = body
    if new_cover:
        post.cover = new_cover
    elif form.get("remove_cover") == "1":
        post.cover = None
    if action == "publish":
        post.publish()
    else:
        post.status = STATUS_DRAFT
    # 内容没变时 onupdate 不会触发，显式记录这次保存
    post.updated_at = utcnow()
    try:
        db.commit()
    except Exception:
        # 写库失败时新封面无人引用，删掉以免留下孤儿文件；旧封面仍在使用，不能删
        delete_media(new_cover)
        raise
    if post.cover != old_cover:
        delete_media(old_cover)
    if action == "publish":
        return RedirectResponse(f"/post/{post.id}/", status_code=303)
    return RedirectResponse(f"/post/{post.id}/edit", status_code=303)


@router.post("/post/{post_id}/delete")
async def delete_post(request: Request, post_id: DbId, db: Session = Depends(get_db)):
    require_admin(request)
    await require_csrf(request)
    # require_csrf 可能已解析表单，本路由用不到，关闭其中上传的临时文件
    await request.close()
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404)
    # 评论由 ORM 级联删除；正文插图不追踪引用，不删除
    db.delete(post)
    db.commit()
    delete_media(post.cover)
    return RedirectResponse("/blog/", status_code=303)


@router.post("/comments/{comment_id}/delete")
async def delete_comment(request: Request, comment_id: DbId, db: Session = Depends(get_db)):
    require_admin(request)
    await require_csrf(request)
    # require_csrf 可能已解析表单，本路由用不到，关闭其中上传的临时文件
    await request.close()
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404)
    db.delete(comment)
    db.commit()
    return RedirectResponse(f"/post/{comment.post_id}/", status_code=303)


@router.post("/preview")
async def preview(request: Request):
    require_admin(request)
    await require_csrf(request)
    async with request.form() as form:
        body = form.get("body")
    if not isinstance(body, str):
        raise HTTPException(status_code=400)
    body_html = render_markdown(body) if body.strip() else None
    return render(request, "_preview.html", {"body_html": body_html})


@router.post("/uploads")
async def upload_image(request: Request):
    require_admin(request)
    await require_csrf(request)
    async with request.form() as form:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            return JSONResponse({"error": "没有收到文件"}, status_code=400)
        try:
            rel = await save_image(upload, "uploads")
        except InvalidImage as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"url": media_url(rel)})
