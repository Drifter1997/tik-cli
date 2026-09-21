import os
import atexit
import shutil
from pathlib import Path

# Base configuration directory in user's home (completely independent from any browser)
CONFIG_DIR = Path(os.path.expanduser("~/.config/tik-cli"))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Isolated session, device, and cookie storage
SESSION_FILE = CONFIG_DIR / "session.json"
DEVICE_FILE = CONFIG_DIR / "device.json"

# Download directory for explicit :d command
DOWNLOAD_DIR = Path(os.path.expanduser("~/Downloads"))
if not DOWNLOAD_DIR.exists():
    DOWNLOAD_DIR = Path(os.path.expanduser("~/repo/tik-cli/downloads"))
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# RAM-only media directory (uses Linux tmpfs in /dev/shm for 0 disk writes)
if os.path.isdir("/dev/shm") and os.access("/dev/shm", os.W_OK):
    RAM_DIR = Path(f"/dev/shm/tik-cli-{os.getuid()}")
else:
    RAM_DIR = Path(f"/tmp/tik-cli-{os.getuid()}")

RAM_DIR.mkdir(parents=True, exist_ok=True)


# Cleanup RAM media directory on application exit
def cleanup_ram_dir():
    try:
        if RAM_DIR.exists():
            shutil.rmtree(RAM_DIR, ignore_errors=True)
    except Exception:
        pass


atexit.register(cleanup_ram_dir)

# External tool commands
MPV_PATH = shutil.which("mpv") or "mpv"
CHAFA_PATH = shutil.which("chafa") or "chafa"
IMV_PATH = shutil.which("imv") or "imv"
FFMPEG_PATH = shutil.which("ffmpeg") or "ffmpeg"
YTDLP_PATH = shutil.which("yt-dlp") or "yt-dlp"

# Thumbnail defaults
THUMB_MAX_WIDTH = 32
THUMB_MAX_HEIGHT = 14
DEFAULT_REGION = "US"


def get_default_vo_driver() -> str:
    env_driver = os.environ.get("TIKCLI_VO")
    if env_driver:
        return env_driver.lower()
    # Default to 24-bit TrueColor (tct) for 100% accurate colors with zero banding or dithering grains.
    # Users can toggle to high-res pixel mode at any time using ':vo sixel' or ':vo'.
    return "tct"


DEFAULT_VO_DRIVER = get_default_vo_driver()
