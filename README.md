# tik-cli

A minimal, fast, and hackable CLI/TUI TikTok client designed for Neovim users and terminal enthusiasts.

---

## ✨ Features

- **🚀 In-Terminal Video Playback (`mpv --vo=sixel,tct`)**:
  - Videos render directly inside your terminal cells without opening external X11/Wayland popup windows.
  - Native Sixel support on modern terminals (like `foot`), with 24-bit TrueColor ANSI half-block fallback.
  - Audio plays seamlessly via PipeWire / PulseAudio.
- **🧠 Zero Drive Clutter (100% RAM-Only)**:
  - Video streaming and inline thumbnails operate strictly in Linux RAM (`/dev/shm`).
  - Temporary files never touch your SSD and are purged automatically on exit (`atexit`).
- **🔓 Zero Login Required for Video Browsing**:
  - Instant access to TikTok's **Trending / For You Page (FYP)**.
  - Explore any creator's latest videos by handle (e.g. `@khaby.lame`, `@tiktok`).
  - Paste and play any standard or shortened TikTok video URL.
- **🖼️ Inline Terminal Thumbnails (`chafa`)**:
  - Cover previews rendered in high-resolution ANSI symbols directly inside the TUI.
- **💾 Explicit Download (`:d`)**:
  - Media is only written to your disk (`~/Downloads/`) when you explicitly command `:d`.
- **🔒 Optional Session Cookie Login**:
  - Keep guest exploration as default, or optionally authenticate using your `sessionid` cookie to view your account details and Direct Messages.
  - Credentials stored securely in `~/.config/tik-cli/session.json` (chmod `0600`).

---

## 📦 Requirements

- **Linux** (Arch Linux / any system with standard tools)
- **Python 3.10+** (Python 3.14 supported)
- **mpv** (for in-terminal video and audio playback)
- **chafa** (for inline terminal thumbnails)
- **ffmpeg** (for media processing)
- **yt-dlp** (for creator profile and video extraction)

---

## 🚀 Setup & Launch

1. Navigate to the repository:
   ```bash
   cd ~/repo/tik-cli
   ```

2. Run the automated setup script:
   ```bash
   bash setup.sh
   ```

3. Launch the client:
   ```bash
   ./tik-cli
   ```

4. (Optional) Symlink to your PATH for global access:
   ```bash
   ln -sf ~/repo/tik-cli/tik-cli ~/.local/bin/tik-cli
   ```

---

## ⌨️ Navigation & Hotkeys

### Global Navigation
| Key | Action |
|---|---|
| `j` / `↓` | Move selection down |
| `k` / `↑` | Move selection up |
| `Mouse Wheel` / `PageUp`/`PageDown` | Fast scroll list |
| `Enter` | **Watch selected video in terminal** |
| `Tab` | Switch mode (`For You` / `Creator` / `DMs`) |
| `1`, `2`, `3` | Jump directly to mode tab |
| `/` | Search creator (`@handle`) or load TikTok video URL |
| `r` | Refresh current feed |
| `q` or `Ctrl+C` | Quit |

### Video Playback Controls (Inside Terminal)
TikTok-style continuous feed playback: each video loops continuously until you scroll to the next video or exit.

| Key | Action |
|---|---|
| `j` / `↓` / `PageDown` / `Wheel Down` | **Next video** (swipes down like TikTok) |
| `k` / `↑` / `PageUp` / `Wheel Up` | **Previous video** (swipes up like TikTok) |
| `Space` | Pause / Resume |
| `←` / `→` | Seek -5s / +5s |
| `m` | Toggle mute |
| `ESC` / `q` / `Ctrl+C` | Stop playback and return to TUI at current video |

### Commands (Type `:`)
| Command | Action |
|---|---|
| `:d` | Download selected video to `~/Downloads/` |
| `:m` | Play background soundtrack only |
| `:user @handle` | Browse videos of a specific creator |
| `:login` | Log in with TikTok `sessionid` cookie |
| `:logout` | Remove saved credentials and return to Guest Mode |
| `:help` | Show command cheat sheet |
| `:q` | Quit application |

---

## 🛠️ CLI Quick Actions

```bash
# Directly watch any TikTok video inside your terminal
./tik-cli --play "https://www.tiktok.com/@tiktok/video/7681695065927912735"

# Launch directly on a specific creator's profile
./tik-cli --user "@khaby.lame"

# Authenticate with session ID
./tik-cli --session "<your_session_id>"

# Clear session
./tik-cli --logout
```
