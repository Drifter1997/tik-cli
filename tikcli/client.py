import os
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

from tikcli.config import CONFIG_DIR, SESSION_FILE, DEVICE_FILE, DEFAULT_REGION, RAM_DIR


class TikTokClient:
    """
    TikTok Client supporting:
    1. Public Video Explorer (FYP, Trending, Creators, Direct URLs) - Zero login required.
    2. Optional Session Authentication via sessionid cookie.
    3. User profile details and DM access if authenticated.
    """

    def __init__(self):
        self.session = requests.Session()
        retries = Retry(
            total=4,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504, 520, 521, 522, 524, 531],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.user_id: Optional[str] = None
        self.username: Optional[str] = None
        self.nickname: Optional[str] = None
        self.avatar_url: Optional[str] = None

        self._load_saved_session()

    def _load_saved_session(self) -> bool:
        """Load saved session cookies from ~/.config/tik-cli/session.json if exists."""
        if not SESSION_FILE.exists():
            return False

        try:
            data = json.loads(SESSION_FILE.read_text())
            cookies = data.get("cookies", {})
            for name, val in cookies.items():
                self.session.cookies.set(name, val, domain=".tiktok.com")
            self.user_id = data.get("user_id")
            self.username = data.get("username")
            self.nickname = data.get("nickname")
            self.avatar_url = data.get("avatar_url")
            return True
        except Exception:
            return False

    def check_session(self) -> Dict[str, Any]:
        """Verify saved session status against TikTok passport API."""
        if not SESSION_FILE.exists():
            return {"status": "no_session"}

        try:
            resp = self.session.get("https://www.tiktok.com/passport/web/account/info/", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("message") == "success" and "data" in data:
                    user_data = data["data"]
                    self.user_id = str(user_data.get("user_id") or user_data.get("user_id_str"))
                    self.username = user_data.get("username") or self.username or "user"
                    self.nickname = user_data.get("screen_name") or self.nickname or self.username
                    self.avatar_url = user_data.get("avatar_url") or self.avatar_url
                    self.save_session()
                    return {
                        "status": "active",
                        "username": self.username,
                        "nickname": self.nickname,
                        "user_id": self.user_id
                    }
                else:
                    return {"status": "expired", "message": data.get("data", {}).get("description", "Session expired")}
            return {"status": "error", "message": f"HTTP {resp.status_code}"}
        except Exception as e:
            # If offline or network glitch but session file exists
            if self.username:
                return {"status": "active", "username": self.username, "cached": True}
            return {"status": "error", "message": str(e)}

    def is_logged_in(self) -> bool:
        """Boolean check for active authenticated session."""
        return self.user_id is not None and self.username is not None

    def save_session(self):
        """Save session cookies and info with secure 0600 permissions."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cookies_dict = self.session.cookies.get_dict()
        data = {
            "cookies": cookies_dict,
            "user_id": self.user_id,
            "username": self.username,
            "nickname": self.nickname,
            "avatar_url": self.avatar_url,
            "updated_at": int(time.time()),
        }
        SESSION_FILE.write_text(json.dumps(data, indent=2))
        try:
            os.chmod(SESSION_FILE, 0o600)
        except Exception:
            pass

    def login_by_sessionid(self, session_id: str, ttwid: Optional[str] = None) -> Dict[str, Any]:
        """
        Log in using sessionid cookie (and optional ttwid).
        Validates credentials without requiring username/password or browser automation.
        """
        clean_session = session_id.strip()
        self.session.cookies.clear()
        self.session.cookies.set("sessionid", clean_session, domain=".tiktok.com")
        if ttwid:
            self.session.cookies.set("ttwid", ttwid.strip(), domain=".tiktok.com")

        try:
            resp = self.session.get("https://www.tiktok.com/passport/web/account/info/", timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("message") == "success" and "data" in data:
                    user_data = data["data"]
                    self.user_id = str(user_data.get("user_id") or user_data.get("user_id_str"))
                    self.username = user_data.get("username") or "user"
                    self.nickname = user_data.get("screen_name") or self.username
                    self.avatar_url = user_data.get("avatar_url")
                    self.save_session()
                    return {
                        "success": True,
                        "message": f"Successfully authenticated as @{self.username} ({self.nickname}).",
                        "username": self.username,
                        "nickname": self.nickname,
                    }
                else:
                    err = data.get("data", {}).get("description", "Invalid or expired session cookie.")
                    return {"success": False, "message": f"Authentication failed: {err}"}
            return {"success": False, "message": f"Server returned HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "message": f"Connection error during login: {e}"}

    def logout(self) -> bool:
        """Remove saved session credentials."""
        try:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink()
            self.session.cookies.clear()
            self.user_id = None
            self.username = None
            self.nickname = None
            self.avatar_url = None
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Public Video Exploration (No login required)
    # -------------------------------------------------------------------------

    def get_feed(self, count: int = 20, region: str = DEFAULT_REGION) -> List[Dict[str, Any]]:
        """
        Fetch public Trending / For You Page (FYP) videos without requiring login.
        Uses resilient REST feed endpoints with automatic retries and RAM caching.
        """
        endpoints = [
            f"https://www.tikwm.com/api/feed/list?region={region}&count={count}",
            f"https://tikwm.com/api/feed/list?region={region}&count={count}",
            f"https://www.tikwm.com/api/feed/list?count={count}",
        ]

        feed_cache_file = RAM_DIR / "cached_feed.json"

        for url in endpoints:
            try:
                resp = self.session.get(url, timeout=12)
                if resp.status_code == 200:
                    body = resp.json()
                    items = body.get("data", [])
                    if items:
                        results = []
                        for item in items:
                            author = item.get("author", {})
                            author_id = author.get("unique_id", "") or "creator"
                            video_id = str(item.get("id") or item.get("video_id") or "")
                            web_url = f"https://www.tiktok.com/@{author_id}/video/{video_id}"

                            # Extract best cover
                            cover = (
                                item.get("cover")
                                or item.get("origin_cover")
                                or item.get("ai_dynamic_cover")
                                or ""
                            )

                            # Extract images if photo-mode post
                            images = item.get("images") or []
                            is_photo = bool(images)

                            # Extract best direct stream
                            play_url = item.get("play") or item.get("wmplay") or web_url

                            music_info = item.get("music_info", {})
                            music_title = music_info.get("title") or "Original Sound"
                            music_author = music_info.get("author") or author.get("nickname", "")
                            music_url = music_info.get("play") or item.get("music") or ""

                            results.append({
                                "id": video_id,
                                "title": item.get("title", "").strip() or f"Video by @{author_id}",
                                "author_id": author_id,
                                "author_name": author.get("nickname") or author_id,
                                "author_avatar": author.get("avatar", ""),
                                "cover_url": cover,
                                "play_url": play_url,
                                "web_url": web_url,
                                "music_title": f"{music_title} - {music_author}",
                                "music_url": music_url,
                                "duration": int(item.get("duration") or 0),
                                "views": int(item.get("play_count") or 0),
                                "likes": int(item.get("digg_count") or 0),
                                "comments": int(item.get("comment_count") or 0),
                                "shares": int(item.get("share_count") or 0),
                                "images": images,
                                "is_photo": is_photo,
                                "source": "feed",
                            })
                        # Cache successful feed
                        try:
                            feed_cache_file.write_text(json.dumps(results))
                        except Exception:
                            pass
                        return results
            except Exception:
                continue

        # If network failed on all endpoints, fall back to cached feed if available
        if feed_cache_file.exists():
            try:
                cached = json.loads(feed_cache_file.read_text())
                if isinstance(cached, list) and cached:
                    return cached
            except Exception:
                pass

        return []

    def get_user_videos(self, username: str, count: int = 20) -> List[Dict[str, Any]]:
        """
        Fetch recent videos of any creator (@username) without requiring login.
        Uses yt-dlp's native extractor.
        """
        clean_user = username.lstrip("@").strip()
        if not clean_user:
            return []

        user_url = f"https://www.tiktok.com/@{clean_user}"

        if yt_dlp is None:
            return []

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlist_items": f"1-{count}",
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(user_url, download=False)
                if not info:
                    return []

                entries = info.get("entries") or []
                results = []
                for e in entries:
                    if not e:
                        continue
                    video_id = str(e.get("id") or "")
                    web_url = e.get("url") or f"https://www.tiktok.com/@{clean_user}/video/{video_id}"

                    # Extract thumbnail
                    thumbs = e.get("thumbnails") or []
                    cover_url = ""
                    if thumbs:
                        cover_url = thumbs[-1].get("url") or ""
                    elif e.get("thumbnail"):
                        cover_url = e.get("thumbnail")

                    results.append({
                        "id": video_id,
                        "title": (e.get("title") or e.get("description") or f"Video by @{clean_user}").strip(),
                        "author_id": clean_user,
                        "author_name": e.get("uploader") or clean_user,
                        "author_avatar": "",
                        "cover_url": cover_url,
                        "play_url": web_url,  # mpv plays web_url directly via yt-dlp
                        "web_url": web_url,
                        "music_title": e.get("track") or "Original Sound",
                        "music_url": "",
                        "duration": int(e.get("duration") or 0),
                        "views": int(e.get("view_count") or 0),
                        "likes": int(e.get("like_count") or 0),
                        "comments": int(e.get("comment_count") or 0),
                        "shares": int(e.get("repost_count") or 0),
                        "source": "creator",
                    })
                return results
        except Exception:
            pass

        return []

    def resolve_video_url(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a single TikTok video from standard link or shortlink.
        Returns full stream URL and metadata.
        """
        clean_url = url.strip()
        if not clean_url:
            return None

        # Try fast TikWM POST resolution with retry session
        for post_api in ("https://www.tikwm.com/api/", "https://tikwm.com/api/"):
            try:
                resp = self.session.post(
                    post_api,
                    data={"url": clean_url},
                    timeout=10,
                )
                if resp.status_code == 200:
                    body = resp.json()
                    if body.get("code") == 0 and "data" in body:
                        data = body["data"]
                        images = data.get("images") or []
                        is_photo = bool(images)
                        author = data.get("author", {})
                        author_id = author.get("unique_id", "") or "creator"
                        video_id = str(data.get("id") or "")
                        music_info = data.get("music_info", {})

                        return {
                            "id": video_id,
                            "title": data.get("title", "").strip() or f"Video by @{author_id}",
                            "author_id": author_id,
                            "author_name": author.get("nickname") or author_id,
                            "author_avatar": author.get("avatar", ""),
                            "cover_url": data.get("cover") or data.get("origin_cover") or "",
                            "play_url": data.get("play") or data.get("wmplay") or clean_url,
                            "web_url": clean_url,
                            "music_title": music_info.get("title") or "Original Sound",
                            "music_url": music_info.get("play") or "",
                            "duration": int(data.get("duration") or 0),
                            "views": int(data.get("play_count") or 0),
                            "likes": int(data.get("digg_count") or 0),
                            "comments": int(data.get("comment_count") or 0),
                            "shares": int(data.get("share_count") or 0),
                            "images": images,
                            "is_photo": is_photo,
                            "source": "direct",
                        }
            except Exception:
                continue

        # Fallback to yt-dlp info extractor
        if yt_dlp:
            try:
                with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                    e = ydl.extract_info(clean_url, download=False)
                    if e:
                        author_id = e.get("uploader_id") or e.get("uploader") or "creator"
                        thumbs = e.get("thumbnails") or []
                        cover_url = thumbs[-1].get("url") if thumbs else (e.get("thumbnail") or "")
                        formats = e.get("formats") or []
                        play_url = formats[-1].get("url") if formats else clean_url

                        return {
                            "id": str(e.get("id") or ""),
                            "title": (e.get("title") or e.get("description") or f"Video by @{author_id}").strip(),
                            "author_id": author_id,
                            "author_name": e.get("uploader") or author_id,
                            "author_avatar": "",
                            "cover_url": cover_url,
                            "play_url": play_url,
                            "web_url": clean_url,
                            "music_title": e.get("track") or "Original Sound",
                            "music_url": "",
                            "duration": int(e.get("duration") or 0),
                            "views": int(e.get("view_count") or 0),
                            "likes": int(e.get("like_count") or 0),
                            "comments": int(e.get("comment_count") or 0),
                            "shares": int(e.get("repost_count") or 0),
                            "source": "direct",
                        }
            except Exception:
                pass

        return None

    # -------------------------------------------------------------------------
    # Direct Messages (Authenticated only)
    # -------------------------------------------------------------------------

    def get_direct_messages(self) -> List[Dict[str, Any]]:
        """
        Fetch user DM conversations when logged in with session cookie.
        Returns list of thread items.
        """
        if not self.is_logged_in():
            return []

        # TikTok Web IM uses internal passport / web endpoints
        url = "https://www.tiktok.com/api/v1/web/im/chat/list/"
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                threads = data.get("data", {}).get("conversations", [])
                results = []
                for th in threads:
                    results.append({
                        "id": str(th.get("id")),
                        "title": th.get("name") or "Direct Message",
                        "last_message": th.get("last_message", {}).get("text", ""),
                        "last_time": th.get("last_message_time", 0),
                    })
                return results
        except Exception:
            pass

        return []

    def send_direct_message(self, recipient_id: str, text: str) -> Dict[str, Any]:
        """Send a direct message if logged in."""
        if not self.is_logged_in():
            return {"success": False, "message": "Login required for sending direct messages."}

        url = "https://www.tiktok.com/api/v1/web/im/message/send/"
        try:
            resp = self.session.post(url, json={"recipient_id": recipient_id, "text": text}, timeout=10)
            if resp.status_code == 200:
                return {"success": True, "message": "Message sent."}
            return {"success": False, "message": f"Failed with HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
