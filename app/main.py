from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_DIR, settings
from app.db import init_db
from app.routes import auth, authoring, pages
from app.security import LoginRequired
from app.templating import render


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax")
    settings.media_root.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
    app.mount("/media", StaticFiles(directory=settings.media_root), name="media")
    app.include_router(pages.router)
    app.include_router(auth.router)
    app.include_router(authoring.router)

    @app.exception_handler(LoginRequired)
    async def redirect_to_login(request: Request, exc: LoginRequired) -> RedirectResponse:
        return RedirectResponse("/login?next=" + quote(exc.next_path, safe="/"), status_code=303)

    @app.exception_handler(StarletteHTTPException)
    async def not_found_page(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return render(request, "404.html", status_code=404)
        return await http_exception_handler(request, exc)

    # 会校验失败的只有整数路径参数（如 /post/abc/），按地址不存在处理
    @app.exception_handler(RequestValidationError)
    async def invalid_path_page(request: Request, exc: RequestValidationError):
        return render(request, "404.html", status_code=404)

    return app


app = create_app()
