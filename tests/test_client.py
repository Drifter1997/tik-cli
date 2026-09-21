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


def test_search_videos_empty_query():
    client = TikTokClient()
    assert client.search_videos("") == []
    assert client.search_videos("   ") == []


def test_search_videos_url_routing(monkeypatch):
    client = TikTokClient()
    called = []
    def mock_resolve(url):
        called.append(url)
        return {"id": "123", "title": "test", "author_id": "tester"}
    monkeypatch.setattr(client, "resolve_video_url", mock_resolve)

    res = client.search_videos("https://www.tiktok.com/@tester/video/123")
    assert len(res) == 1
    assert res[0]["id"] == "123"
    assert len(called) == 1


def test_search_videos_creator_routing(monkeypatch):
    client = TikTokClient()
    called = []
    def mock_user_videos(username, count=20):
        called.append((username, count))
        return [{"id": "456", "title": "creator video", "author_id": username}]
    monkeypatch.setattr(client, "get_user_videos", mock_user_videos)

    res = client.search_videos("@tiktok", count=10)
    assert len(res) == 1
    assert res[0]["id"] == "456"
    assert called == [("tiktok", 10)]


def test_search_videos_keyword(monkeypatch):
    client = TikTokClient()
    def mock_urlebird(query, count=20):
        return [
            {"id": "789", "title": f"Video for {query}", "author_id": "artist", "source": "search"}
        ]
    monkeypatch.setattr(client, "_search_urlebird", mock_urlebird)

    res = client.search_videos("naat", count=5)
    assert len(res) == 1
    assert res[0]["id"] == "789"
    assert res[0]["source"] == "search"

