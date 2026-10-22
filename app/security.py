import hmac
import secrets

from fastapi import HTTPException, Request

from app.config import settings
from app.passwords import verify_password

SESSION_CSRF = "csrf"
SESSION_ADMIN = "admin"
CSRF_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def get_csrf_token(request: Request) -> str:
    token = request.session.get(SESSION_CSRF)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_CSRF] = token
    return token


def csrf_valid(request: Request, token: str | None) -> bool:
    expected = request.session.get(SESSION_CSRF)
    if not expected or not token:
        return False
    # 先转 bytes：compare_digest 不接受含非 ASCII 字符的 str
    return hmac.compare_digest(expected.encode(), token.encode())


def is_admin(request: Request) -> bool:
    return request.session.get(SESSION_ADMIN) is True


def check_credentials(username: str, password: str) -> bool:
    # 用户名错误时也做一次密码校验，避免通过响应时间判断用户名
    username_ok = hmac.compare_digest(username.encode(), settings.admin_username.encode())
    password_ok = verify_password(password, settings.admin_password_hash)
    return username_ok and password_ok


def log_in(request: Request) -> None:
    request.session.clear()
    request.session[SESSION_ADMIN] = True
    get_csrf_token(request)


def log_out(request: Request) -> None:
    request.session.clear()


def safe_next(value: str | None) -> str:
    if (
        value
        and value.isprintable()
        and value.startswith("/")
        and not value.startswith(("//", "/\\"))
    ):
        return value
    return "/write"


class LoginRequired(Exception):
    def __init__(self, next_path: str) -> None:
        super().__init__(next_path)
        self.next_path = next_path


def require_admin_page(request: Request) -> None:
    if not is_admin(request):
        query = request.url.query
        raise LoginRequired(request.url.path + (f"?{query}" if query else ""))


def require_admin(request: Request) -> None:
    if not is_admin(request):
        raise HTTPException(status_code=403)


async def require_csrf(request: Request) -> None:
    token = request.headers.get(CSRF_HEADER)
    if token is None:
        value = (await request.form()).get(CSRF_FIELD)
        # 字段可能以文件形式提交，只接受字符串
        token = value if isinstance(value, str) else None
    if not csrf_valid(request, token):
        # 关闭已解析表单中的上传临时文件；通过时表单留给路由函数继续使用
        await request.close()
        raise HTTPException(status_code=403)
