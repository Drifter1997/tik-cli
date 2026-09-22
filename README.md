# 🎬 tik-cli

> **Minimal, keyboard-centric, and ephemeral TikTok client for the terminal.**  
> Stream videos directly inside terminal cells with Sixel/TrueColor graphics, browse creators, and navigate feeds without leaving your keyboard.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%2F%20Wayland-green.svg)]()
[![Terminal](https://img.shields.io/badge/Terminal-Sixel%20%2F%20Foot%20%2F%20Kitty-orange.svg)]()
[![License](https://img.shields.io/badge/License-MIT-purple.svg)]()

---

## ✨ Features

- **🚀 In-Terminal Video Playback (`mpv --vo=sixel,tct`)**:
  - Stream videos directly inside your terminal emulator without launching detached GUI windows.
  - Native high-speed Sixel graphics on modern terminals (e.g. `foot`), with 24-bit TrueColor ANSI half-block fallback.
  - Seamless audio routing via PipeWire / PulseAudio.
- **🧠 Zero Drive Clutter (100% RAM-Only)**:
  - Video streams and inline thumbnails live purely in Linux tmpfs RAM (`/dev/shm`).
  - Never writes temporary media to disk and purges cache automatically on exit (`atexit`).
- **🔓 Zero Login Required for Video Browsing**:
  - Instant access to TikTok's **Trending / For You Page (FYP)**.
  - Explore any creator's latest videos by handle (e.g. `@khaby.lame`, `@tiktok`).
  - Paste and play any standard or shortened TikTok video URL directly.
- **🖼️ Inline Terminal Thumbnails (`chafa`)**:
  - High-resolution ANSI cover thumbnails rendered directly inside the TUI feed.
- **💾 Explicit Download (`:d`)**:
  - Media is only written to your disk (`~/Downloads/`) when you explicitly command `:d`.
- **🔒 Optional Session Cookie Login**:
  - Guest mode is default and login-free.
  - Optional session authentication (`sessionid` cookie) to access profile data and DMs.
  - Auth data stored securely in `~/.config/tik-cli/session.json` (`chmod 0600`).

---

## 📦 Requirements

- **Linux** (Arch Linux, Ubuntu, Fedora, Debian, etc.)
- **Python 3.10+** (Python 3.14 supported)
- **mpv** (for terminal video and audio playback)
- **chafa** (for inline terminal thumbnail rendering)
- **ffmpeg** (media demuxing and conversion)
- **yt-dlp** (creator feed extraction)

On Arch Linux:
```bash
sudo pacman -S mpv chafa ffmpeg yt-dlp python
```

---

## 🚀 Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Drifter1997/tik-cli.git ~/repo/tik-cli
   cd ~/repo/tik-cli
   ```

2. **Run the setup script**:
   ```bash
   bash setup.sh
   ```

3. **Launch the client**:
   ```bash
   ./tik-cli
   ```

4. **Global Access (Optional)**:
   Add a symlink to your `$PATH`:
   ```bash
   ln -sf ~/repo/tik-cli/tik-cli ~/.local/bin/tik-cli
   ```

---

## ⌨️ Controls & Navigation

### Feed Navigation
| Key | Action |
|---|---|
| `j` / `↓` | Move selection down |
| `k` / `↑` | Move selection up |
| `Mouse Wheel` / `PageUp` / `PageDown` | Fast scroll list |
| `Enter` | **Watch selected video in terminal** |
| `Tab` | Switch mode (`For You` / `Creator` / `DMs`) |
| `1`, `2`, `3` | Jump directly to tab |
| `/` | Search creator (`@handle`) or load TikTok video URL |
| `r` | Refresh current feed |
| `q` or `Ctrl+C` | Quit application |

### Video Playback Controls (Inside Terminal)
Continuous loop video playback just like mobile TikTok:

| Key | Action |
|---|---|
| `j` / `↓` / `PageDown` / `Wheel Down` | **Next video** (swipes down) |
| `k` / `↑` / `PageUp` / `Wheel Up` | **Previous video** (swipes up) |
| `Space` | Pause / Resume |
| `←` / `→` | Seek -5s / +5s |
| `m` | Toggle mute |
| `ESC` / `q` | Exit playback and return to TUI feed |

### Commands (Type `:`)
| Command | Action |
|---|---|
| `:d` | Download selected video to `~/Downloads/` |
| `:m` | Play background audio soundtrack only |
| `:user @handle` | Browse videos of a specific creator |
| `:login` | Log in with TikTok `sessionid` cookie |
| `:logout` | Remove saved session and return to guest mode |
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

---

## 📄 License

MIT License. Crafted for terminal and keyboard enthusiasts.
