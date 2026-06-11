#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
# Add Homebrew bin to PATH so yt-dlp can find node/deno for YouTube format extraction
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
"$DIR/venv/bin/python" "$DIR/server.py"
