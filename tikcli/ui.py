import os
import sys
import re
import time
import shutil
import select
import termios
import tty
import atexit
from typing import Optional, List, Dict, Any, Callable

from tikcli.config import (
    CONFIG_DIR,
    DOWNLOAD_DIR,
    RAM_DIR,
    THUMB_MAX_WIDTH,
    THUMB_MAX_HEIGHT,
    DEFAULT_VO_DRIVER,
)
from tikcli.client import TikTokClient
from tikcli.media import (
    get_inline_thumbnail,
    play_feed_in_terminal,
    play_video_in_terminal,
    play_audio_in_terminal,
    download_video,
    download_audio,
)

# ANSI Styling (TikTok Aesthetic: Cyan, Neon Red/Pink, Dark Background)
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"

RED = "\033[38;2;254;44;85m"       # TikTok Red / Neon Pink
CYAN = "\033[38;2;37;244;238m"     # TikTok Cyan
WHITE = "\033[97m"
GRAY = "\033[90m"
LIGHT_GRAY = "\033[37m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"

BG_HEADER = "\033[48;5;235m"
BG_ACTIVE = "\033[48;5;238m"
BG_STATUS = "\033[48;5;236m"
BG_CYAN = "\033[48;2;37;244;238m"
BG_RED = "\033[48;2;254;44;85m"


_key_buffer: List[str] = []


ANSI_REGEX = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences for accurate visible string length measuring."""
    return ANSI_REGEX.sub('', text)


class RawTerminal:
    """Context manager for terminal raw/cbreak mode with SGR mouse tracking."""
    def __init__(self, enable_mouse: bool = True):
        self.fd = sys.stdin.fileno() if sys.stdin.isatty() else None
        self.old_settings = None
        self.enable_mouse = enable_mouse

    def __enter__(self):
        if self.fd is not None:
            self.old_settings = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
            if self.enable_mouse:
                # Enable button reporting and SGR extended coordinates for mouse/touchpad scrolling
                sys.stdout.write("\033[?1000h\033[?1006h\033[?25l")
                sys.stdout.flush()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd is not None:
            if self.enable_mouse:
                sys.stdout.write("\033[?1000l\033[?1006l\033[?25h\033[0m")
                sys.stdout.flush()
            if self.old_settings is not None:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)


def parse_input_bytes(data: bytes) -> List[str]:
    """Parse low-level terminal bytes into keys and mouse events."""
    events = []
    i = 0
    n = len(data)
    while i < n:
        if data[i:i+1] == b'\x1b':
            rest = data[i:]
            # 1. SGR Mouse: \x1b[<(\d+);(\d+);(\d+)([Mm])
            m = re.match(rb'^\x1b\[<(\d+);(\d+);(\d+)([Mm])', rest)
            if m:
                btn = int(m.group(1))
                if btn == 64:
                    events.append("MOUSE_UP")
                elif btn == 65:
                    events.append("MOUSE_DOWN")
                i += len(m.group(0))
                continue

            # 2. Legacy X10 Mouse: \x1b[M(btn)(x)(y)
            if rest.startswith(b'\x1b[M') and len(rest) >= 6:
                cb = rest[3] - 32
                if cb == 64:
                    events.append("MOUSE_UP")
                elif cb == 65:
                    events.append("MOUSE_DOWN")
                i += 6
                continue

            # 3. Arrow Keys: \x1b[A, \x1bOA, etc.
            m = re.match(rb'^\x1b(\[|O)(?:[0-9;]*)([A-D])', rest)
            if m:
                code = m.group(2)
                mapping = {b'A': 'UP', b'B': 'DOWN', b'C': 'RIGHT', b'D': 'LEFT'}
                events.append(mapping.get(code, 'UNKNOWN'))
                i += len(m.group(0))
                continue

            # 4. PageUp / PageDown
            m = re.match(rb'^\x1b\[([0-9;]*)~', rest)
            if m:
                num = m.group(1)
                if num.startswith(b'5'):
                    events.append('PAGE_UP')
                elif num.startswith(b'6'):
                    events.append('PAGE_DOWN')
                i += len(m.group(0))
                continue

            # Standalone ESC
            if len(rest) == 1:
                events.append('ESC')
                i += 1
                continue

            # Skip other escape sequences safely
            if rest.startswith(b'\x1b[') or rest.startswith(b'\x1bO'):
                end_pos = 2
                while end_pos < len(rest) and not (rest[end_pos:end_pos+1].isalpha() or rest[end_pos:end_pos+1] == b'~'):
                    end_pos += 1
                if end_pos < len(rest):
                    end_pos += 1
                i += end_pos
                continue

            events.append('ESC')
            i += 1

        elif data[i:i+1] in (b'\r', b'\n'):
            events.append('ENTER')
            i += 1
        elif data[i:i+1] == b'\t':
            events.append('TAB')
            i += 1
        elif data[i:i+1] in (b'\x7f', b'\x08'):
            events.append('BACKSPACE')
            i += 1
        elif data[i:i+1] == b'\x03':
            events.append('CTRL_C')
            i += 1
        elif data[i:i+1] == b'\x15':
            events.append('CTRL_U')
            i += 1
        else:
            try:
                ch = data[i:i+1].decode('utf-8')
                events.append(ch)
            except UnicodeDecodeError:
                pass
            i += 1
    return events


def read_key(timeout: float = 0.05) -> Optional[str]:
    """Read a key with timeout."""
    global _key_buffer
    if _key_buffer:
        return _key_buffer.pop(0)

    if not sys.stdin.isatty():
        return None

    fd = sys.stdin.fileno()
    r, _, _ = select.select([fd], [], [], timeout)
    if not r:
        return None

    try:
        data = os.read(fd, 1024)
        if not data:
            return None
        _key_buffer.extend(parse_input_bytes(data))
        if _key_buffer:
            return _key_buffer.pop(0)
    except Exception:
        return None

    return None


def format_count(n: int) -> str:
    """Format large numbers nicely (e.g. 1.2M, 45.3K)."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def format_duration(seconds: int) -> str:
    """Format duration in M:SS."""
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


class TerminalUI:
    """Interactive Neovim-style Terminal UI for TikTok."""

    def __init__(self, client: TikTokClient):
        self.client = client
        self.running = True

        # Navigation state
        self.mode = "feed"  # "feed", "creator", "dms"
        self.feed_items: List[Dict[str, Any]] = []
        self.feed_index = 0
        self.creator_items: List[Dict[str, Any]] = []
        self.creator_index = 0
        self.current_creator = "tiktok"
        self.dms_items: List[Dict[str, Any]] = []
        self.dms_index = 0

        # Command & Search input prompt state
        self.input_mode = False
        self.input_prompt = ""
        self.input_buffer = ""
        self.input_action: Optional[Callable[[str], None]] = None

        # Status notification
        self.status_message = "Ready. Press Enter to play in terminal."
        self.status_time = time.time()
        self.status_color = GREEN

        # Cached thumbnails
        self._thumbnail_cache: Dict[str, List[str]] = {}

        # Video driver selection (tct or sixel)
        self.vo_driver = DEFAULT_VO_DRIVER
        self.force_clear = True

        atexit.register(self._cleanup_terminal)

    def _cleanup_terminal(self):
        sys.stdout.write("\033[?1000l\033[?1006l\033[?25h\033[0m")
        sys.stdout.flush()

    def set_status(self, msg: str, color: str = GREEN):
        self.status_message = msg
        self.status_time = time.time()
        self.status_color = color

    def run(self):
        """Main UI event loop."""
        # Initial silent session check
        sess = self.client.check_session()
        if sess["status"] == "active":
            self.set_status(f"Authenticated as @{sess.get('username')}", GREEN)
        else:
            self.set_status("Guest Mode (No login required). Loading trending feed...", CYAN)

        # Initial feed load
        self.load_feed()

        with RawTerminal(enable_mouse=True):
            while self.running:
                self.draw()
                key = read_key(timeout=0.08)
                if key:
                    self.handle_input(key)

    def load_feed(self):
        """Fetch trending / FYP feed."""
        self.set_status("Fetching trending TikTok feed...", CYAN)
        items = self.client.get_feed(count=25)
        if items:
            self.feed_items = items
            self.feed_index = min(self.feed_index, len(self.feed_items) - 1)
            self.set_status(f"Loaded {len(items)} trending videos.", GREEN)
        else:
            self.set_status("Failed to load trending feed. Check network.", RED)

    def load_creator(self, username: str):
        """Fetch videos for specific creator."""
        clean_user = username.lstrip("@").strip()
        if not clean_user:
            return
        self.current_creator = clean_user
        self.set_status(f"Loading videos for @{clean_user} via yt-dlp...", CYAN)
        self.draw()
        items = self.client.get_user_videos(clean_user, count=25)
        if items:
            self.creator_items = items
            self.creator_index = 0
            self.mode = "creator"
            self.set_status(f"Loaded {len(items)} videos for @{clean_user}.", GREEN)
        else:
            self.set_status(f"No videos found for @{clean_user}.", YELLOW)

    def load_direct_url(self, url: str):
        """Resolve a direct TikTok video URL."""
        self.set_status("Resolving video URL...", CYAN)
        self.draw()
        video = self.client.resolve_video_url(url)
        if video:
            self.feed_items.insert(0, video)
            self.feed_index = 0
            self.mode = "feed"
            self.set_status(f"Loaded video by @{video.get('author_id')}.", GREEN)
        else:
            self.set_status("Could not resolve video URL.", RED)

    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------

    def draw(self):
        """Render complete screen buffer."""
        term_size = shutil.get_terminal_size((80, 24))
        cols = term_size.columns
        lines = term_size.lines

        buf = []
        if getattr(self, "force_clear", False):
            buf.append("\033[2J")
            self.force_clear = False
        buf.append("\033[H")  # Move to top-left

        # 1. Header
        header_lines = self.render_header(cols)
        buf.extend(header_lines)

        # 2. Main Content Area
        avail_height = max(10, lines - len(header_lines) - 3)
        content_lines = self.render_content(cols, avail_height)
        buf.extend(content_lines)

        # 3. Footer / Status bar
        footer_lines = self.render_footer(cols)
        buf.extend(footer_lines)

        sys.stdout.write("".join(buf))
        sys.stdout.flush()

    def render_header(self, width: int) -> List[str]:
        lines = []

        # Logo and Title
        logo = f"{CYAN}{BOLD}tik{RESET}{RED}{BOLD}-cli{RESET}"
        auth_badge = (
            f"{GREEN}● @{self.client.username}{RESET}"
            if self.client.is_logged_in()
            else f"{GRAY}○ Guest Mode{RESET}"
        )

        title_bar = f" {logo} {GRAY}│{RESET} {DIM}Terminal TikTok Client{RESET}"
        gap = width - len(strip_ansi(title_bar)) - len(strip_ansi(auth_badge)) - 2
        lines.append(f"{BG_HEADER}{title_bar}{' ' * max(1, gap)}{auth_badge} {RESET}\n")

        # Mode Tab Bar
        tab_feed = f"{BOLD}{CYAN}[1] 🔥 For You / Trending{RESET}" if self.mode == "feed" else f"{GRAY}[1] For You{RESET}"
        tab_creator = f"{BOLD}{CYAN}[2] 👤 Creator (@{self.current_creator}){RESET}" if self.mode == "creator" else f"{GRAY}[2] Creator{RESET}"
        tab_dms = f"{BOLD}{CYAN}[3] 💬 Direct Messages{RESET}" if self.mode == "dms" else f"{GRAY}[3] Messages{RESET}"

        tabs_str = f"  {tab_feed}    {tab_creator}    {tab_dms}"
        lines.append(f"{tabs_str}\n")
        lines.append(f"{GRAY}{'─' * width}{RESET}\n")
        return lines

    def render_content(self, width: int, height: int) -> List[str]:
        if self.mode == "dms":
            return self.render_dms(width, height)

        # Split into Left List (55%) and Right Preview (45%)
        left_w = max(35, int(width * 0.52))
        right_w = max(30, width - left_w - 3)

        items = self.feed_items if self.mode == "feed" else self.creator_items
        selected_idx = self.feed_index if self.mode == "feed" else self.creator_index

        left_lines = self.render_video_list(items, selected_idx, left_w, height)
        selected_video = items[selected_idx] if (items and selected_idx < len(items)) else None
        right_lines = self.render_preview(selected_video, right_w, height)

        combined = []
        for i in range(height):
            l_str = left_lines[i] if i < len(left_lines) else " " * left_w
            r_str = right_lines[i] if i < len(right_lines) else " " * right_w
            # Clear to end of line (\033[K) to avoid ghosting artifacts
            combined.append(f"{l_str} {GRAY}│{RESET} {r_str}\033[K\n")

        return combined

    def render_video_list(self, items: List[Dict[str, Any]], selected: int, width: int, height: int) -> List[str]:
        lines = []
        if not items:
            lines.append(f"{DIM}  No videos loaded. Press 'r' to refresh or '/' to search.{RESET}".ljust(width))
            while len(lines) < height:
                lines.append(" " * width)
            return lines

        # Scrolling window calculation
        scroll_start = 0
        if selected >= height:
            scroll_start = selected - height + 1
        visible_items = items[scroll_start:scroll_start + height]

        for i, item in enumerate(visible_items):
            real_idx = scroll_start + i
            is_active = (real_idx == selected)

            marker = f"{CYAN}▶{RESET}" if is_active else " "
            author = f"@{item.get('author_id', 'unknown')[:14]}"
            dur = format_duration(item.get("duration", 0))
            likes = format_count(item.get("likes", 0))

            title = item.get("title", "").replace("\n", " ")
            max_title_len = max(10, width - len(author) - len(dur) - len(likes) - 10)
            if len(title) > max_title_len:
                title = title[:max_title_len - 1] + "…"

            if is_active:
                row = (
                    f"{marker} {BOLD}{WHITE}{title}{RESET} "
                    f"{CYAN}{author}{RESET} {RED}♥{likes}{RESET} {DIM}{dur}{RESET}"
                )
                bg_colored = f"{BG_ACTIVE}{row}{' ' * max(0, width - len(strip_ansi(row)))}{RESET}"
                lines.append(bg_colored)
            else:
                row = (
                    f"{marker} {LIGHT_GRAY}{title}{RESET} "
                    f"{GRAY}{author}{RESET} {DIM}♥{likes} {dur}{RESET}"
                )
                lines.append(f"{row}{' ' * max(0, width - len(strip_ansi(row)))}")

        while len(lines) < height:
            lines.append(" " * width)

        return lines

    def render_preview(self, video: Optional[Dict[str, Any]], width: int, height: int) -> List[str]:
        lines = []
        if not video:
            lines.append(f"{DIM}Select a video to preview.{RESET}".ljust(width))
            while len(lines) < height:
                lines.append(" " * width)
            return lines

        # 1. Inline Thumbnail via chafa in RAM
        cover_url = video.get("cover_url", "")
        thumb_h = max(12, min(26, height - 7))
        thumb_w = min(width - 2, 48)

        if cover_url:
            cache_key = f"{cover_url}:{thumb_w}x{thumb_h}"
            if cache_key not in self._thumbnail_cache:
                rendered = get_inline_thumbnail(cover_url, max_width=thumb_w, max_height=thumb_h)
                self._thumbnail_cache[cache_key] = rendered.split("\n") if rendered else []
            thumb_lines = self._thumbnail_cache[cache_key]
            for t_line in thumb_lines[:thumb_h]:
                vis_len = len(strip_ansi(t_line))
                margin_left = max(0, (width - vis_len) // 2)
                margin_right = max(0, width - vis_len - margin_left)
                lines.append(f"{' ' * margin_left}{t_line}{RESET}{' ' * margin_right}")
        else:
            no_thumb = f"{DIM}[No thumbnail available]{RESET}"
            vis_len = len(strip_ansi(no_thumb))
            margin_left = max(0, (width - vis_len) // 2)
            margin_right = max(0, width - vis_len - margin_left)
            lines.append(f"{' ' * margin_left}{no_thumb}{' ' * margin_right}")

        lines.append(" " * width)

        # 2. Author and stats
        author_name = video.get("author_name") or video.get("author_id", "Creator")
        author_line = f"  {BOLD}{WHITE}{author_name}{RESET} {CYAN}@{video.get('author_id')}{RESET}"
        pad = " " * max(0, width - len(strip_ansi(author_line)))
        lines.append(f"{author_line}{pad}")

        stats_row = (
            f"  {RED}♥ {format_count(video.get('likes', 0))}{RESET}   "
            f"{CYAN}▶ {format_count(video.get('views', 0))}{RESET}   "
            f"{YELLOW}💬 {format_count(video.get('comments', 0))}{RESET}   "
            f"{DIM}⏱ {format_duration(video.get('duration', 0))}{RESET}"
        )
        pad = " " * max(0, width - len(strip_ansi(stats_row)))
        lines.append(f"{stats_row}{pad}")

        # 3. Title / Caption
        title = video.get("title", "").strip()
        lines.append(f"  {DIM}Caption:{RESET}".ljust(width))
        wrapped = [title[j:j + width - 6] for j in range(0, min(160, len(title)), max(1, width - 6))]
        for w in wrapped[:3]:
            cap_line = f"    {LIGHT_GRAY}{w}{RESET}"
            pad = " " * max(0, width - len(strip_ansi(cap_line)))
            lines.append(f"{cap_line}{pad}")

        # 4. Music Track
        music = video.get("music_title", "").strip()
        if music:
            music_line = f"  {DIM}Sound:{RESET} 🎵 {music[:max(10, width - 14)]}"
            pad = " " * max(0, width - len(strip_ansi(music_line)))
            lines.append(f"{music_line}{pad}")

        while len(lines) < height:
            lines.append(" " * width)

        return lines

    def render_dms(self, width: int, height: int) -> List[str]:
        lines = []
        if not self.client.is_logged_in():
            lines.append("")
            lines.append(f"{YELLOW}{BOLD}  🔒 Authentication Required for Direct Messages{RESET}")
            lines.append(f"{DIM}  Video exploring and streaming require NO login.{RESET}")
            lines.append(f"{DIM}  To use Direct Messages, you can optionally log in with your sessionid cookie.{RESET}")
            lines.append("")
            lines.append(f"  Commands:")
            lines.append(f"    {BOLD}:login{RESET}   - Enter sessionid cookie")
            lines.append(f"    {BOLD}Tab{RESET}      - Switch back to Video Feed")
            while len(lines) < height:
                lines.append(" " * width)
            return lines

        lines.append(f"{BOLD}Direct Messages for @{self.client.username}:{RESET}")
        if not self.dms_items:
            lines.append(f"{DIM}  No conversations found.{RESET}")
        else:
            for i, th in enumerate(self.dms_items[:height - 2]):
                marker = f"{CYAN}▶{RESET}" if i == self.dms_index else " "
                lines.append(f"{marker} {BOLD}{th.get('title')}{RESET}: {th.get('last_message', '')[:width - 30]}")

        while len(lines) < height:
            lines.append(" " * width)
        return lines

    def render_footer(self, width: int) -> List[str]:
        lines = []
        lines.append(f"{GRAY}{'─' * width}{RESET}\n")

        if self.input_mode:
            # Active command/search input bar
            prompt_str = f"{CYAN}{BOLD}{self.input_prompt}{RESET}{self.input_buffer}{CYAN}█{RESET}"
            lines.append(f"{prompt_str}\n")
        else:
            # Controls and Dynamic Status bar
            shortcuts = (
                f"{BOLD}[Enter]{RESET} Watch (Loop/Scroll)  "
                f"{BOLD}[:d]{RESET} Download  "
                f"{BOLD}[:m]{RESET} Audio  "
                f"{BOLD}[/]{RESET} Search/@  "
                f"{BOLD}[Tab]{RESET} Mode  "
                f"{BOLD}[:q]{RESET} Quit"
            )
            status = f"{self.status_color}{self.status_message}{RESET}"
            lines.append(f"{shortcuts}\n")
            lines.append(f"{BG_STATUS} {status}{' ' * max(0, width - len(strip_ansi(status)) - 2)} {RESET}\n")

        return lines

    # -------------------------------------------------------------------------
    # Input & Action Handling
    # -------------------------------------------------------------------------

    def handle_input(self, key: str):
        if self.input_mode:
            self.handle_input_mode(key)
            return

        # Navigation
        if key in ("UP", "k"):
            if self.mode == "feed" and self.feed_items:
                self.feed_index = max(0, self.feed_index - 1)
            elif self.mode == "creator" and self.creator_items:
                self.creator_index = max(0, self.creator_index - 1)
            elif self.mode == "dms" and self.dms_items:
                self.dms_index = max(0, self.dms_index - 1)
        elif key in ("DOWN", "j"):
            if self.mode == "feed" and self.feed_items:
                self.feed_index = min(len(self.feed_items) - 1, self.feed_index + 1)
            elif self.mode == "creator" and self.creator_items:
                self.creator_index = min(len(self.creator_items) - 1, self.creator_index + 1)
            elif self.mode == "dms" and self.dms_items:
                self.dms_index = min(len(self.dms_items) - 1, self.dms_index + 1)
        elif key in ("PAGE_UP", "MOUSE_UP"):
            if self.mode == "feed":
                self.feed_index = max(0, self.feed_index - 5)
            elif self.mode == "creator":
                self.creator_index = max(0, self.creator_index - 5)
        elif key in ("PAGE_DOWN", "MOUSE_DOWN"):
            if self.mode == "feed":
                self.feed_index = min(len(self.feed_items) - 1, self.feed_index + 5)
            elif self.mode == "creator":
                self.creator_index = min(len(self.creator_items) - 1, self.creator_index + 5)
        elif key == "TAB":
            # Cycle modes
            modes = ["feed", "creator", "dms"]
            idx = modes.index(self.mode)
            self.mode = modes[(idx + 1) % len(modes)]
            self.set_status(f"Switched to {self.mode.upper()} mode.", CYAN)
        elif key in ("1",):
            self.mode = "feed"
        elif key in ("2",):
            self.mode = "creator"
        elif key in ("3",):
            self.mode = "dms"
        elif key == "ENTER":
            self.action_play_selected()
        elif key == "r":
            self.load_feed()
        elif key == "/":
            self.start_search_prompt()
        elif key == ":":
            self.start_command_prompt()
        elif key == "CTRL_C" or key in (":q", "q"):
            self.running = False

    def handle_input_mode(self, key: str):
        if key == "ENTER":
            val = self.input_buffer.strip()
            self.input_mode = False
            self.input_buffer = ""
            if self.input_action:
                self.input_action(val)
        elif key == "ESC":
            self.input_mode = False
            self.input_buffer = ""
            self.set_status("Cancelled.", YELLOW)
        elif key == "BACKSPACE":
            self.input_buffer = self.input_buffer[:-1]
        elif key == "CTRL_U":
            self.input_buffer = ""
        elif len(key) == 1 and key.isprintable():
            self.input_buffer += key

    def start_search_prompt(self):
        self.input_mode = True
        self.input_prompt = "Search creator (@handle) or paste TikTok URL: "
        self.input_buffer = ""

        def on_submit(val: str):
            if not val:
                return
            if val.startswith("http://") or val.startswith("https://"):
                self.load_direct_url(val)
            else:
                self.load_creator(val)

        self.input_action = on_submit

    def start_command_prompt(self):
        self.input_mode = True
        self.input_prompt = ":"
        self.input_buffer = ""

        def on_submit(cmd: str):
            cmd = cmd.strip()
            if cmd in ("q", "quit", "exit"):
                self.running = False
            elif cmd in ("d", "download"):
                self.action_download_selected()
            elif cmd in ("m", "audio"):
                self.action_audio_selected()
            elif cmd.startswith("user ") or cmd.startswith("creator "):
                user = cmd.split(" ", 1)[1]
                self.load_creator(user)
            elif cmd.startswith("vo "):
                driver = cmd.split(" ", 1)[1].strip().lower()
                if driver in ("tct", "sixel"):
                    self.vo_driver = driver
                    self.set_status(f"Video driver set to '{driver.upper()}'.", GREEN)
                else:
                    self.set_status("Invalid driver. Use ':vo tct' or ':vo sixel'.", RED)
            elif cmd == "login":
                self.start_login_flow()
            elif cmd == "logout":
                self.client.logout()
                self.set_status("Logged out. Switched to Guest Mode.", YELLOW)
            elif cmd == "help":
                self.set_status("Keys: Enter=play, :d=download, :m=audio, :vo tct|sixel, /=search, :q=quit", CYAN)
            elif cmd:
                self.set_status(f"Unknown command: :{cmd}", RED)

        self.input_action = on_submit

    def start_login_flow(self):
        self.input_mode = True
        self.input_prompt = "Enter sessionid cookie: "
        self.input_buffer = ""

        def on_session_entered(session_id: str):
            if not session_id:
                self.set_status("Login cancelled.", YELLOW)
                return
            self.set_status("Verifying session cookie with TikTok...", CYAN)
            self.draw()
            res = self.client.login_by_sessionid(session_id)
            if res["success"]:
                self.set_status(f"✓ {res['message']}", GREEN)
            else:
                self.set_status(f"✗ {res['message']}", RED)

        self.input_action = on_session_entered

    # -------------------------------------------------------------------------
    # Actions: Play, Download, Audio
    # -------------------------------------------------------------------------

    def get_selected_video(self) -> Optional[Dict[str, Any]]:
        items = self.feed_items if self.mode == "feed" else self.creator_items
        idx = self.feed_index if self.mode == "feed" else self.creator_index
        if items and 0 <= idx < len(items):
            return items[idx]
        return None

    def action_play_selected(self):
        """Play feed in terminal with looping, next/prev scrolling, and pos tracking."""
        items = self.feed_items if self.mode == "feed" else self.creator_items
        idx = self.feed_index if self.mode == "feed" else self.creator_index
        if not items or not (0 <= idx < len(items)):
            self.set_status("No video selected.", RED)
            return

        video = items[idx]
        author = video.get("author_id", "creator")
        self.set_status(f"Feed playback ({self.vo_driver.upper()}): @{author} [j/↓: Next, k/↑: Prev, ESC/q: Exit]", CYAN)
        self.draw()

        new_idx, msg = play_feed_in_terminal(
            items=items,
            start_index=idx,
            vo_driver=self.vo_driver
        )

        if self.mode == "feed":
            self.feed_index = new_idx
        else:
            self.creator_index = new_idx

        self.force_clear = True
        self.set_status(msg, GREEN)


    def action_download_selected(self):
        """Explicitly download the selected video (:d)."""
        video = self.get_selected_video()
        if not video:
            self.set_status("No video selected to download.", RED)
            return

        play_url = video.get("play_url") or video.get("web_url")
        author = video.get("author_id", "tiktok")
        self.set_status("Downloading video to ~/Downloads/...", CYAN)
        self.draw()
        success, res = download_video(play_url, filename_prefix=f"tiktok_{author}")
        if success:
            self.set_status(f"✓ Downloaded: {res}", GREEN)
        else:
            self.set_status(f"✗ {res}", RED)

    def action_audio_selected(self):
        """Play audio soundtrack in terminal (:m)."""
        video = self.get_selected_video()
        if not video:
            self.set_status("No video selected.", RED)
            return

        audio_url = video.get("music_url") or video.get("play_url")
        if not audio_url:
            self.set_status("No audio URL available.", RED)
            return

        self.set_status("Playing audio in terminal...", CYAN)
        success, msg = play_audio_in_terminal(audio_url, title=video.get("music_title", ""))
        self.set_status(msg, GREEN if success else RED)
