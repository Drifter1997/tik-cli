import pytest
from tikcli.media import _THUMBNAIL_CACHE, fetch_bytes_in_ram, get_inline_thumbnail


def test_thumbnail_cache_empty_url():
    res = get_inline_thumbnail("")
    assert res == ""


def test_thumbnail_caching():
    _THUMBNAIL_CACHE["mock_url:32x14"] = "MOCK_ANSI_RENDER\033[0m"
    res = get_inline_thumbnail("mock_url", max_width=32, max_height=14)
    assert res == "MOCK_ANSI_RENDER\033[0m"


def test_play_video_empty_url():
    from tikcli.media import play_video_in_terminal
    success, msg = play_video_in_terminal("")
    assert not success
    assert "No video URL" in msg


def test_get_terminal_pixel_size():
    from tikcli.media import get_terminal_pixel_size
    w, h = get_terminal_pixel_size()
    assert isinstance(w, int) and w > 0
    assert isinstance(h, int) and h > 0


def test_play_feed_empty_list():
    from tikcli.media import play_feed_in_terminal
    idx, msg = play_feed_in_terminal([], start_index=0)
    assert idx == 0
    assert "No videos" in msg


def test_play_feed_no_urls():
    from tikcli.media import play_feed_in_terminal
    items = [{"title": "No URL", "duration": 10}]
    idx, msg = play_feed_in_terminal(items, start_index=0)
    assert idx == 0
    assert "No playable videos" in msg


def test_strip_ansi_private_modes():
    from tikcli.ui import strip_ansi
    raw = "\x1b[?25l\x1b[38;2;254;44;85mText\x1b[0m\x1b[?25h"
    assert strip_ansi(raw) == "Text"


