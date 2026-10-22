import re
from datetime import datetime, timedelta, timezone

from app.models import STATUS_DRAFT

BASE = datetime(2025, 10, 1, 4, 0, tzinfo=timezone.utc)


def post_links(html: str) -> list[tuple[int, str]]:
    # 按顺序返回 (文章 id, 链接内的 HTML)
    return [
        (int(post_id), inner)
        for post_id, inner in re.findall(r'<a\b[^>]*href="/post/(\d+)/"[^>]*>(.*?)</a>', html, re.S)
    ]


def test_home_has_recent_heading(client):
    html = client.get("/").text

    assert re.findall(r"<h1\b[^>]*>(.*?)</h1>", html, re.S) == ["最近文章"]


def test_home_lists_latest_five(client, make_post):
    """Scenario: 有 7 篇已发布文章"""
    posts = [make_post(title=f"文章{i}", published_at=BASE + timedelta(days=i)) for i in range(7)]

    html = client.get("/").text

    links = post_links(html)
    expected = list(reversed(posts))[:5]
    assert [post_id for post_id, _ in links] == [post.id for post in expected]
    dates = ["2025-10-07", "2025-10-06", "2025-10-05", "2025-10-04", "2025-10-03"]
    for (_, inner), post, date in zip(links, expected, dates):
        assert post.title in inner
        assert date in inner
    assert re.search(r'<a\b[^>]*href="/blog/"[^>]*>全部文章 →</a>', html)


def test_home_without_published_posts(client, make_post):
    """Scenario: 没有已发布文章"""
    make_post(title="未发布的草稿", status=STATUS_DRAFT)

    response = client.get("/")

    assert response.status_code == 200
    assert "还没有文章" in response.text
    assert "未发布的草稿" not in response.text
    assert post_links(response.text) == []


def test_home_background_video(client):
    """Scenario: 背景视频属性"""
    html = client.get("/").text

    tag = re.search(r"<video\b([^>]*)>", html)
    assert tag, "首页没有 <video>"
    attrs = {token.split("=")[0] for token in tag.group(1).split()}
    assert {"autoplay", "muted", "loop", "playsinline"} <= attrs
    assert 'src="/static/videos/home.mp4"' in tag.group(0)
    video = client.get("/static/videos/home.mp4")
    assert video.status_code == 200
    assert video.headers["content-type"] == "video/mp4"


def test_home_video_has_poster(client):
    # 视频加载出来之前先显示第一帧，避免黑屏
    tag = re.search(r"<video\b[^>]*>", client.get("/").text).group(0)

    assert 'poster="/static/videos/home.jpg"' in tag
    poster = client.get("/static/videos/home.jpg")
    assert poster.status_code == 200
    assert poster.headers["content-type"] == "image/jpeg"


def mp4_boxes(data: bytes) -> list[str]:
    boxes, i = [], 0
    while i + 8 <= len(data):
        size = int.from_bytes(data[i : i + 4], "big")
        boxes.append(data[i + 4 : i + 8].decode("latin1"))
        i += size
    return boxes


def test_home_video_is_progressive_h264(client):
    # H.264 几乎所有设备都能硬件解码；moov 在 mdat 之前才能边下边播；分片 MP4 循环时易卡顿
    data = client.get("/static/videos/home.mp4").content

    boxes = mp4_boxes(data)
    assert boxes.index("moov") < boxes.index("mdat")
    assert "moof" not in boxes
    assert b"avc1" in data and b"av01" not in data
    assert b"mp4a" not in data  # 页面静音，不需要音轨


def test_home_video_has_no_text_overlay(client):
    html = client.get("/").text

    hero = re.search(r'<div class="hero">(.*?)</div>', html, re.S).group(1)
    assert re.sub(r"<script>.*?</script>|<[^>]+>", "", hero, flags=re.S).strip() == ""


def test_home_video_respects_reduced_motion(client):
    html = client.get("/").text

    script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    assert "prefers-reduced-motion: reduce" in script
    assert 'removeAttribute("autoplay")' in script
    assert ".pause()" in script


def test_home_scroll_arrow(client):
    html = client.get("/").text

    arrow = re.search(r'<a\b[^>]*href="#recent"[^>]*>', html)
    assert arrow, "没有向下滚动的箭头"
    assert re.search(r'aria-label="[^"]+"', arrow.group(0))
    assert 'id="recent"' in html


def test_home_date_in_beijing_time(client, make_post):
    """Scenario: 跨日的时间（首页显示北京时间的日期）"""
    make_post(published_at=datetime(2025, 10, 21, 16, 30, tzinfo=timezone.utc))

    html = client.get("/").text

    assert "2025-10-22" in html
    assert "2025-10-21" not in html
