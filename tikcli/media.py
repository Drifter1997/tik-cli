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


def get_terminal_pixel_size() -> Tuple[int, int]:
    """
    Determine exact terminal pixel dimensions.
    Queries Sway window geometry on Wayland (eDP-1 / foot), accounting for window padding.
    """
    if os.environ.get("SWAYSOCK"):
        try:
            res = subprocess.run(["swaymsg", "-t", "get_tree"], capture_output=True, text=True, timeout=1)
            import json
            tree = json.loads(res.stdout)
            def find_foot(node):
                if node.get("app_id") == "foot" and node.get("visible", True):
                    return node
                for c in node.get("nodes", []) + node.get("floating_nodes", []):
                    f = find_foot(c)
                    if f:
                        return f
                return None
            foot_node = find_foot(tree)
            if foot_node:
                w_rect = foot_node.get("window_rect") or foot_node.get("rect")
                if w_rect and w_rect.get("width", 0) > 0 and w_rect.get("height", 0) > 0:
                    w = int(w_rect["width"])
                    h = int(w_rect["height"])
                    # Subtract Foot's 10x10 padding (20px total per axis) so video never overflows/scrolls
                    pad_x = 20 if w > 100 else 0
                    pad_y = 20 if h > 100 else 0
                    return max(320, w - pad_x), max(240, h - pad_y)
        except Exception:
            pass

    cols, rows = shutil.get_terminal_size((80, 24))
    return int(cols * 9.6), int(rows * 19.5)


def get_inline_thumbnail(image_url: str, max_width: int = THUMB_MAX_WIDTH, max_height: int = THUMB_MAX_HEIGHT) -> str:
    """Generate crisp TrueColor ANSI terminal thumbnail using chafa, cached in RAM."""
    if not image_url:
        return ""

    cache_key = f"{image_url}:{max_width}x{max_height}"
    if cache_key in _THUMBNAIL_CACHE:
        return _THUMBNAIL_CACHE[cache_key]

    raw_bytes = fetch_bytes_in_ram(image_url)
    if not raw_bytes:
        return ""

    try:
        # Run chafa with 24-bit TrueColor, clean half-block pixel grid, and optimal scale
        result = subprocess.run(
            [
                CHAFA_PATH,
                "-s", f"{max_width}x{max_height}",
                "--scale=max",
                "--format=symbols",
                "-c", "full",
                "--symbols=half",
                "--color-extractor=median",
                "--work=5",
                "--dither=none",
                "-"
            ],
            input=raw_bytes,
            capture_output=True,
            timeout=8
        )
        if result.returncode == 0 and result.stdout:
            raw_text = result.stdout.decode("utf-8", errors="replace")
            # Strip cursor hide/show sequences (\x1b[?25l / \x1b[?25h) so they don't break row alignments
            raw_text = re.sub(r'\x1b\[\?[0-9]+[hl]', '', raw_text)
            raw_lines = raw_text.splitlines()
            clean_lines = [line.rstrip() + "\033[0m" for line in raw_lines if line.strip()]
            rendered = "\n".join(clean_lines)
            _THUMBNAIL_CACHE[cache_key] = rendered
            return rendered
    except Exception:
        pass

    return ""


def play_feed_in_terminal(
    items: List[Dict[str, Any]],
    start_index: int = 0,
    vo_driver: Optional[str] = None
) -> Tuple[int, str]:
    """
    Play TikTok feed in terminal with native looping and next/prev scrolling:
    - Current video plays on continuous loop (just like TikTok app).
    - Down arrow / 'j' / PageDown: forwards to NEXT video and loops it.
    - Up arrow / 'k' / PageUp: goes back to PREVIOUS video and loops it.
    - ESC / 'q' / Ctrl+C: stops playback and returns to TUI at the current video position.
    """
    if not items:
        return start_index, "No videos in feed to play."

    if not shutil.which(MPV_PATH) and not Path(MPV_PATH).exists():
        return start_index, f"mpv player not found at '{MPV_PATH}'."

    from tikcli.config import DEFAULT_VO_DRIVER, RAM_DIR
    RAM_DIR.mkdir(parents=True, exist_ok=True)
    selected_driver = (vo_driver or DEFAULT_VO_DRIVER or "sixel").lower()

    # 1. Filter playable items and maintain index mapping
    valid_entries: List[Tuple[int, Dict[str, Any]]] = []
    for idx, v in enumerate(items):
        play_url = v.get("play_url") or v.get("web_url", "")
        if play_url:
            valid_entries.append((idx, v))

    if not valid_entries:
        return start_index, "No playable videos found in feed."

    # Find the M3U start index matching start_index
    m3u_start_idx = 0
    for m_idx, (orig_idx, _) in enumerate(valid_entries):
        if orig_idx == start_index:
            m3u_start_idx = m_idx
            break
        elif orig_idx < start_index:
            m3u_start_idx = m_idx

    m3u_file = RAM_DIR / "feed_playlist.m3u"
    m3u_lines = ["#EXTM3U"]
    for orig_idx, v in valid_entries:
        dur = v.get("duration", 0)
        author = v.get("author_id", "creator")
        title = (v.get("title") or f"TikTok by @{author}").replace("\n", " ")[:50]
        play_url = v.get("play_url") or v.get("web_url", "")
        m3u_lines.append(f"#EXTINF:{dur},@{author} - {title}")
        m3u_lines.append(play_url)

    m3u_file.write_text("\n".join(m3u_lines) + "\n")

    # 2. Input conf for TikTok-style scrolling & loop controls
    input_conf_file = RAM_DIR / "feed_input.conf"
    input_conf_content = (
        "j playlist-next\n"
        "DOWN playlist-next\n"
        "PGDWN playlist-next\n"
        "WHEEL_DOWN playlist-next\n"
        "k playlist-prev\n"
        "UP playlist-prev\n"
        "PGUP playlist-prev\n"
        "WHEEL_UP playlist-prev\n"
        "ESC quit 0\n"
        "q quit 0\n"
        "Ctrl+c quit 0\n"
        "SPACE cycle pause\n"
        "m cycle mute\n"
        "LEFT seek -5\n"
        "RIGHT seek 5\n"
    )
    input_conf_file.write_text(input_conf_content)

    # 3. Position tracking Lua script
    tracker_file = RAM_DIR / "last_pos.txt"
    if tracker_file.exists():
        try:
            tracker_file.unlink()
        except Exception:
            pass

    tracker_lua = RAM_DIR / "tracker.lua"
    lua_code = f"""
local current_pos = {m3u_start_idx}
mp.register_event("start-file", function()
    local pos = mp.get_property_number("playlist-pos", -1)
    if pos and pos >= 0 then
        current_pos = pos
        local f = io.open([[{str(tracker_file)}]], "w")
        if f then
            f:write(tostring(current_pos))
            f:close()
        end
    end
end)
"""
    tracker_lua.write_text(lua_code)

    term_size = shutil.get_terminal_size((80, 24))
    cols = term_size.columns
    rows = term_size.lines
    pixel_w, pixel_h = get_terminal_pixel_size()

    cmd = [
        MPV_PATH,
        "--no-config",
        "--force-window=no",
        "--loop-file=inf",             # Loop current video indefinitely!
        "--loop-playlist=inf",         # Continuous playlist navigation
        f"--playlist={m3u_file}",
        f"--playlist-start={m3u_start_idx}",
        f"--input-conf={input_conf_file}",
        f"--script={tracker_lua}",
        "--really-quiet",              # Prevent stdout text from interrupting and corrupting video frames
        "--terminal=no",               # Never interleave stdout terminal text with graphic escape sequences
        "--no-term-osd-bar",
        "--http-header-fields-append=Referer: https://www.tiktok.com/",
        "--http-header-fields-append=User-Agent: Mozilla/5.0 (X11; Linux x86_64)",
    ]

    if selected_driver == "sixel":
        # Dynamic high-fidelity Sixel graphics: no fixed palette, no dithering grains, full vertical height
        cmd.extend([
            "--vo=sixel",
            f"--vo-sixel-width={pixel_w}",
            f"--vo-sixel-height={pixel_h}",
            "--vo-sixel-fixedpalette=no",   # Dynamic adaptive palette: eliminates Windows 98 8-bit VGA look!
            "--vo-sixel-threshold=-1",      # Per-frame palette optimization for maximum color fidelity
            "--vo-sixel-reqcolors=256",     # Full 256 colors per frame
            "--vo-sixel-dither=none",       # Eradicate all dithering grain noise!
            "--vo-sixel-buffered=yes",
        ])
    else:
        # TrueColor text terminal fallback (16.7M 24-bit TrueColor)
        cmd.extend([
            "--vo=tct",
            f"--vo-tct-width={cols}",
            f"--vo-tct-height={rows}",
            "--vo-tct-algo=half-blocks",
            "--vo-tct-256=no",
        ])

    # Save alternate screen buffer and show cursor
    sys.stdout.write("\033[?1049h\033[2J\033[H\033[?25h")
    sys.stdout.flush()

    last_index = start_index
    try:
        proc = subprocess.run(cmd)
        if tracker_file.exists():
            try:
                val = int(tracker_file.read_text().strip())
                if 0 <= val < len(valid_entries):
                    last_index = valid_entries[val][0]
            except Exception:
                pass
        msg = "Returned to menu."
    except KeyboardInterrupt:
        if tracker_file.exists():
            try:
                val = int(tracker_file.read_text().strip())
                if 0 <= val < len(valid_entries):
                    last_index = valid_entries[val][0]
            except Exception:
                pass
        msg = "Playback stopped."
    except Exception as e:
        msg = f"Playback error: {e}"
    finally:
        sys.stdout.write("\033[?1049l\033[2J\033[H\033[?25l")
        sys.stdout.flush()

    return last_index, msg


def play_video_in_terminal(
    video_url: str,
    title: str = "",
    extra_headers: Optional[Dict[str, str]] = None,
    vo_driver: Optional[str] = None
) -> Tuple[bool, str]:
    """Single video playback helper (loops continuously until ESC/q)."""
    if not video_url:
        return False, "No video URL provided."
    single_item = [{"play_url": video_url, "title": title, "author_id": "tiktok", "duration": 0}]
    _, msg = play_feed_in_terminal(single_item, start_index=0, vo_driver=vo_driver)
    return True, msg




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
