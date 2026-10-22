from datetime import datetime, timezone

import pytest
from markupsafe import Markup

from app.db import SessionLocal
from app.models import Post
from app.rendering import (
    TZ,
    current_year,
    excerpt,
    fmt_date,
    fmt_date_cn,
    fmt_datetime,
    reading_minutes,
    render_markdown,
    to_local,
)

CROSS_DAY_AWARE = datetime(2025, 10, 21, 16, 30, tzinfo=timezone.utc)
CROSS_DAY_NAIVE = datetime(2025, 10, 21, 16, 30)


def test_reading_minutes_1000_chars():
    """Scenario: 1000 字正文"""
    body = "字" * 500 + " \n\t " + "字" * 500

    assert reading_minutes(body) == 3


def test_reading_minutes_short():
    """Scenario: 极短正文"""
    assert reading_minutes("一二三四五 六七八九十") == 1


def test_reading_minutes_ignores_whitespace():
    assert reading_minutes("字" * 400 + "\n\n  \t" * 10) == 1


def test_reading_minutes_empty_is_one():
    assert reading_minutes("") == 1


@pytest.mark.parametrize("dt", [CROSS_DAY_AWARE, CROSS_DAY_NAIVE], ids=["aware", "naive"])
def test_cross_day_time(dt):
    """Scenario: 跨日的时间"""
    assert fmt_date(dt) == "2025-10-22"
    assert fmt_date_cn(dt) == "2025年10月22日"
    assert fmt_datetime(dt) == "2025-10-22 00:30"
    assert to_local(dt).tzinfo is TZ


def test_cross_day_time_read_from_database(make_post):
    """Scenario: 跨日的时间（经 SQLite 读出的 naive 值）"""
    post = make_post(published_at=CROSS_DAY_AWARE)

    with SessionLocal() as other:
        stored = other.get(Post, post.id).published_at

    assert stored.tzinfo is None
    assert fmt_date(stored) == "2025-10-22"


@pytest.mark.parametrize(
    "now, year",
    [
        (datetime(2025, 12, 31, 16, 0, tzinfo=timezone.utc), 2026),
        (datetime(2025, 12, 31, 15, 59, tzinfo=timezone.utc), 2025),
    ],
)
def test_current_year_in_beijing_time(now, year):
    assert current_year(now) == year


def test_current_year_defaults_to_now():
    assert current_year() == datetime.now(TZ).year


def test_render_markdown():
    html = render_markdown("## 小节\n\n```python\nprint(1)\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")

    assert isinstance(html, Markup)
    assert '<h2 id="' in html
    assert '<div class="codehilite">' in html
    assert "<table>" in html


def test_excerpt_strips_markdown():
    body = "## 小节标题\n\n这里有 `行内代码` 和 **粗体**。\n\n```python\nprint(1)\n```\n\n" + "长" * 200

    result = excerpt(body)

    assert "##" not in result
    assert "`" not in result
    assert "<" not in result
    assert result.endswith("…")
    assert len(result) == 101
    assert result.startswith("小节标题 这里有 行内代码 和 粗体。 print(1) 长")


def test_excerpt_short_text_unchanged():
    assert excerpt("A & B\n\n第二段") == "A & B 第二段"


def test_chinese_heading_anchor_is_readable():
    assert '<h2 id="写一个过滤器">写一个过滤器</h2>' in render_markdown("## 写一个过滤器")


def test_excerpt_ignores_html_comments():
    assert excerpt("<!-- a > b -->\n\n正文") == "正文"


def test_excerpt_no_space_before_ellipsis():
    assert excerpt("字" * 99 + " " + "字" * 10) == "字" * 99 + "…"


def test_excerpt_exactly_length_has_no_ellipsis():
    assert excerpt("字" * 100) == "字" * 100
