from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.security import check_credentials, is_admin, log_in, log_out, require_csrf, safe_next
from app.templating import render

router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    if is_admin(request):
        return RedirectResponse("/write", status_code=303)
    return render(request, "login.html")


@router.post("/login")
async def login(request: Request):
    await require_csrf(request)
    async with request.form() as form:
        username = form.get("username")
        password = form.get("password")
    # 浏览器总会提交这两个字段，缺失或以文件形式提交只可能是构造的请求
    if not isinstance(username, str) or not isinstance(password, str):
        raise HTTPException(status_code=400)
    # scrypt 约 20ms，放进线程池避免阻塞事件循环
    if not await run_in_threadpool(check_credentials, username, password):
        context = {"username": username, "error": "用户名或密码错误"}
        return render(request, "login.html", context, status_code=400)
    log_in(request)
    return RedirectResponse(safe_next(request.query_params.get("next")), status_code=303)


@router.post("/logout")
async def logout(request: Request):
    await require_csrf(request)
    await request.close()
    log_out(request)
    return RedirectResponse("/", status_code=303)
