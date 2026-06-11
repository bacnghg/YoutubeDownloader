import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DOWNLOAD_PATH = os.path.join(BASE_DIR, 'downloads')
LOG_PATH      = os.path.join(BASE_DIR, 'logs')

# Format selectors — vcodec^=avc = H.264 (AVC), native on macOS QuickTime
# Fallback chain ensures we always get something even if H.264 unavailable
QUALITY_MAP = {
    # Best quality H.264 (up to 1080p) → QuickTime compatible
    'best':  ('bestvideo[vcodec^=avc]+bestaudio[ext=m4a]'
              '/bestvideo[vcodec^=avc]+bestaudio'
              '/bestvideo[ext=mp4]+bestaudio[ext=m4a]'
              '/bestvideo+bestaudio/best'),

    # H.264 capped at 1080p
    '1080p': ('bestvideo[vcodec^=avc][height<=1080]+bestaudio[ext=m4a]'
              '/bestvideo[height<=1080]+bestaudio'
              '/best[height<=1080]'),

    '720p':  ('bestvideo[vcodec^=avc][height<=720]+bestaudio[ext=m4a]'
              '/bestvideo[height<=720]+bestaudio'
              '/best[height<=720]'),

    '480p':  ('bestvideo[vcodec^=avc][height<=480]+bestaudio[ext=m4a]'
              '/bestvideo[height<=480]+bestaudio'
              '/best[height<=480]'),

    # Max quality regardless of codec — may produce AV1/VP9, use VLC to play
    'max':   ('bestvideo+bestaudio/best'),

    'audio': 'bestaudio/best',
}

OUTPUT_TEMPLATE = '%(title)s.%(ext)s'

MAX_WORKERS  = 3
MAX_RETRIES  = 3
RETRY_DELAY  = 2  # seconds
