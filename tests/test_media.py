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
