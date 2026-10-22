from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from app.config import BASE_DIR
from app.rendering import current_year, fmt_date, fmt_date_cn, fmt_datetime
from app.security import get_csrf_token, is_admin

# 不传 env 时 Starlette 使用 select_autoescape()，.html 模板自动转义
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")
templates.env.filters["date"] = fmt_date
templates.env.filters["date_cn"] = fmt_date_cn
templates.env.filters["datetime_local"] = fmt_datetime


def render(
    request: Request, name: str, context: dict | None = None, status_code: int = 200
) -> Response:
    context = {
        **(context or {}),
        "is_admin": is_admin(request),
        # 只在模板调用时才生成令牌，未用到令牌的页面不写会话
        "csrf_token": lambda: get_csrf_token(request),
        "year": current_year(),
    }
    return templates.TemplateResponse(request, name, context, status_code=status_code)
