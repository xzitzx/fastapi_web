import html
import math
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import markdown
from markdown.extensions.toc import slugify_unicode
from markupsafe import Markup

TZ = ZoneInfo("Asia/Shanghai")


def render_markdown(text: str) -> Markup:
    # 正文只有站长能写，视为可信内容
    return Markup(
        markdown.markdown(
            text,
            extensions=["extra", "codehilite", "toc"],
            # 默认 slugify 会丢掉中文，标题锚点只剩 _1 这类编号
            extension_configs={"toc": {"slugify": slugify_unicode}},
        )
    )


def excerpt(text: str, length: int = 100) -> str:
    stripped = re.sub(r"<!--.*?-->|<[^>]*>", "", str(render_markdown(text)), flags=re.S)
    plain = " ".join(html.unescape(stripped).split())
    return plain[:length].rstrip() + "…" if len(plain) > length else plain


def reading_minutes(text: str) -> int:
    chars = len("".join(text.split()))
    return max(1, math.ceil(chars / 400))


def to_local(dt: datetime) -> datetime:
    # SQLite 读出的时间不带时区，按 UTC 处理
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ)


def fmt_date(dt: datetime) -> str:
    return to_local(dt).strftime("%Y-%m-%d")


def fmt_date_cn(dt: datetime) -> str:
    return to_local(dt).strftime("%Y年%m月%d日")


def fmt_datetime(dt: datetime) -> str:
    return to_local(dt).strftime("%Y-%m-%d %H:%M")


def current_year(now: datetime | None = None) -> int:
    return to_local(now or datetime.now(timezone.utc)).year
