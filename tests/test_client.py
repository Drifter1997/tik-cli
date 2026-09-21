import pytest
from tikcli.client import TikTokClient


def test_client_init():
    client = TikTokClient()
    assert client is not None
    assert client.session is not None


def test_check_session_without_file():
    client = TikTokClient()
    # If no session file exists
    res = client.check_session()
    assert "status" in res


def test_resolve_video_empty_url():
    client = TikTokClient()
    res = client.resolve_video_url("")
    assert res is None
