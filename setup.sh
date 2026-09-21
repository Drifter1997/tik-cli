#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "=== Setting up tik-cli in $SCRIPT_DIR ==="

# Check external system tools
echo -n "Checking for mpv... "
if command -v mpv >/dev/null 2>&1; then
    echo "found ($(mpv --version 2>&1 | head -n 1))"
else
    echo "WARNING: mpv not found. In-terminal video playback will be disabled."
fi

echo -n "Checking for chafa... "
if command -v chafa >/dev/null 2>&1; then
    echo "found ($(chafa --version 2>&1 | head -n 1))"
else
    echo "WARNING: chafa not found. Inline thumbnails will be disabled."
fi

echo -n "Checking for ffmpeg... "
if command -v ffmpeg >/dev/null 2>&1; then
    echo "found ($(ffmpeg -version 2>&1 | head -n 1))"
else
    echo "WARNING: ffmpeg not found. Media conversions may be limited."
fi

echo -n "Checking for yt-dlp... "
if command -v yt-dlp >/dev/null 2>&1; then
    echo "found ($(yt-dlp --version 2>&1 | head -n 1))"
else
    echo "Note: system yt-dlp found or will be installed in virtual environment."
fi

# Create virtual environment if needed
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

echo "Installing / updating dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

chmod +x "$SCRIPT_DIR/tik-cli" "$SCRIPT_DIR/setup.sh"

echo ""
echo "=== Setup completed successfully! ==="
echo "You can now run: ./tik-cli"
echo "Or link it: ln -sf $SCRIPT_DIR/tik-cli ~/.local/bin/tik-cli"
