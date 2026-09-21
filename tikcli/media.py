import os
import sys
import time
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import requests

from tikcli.config import (
    RAM_DIR,
    DOWNLOAD_DIR,
    MPV_PATH,
    CHAFA_PATH,
    IMV_PATH,
    YTDLP_PATH,
    THUMB_MAX_WIDTH,
    THUMB_MAX_HEIGHT,
)

# In-memory RAM cache for rendered ANSI thumbnails
_THUMBNAIL_CACHE: Dict[str, str] = {}


def fetch_bytes_in_ram(url: str, timeout: int = 15) -> Optional[bytes]:
    """Fetch media bytes directly into RAM memory without touching disk."""
    if not url:
        return None
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.tiktok.com/",
        }
        resp = requests.get(url, timeout=timeout, headers=headers)
        if resp.status_code == 200:
            return resp.content
    except Exception:
        pass
    return None


def get_inline_thumbnail(image_url: str, max_width: int = THUMB_MAX_WIDTH, max_height: int = THUMB_MAX_HEIGHT) -> str:
    """Generate ANSI terminal thumbnail using chafa, cached in RAM memory."""
    if not image_url:
        return ""

    cache_key = f"{image_url}:{max_width}x{max_height}"
    if cache_key in _THUMBNAIL_CACHE:
        return _THUMBNAIL_CACHE[cache_key]

    raw_bytes = fetch_bytes_in_ram(image_url)
    if not raw_bytes:
        return ""

    try:
        # Run chafa with input piped via stdin to keep 100% in RAM
        result = subprocess.run(
            [
                CHAFA_PATH,
                "-s", f"{max_width}x{max_height}",
                "--format=symbols",
                "--colors=256",
                "-"
            ],
            input=raw_bytes,
            capture_output=True,
            timeout=8
        )
        if result.returncode == 0 and result.stdout:
            rendered = result.stdout.decode("utf-8", errors="replace").rstrip("\n")
            _THUMBNAIL_CACHE[cache_key] = rendered
            return rendered
    except Exception:
        pass

    return ""


def play_video_in_terminal(video_url: str, title: str = "", extra_headers: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
    """
    Play video directly inside the terminal cells using mpv's sixel or tct (true-color) video driver.
    Ensures ZERO external popup windows.
    Zero disk clutter: streams directly over HTTPS via RAM.
    """
    if not video_url:
        return False, "No video URL provided."

    if not shutil.which(MPV_PATH) and not Path(MPV_PATH).exists():
        return False, f"mpv player not found at '{MPV_PATH}'."

    cmd = [
        MPV_PATH,
        "--vo=sixel,tct",         # Sixel if terminal supports it (e.g. foot), truecolor ANSI block fallback
        "--keep-open=no",          # Exit when playback finishes
        "--term-osd-bar",          # Show OSD seek bar in terminal
        "--msg-level=all=no",      # Suppress verbose log spam in terminal
        "--term-title=" + (f"tik-cli: {title[:40]}" if title else "tik-cli playback"),
    ]

    # Add custom HTTP headers if needed for direct CDN streams
    if extra_headers:
        header_str = ",".join([f"{k}: {v}" for k, v in extra_headers.items()])
        cmd.append(f"--http-header-fields={header_str}")
    else:
        cmd.append("--http-header-fields=Referer: https://www.tiktok.com/,User-Agent: Mozilla/5.0 (X11; Linux x86_64)")

    cmd.append(video_url)

    # Save alternate screen buffer and show cursor
    sys.stdout.write("\033[?1049h\033[2J\033[H\033[?25h")
    sys.stdout.flush()

    try:
        # Run mpv synchronously with inherited terminal stdio for interactive controls (Space, q, arrows)
        proc = subprocess.run(cmd)
        success = (proc.returncode == 0)
        msg = "Playback finished." if success else f"mpv exited with code {proc.returncode}."
    except KeyboardInterrupt:
        success = True
        msg = "Playback stopped by user."
    except Exception as e:
        success = False
        msg = f"Failed to play video: {e}"
    finally:
        # Restore alternate screen and clear terminal back for TUI
        sys.stdout.write("\033[?1049l\033[2J\033[H\033[?25l")
        sys.stdout.flush()

    return success, msg


def play_audio_in_terminal(audio_url: str, title: str = "") -> Tuple[bool, str]:
    """Play audio track in terminal without video display."""
    if not audio_url:
        return False, "No audio URL provided."

    cmd = [
        MPV_PATH,
        "--no-video",
        "--keep-open=no",
        "--term-osd-bar",
        audio_url
    ]

    sys.stdout.write("\033[?1049h\033[2J\033[H\033[?25h")
    sys.stdout.flush()

    try:
        proc = subprocess.run(cmd)
        success = (proc.returncode == 0)
        msg = "Audio playback finished." if success else f"mpv exited with code {proc.returncode}."
    except KeyboardInterrupt:
        success = True
        msg = "Audio playback stopped."
    except Exception as e:
        success = False
        msg = f"Failed to play audio: {e}"
    finally:
        sys.stdout.write("\033[?1049l\033[2J\033[H\033[?25l")
        sys.stdout.flush()

    return success, msg


def download_video(video_url: str, filename_prefix: str = "tiktok") -> Tuple[bool, str]:
    """
    Explicitly download a TikTok video to ~/Downloads/ (explicit command :d).
    Uses direct stream download or yt-dlp if needed.
    """
    try:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        clean_prefix = "".join(c for c in filename_prefix if c.isalnum() or c in ("-", "_")).strip()
        if not clean_prefix:
            clean_prefix = "video"
        dest_file = DOWNLOAD_DIR / f"{clean_prefix}_{timestamp}.mp4"

        # Check if video_url is a direct CDN mp4 link
        if video_url.startswith("http") and ("video" in video_url or "cdn" in video_url or "tikwm" in video_url):
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
                "Referer": "https://www.tiktok.com/",
            }
            with requests.get(video_url, headers=headers, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(dest_file, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
            return True, str(dest_file)

        # Fallback to yt-dlp if web URL
        if shutil.which(YTDLP_PATH):
            out_template = str(DOWNLOAD_DIR / f"{clean_prefix}_{timestamp}.%(ext)s")
            cmd = [
                YTDLP_PATH,
                "--no-playlist",
                "-o", out_template,
                video_url
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if res.returncode == 0:
                return True, f"Saved to {DOWNLOAD_DIR}"
            return False, f"yt-dlp error: {res.stderr[:100]}"

        return False, "Unable to download video."
    except Exception as e:
        return False, f"Download failed: {e}"


def download_audio(audio_url: str, filename_prefix: str = "tiktok_audio") -> Tuple[bool, str]:
    """Explicitly download an audio track to ~/Downloads/."""
    try:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        clean_prefix = "".join(c for c in filename_prefix if c.isalnum() or c in ("-", "_")).strip()
        dest_file = DOWNLOAD_DIR / f"{clean_prefix}_{timestamp}.mp3"

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
            "Referer": "https://www.tiktok.com/",
        }
        with requests.get(audio_url, headers=headers, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(dest_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
        return True, str(dest_file)
    except Exception as e:
        return False, f"Audio download failed: {e}"
