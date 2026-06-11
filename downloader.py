import os
import re
import shutil
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import yt_dlp

def _find_bin(name: str) -> str | None:
    """Find a binary — check PATH then common macOS locations."""
    found = shutil.which(name)
    if found:
        return found
    for prefix in ('/opt/homebrew/bin', '/usr/local/bin', '/usr/bin'):
        p = os.path.join(prefix, name)
        if os.path.isfile(p):
            return p
    return None

_NODE_PATH   = _find_bin('node')
_FFMPEG_PATH = _find_bin('ffmpeg')

from config import DOWNLOAD_PATH, OUTPUT_TEMPLATE, QUALITY_MAP, MAX_RETRIES, RETRY_DELAY
from utils import is_valid_youtube_url

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mK]')

def _clean(msg: str) -> str:
    msg = _ANSI_RE.sub('', msg).strip()
    msg = re.sub(r'^ERROR:\s*', '', msg)   # yt-dlp prefixes errors with "ERROR: "
    return msg

# Errors that are permanent — no point retrying
_PERMANENT_ERRORS = [
    'Private video',
    'removed by the uploader',
    'This video is unavailable',
    'Join this channel',       # members-only
    'members-only',
    'This video is members-only',
    'Sign in to confirm your age',
]


class _YDLLogger:
    """Routes yt-dlp output to our event system; suppresses terminal noise."""
    _js_warned = False   # class-level flag: show JS runtime warning only once

    def __init__(self, on_event: Callable):
        self._emit = on_event

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        if not msg:
            return
        # Suppress the repeated "no JS runtime" noise — emit only the first time
        if 'JavaScript runtime' in msg or 'js-runtimes' in msg:
            if not _YDLLogger._js_warned:
                _YDLLogger._js_warned = True
                self._emit({'type': 'log', 'level': 'warning',
                            'message': 'yt-dlp: Không tìm thấy JS runtime (deno/node). Một số format có thể bị thiếu.'})
            return
        if '[download]' not in msg:
            self._emit({'type': 'log', 'level': 'warning', 'message': _clean(msg)})

    def error(self, msg):
        if msg:
            self._emit({'type': 'log', 'level': 'error', 'message': _clean(msg)})


class DownloadResult:
    def __init__(self, url: str, index: int = 0):
        self.url = url
        self.index = index
        self.success = False
        self.skipped = False
        self.title = ''
        self.error = ''


class Downloader:
    def __init__(self, quality: str = 'best', workers: int = 3, dry_run: bool = False,
                 on_event: Optional[Callable] = None, logger: Optional[logging.Logger] = None,
                 output_path: str = '', cookies_browser: str = '',
                 cookies_profile: str = '', cookies_file: str = ''):
        self.quality = quality
        self.workers = workers
        self.dry_run = dry_run
        self.on_event = on_event or (lambda e: None)
        self.logger = logger or logging.getLogger('downloader')
        self.lock = threading.Lock()
        self.output_path = output_path.strip() if output_path.strip() else str(DOWNLOAD_PATH)
        self.cookies_browser = cookies_browser.strip().lower()
        self.cookies_profile = cookies_profile.strip()   # absolute path to profile dir
        self.cookies_file = cookies_file.strip()
        os.makedirs(self.output_path, exist_ok=True)

    def _emit(self, event: dict):
        try:
            self.on_event(event)
        except Exception:
            pass

    def _ydl_base(self, extra: dict = None) -> dict:
        opts = {
            'quiet': True,
            'no_warnings': True,
            'logger': _YDLLogger(self._emit),
        }
        # Explicitly tell yt-dlp where node is, bypassing PATH issues
        if _NODE_PATH:
            opts['js_runtimes'] = {'node': {'path': _NODE_PATH}}
        # Allow yt-dlp to download the JS challenge solver from GitHub (needed for YouTube)
        opts['remote_components'] = ['ejs:github']
        # ffmpeg for merging video+audio streams into a proper MP4
        if _FFMPEG_PATH:
            opts['ffmpeg_location'] = _FFMPEG_PATH
        if self.cookies_browser:
            if self.cookies_profile:
                opts['cookiesfrombrowser'] = (self.cookies_browser, self.cookies_profile, None, None)
            else:
                opts['cookiesfrombrowser'] = (self.cookies_browser,)
        elif self.cookies_file:
            opts['cookiefile'] = self.cookies_file
        if extra:
            opts.update(extra)
        return opts

    def _build_ydl_opts(self, index: int) -> dict:
        fmt = QUALITY_MAP.get(self.quality, QUALITY_MAP['best'])
        opts = self._ydl_base({
            'format': fmt,
            'outtmpl': os.path.join(self.output_path, OUTPUT_TEMPLATE),
            'merge_output_format': 'mp4',   # always output MP4 container
            'ignoreerrors': False,
            'noplaylist': True,
            'progress_hooks': [self._make_progress_hook(index)],
        })
        if self.quality == 'audio':
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        return opts

    def _make_progress_hook(self, index: int):
        def hook(d):
            if d['status'] == 'downloading':
                try:
                    downloaded = d.get('downloaded_bytes') or 0
                    total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                    percent = round(downloaded / total * 100, 1) if total > 0 else 0
                    self._emit({
                        'type': 'video_progress',
                        'index': index,
                        'percent': percent,
                        'speed': (d.get('_speed_str') or '').strip(),
                        'eta': (d.get('_eta_str') or '').strip(),
                    })
                except Exception:
                    pass
        return hook

    def get_playlist_urls(self, playlist_url: str) -> list[str]:
        self._emit({'type': 'log', 'level': 'info', 'message': 'Đang lấy danh sách playlist...'})
        opts = self._ydl_base({'extract_flat': True, 'ignoreerrors': True})
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)

        if not info or 'entries' not in info:
            self._emit({'type': 'log', 'level': 'error', 'message': 'Không thể lấy thông tin playlist'})
            return []

        entries = [e for e in info['entries'] if e and e.get('id')]
        urls = [f"https://www.youtube.com/watch?v={e['id']}" for e in entries]
        title = info.get('title', '')
        self._emit({'type': 'playlist_info', 'title': title, 'total': len(urls)})
        self._emit({'type': 'log', 'level': 'info',
                    'message': f'Playlist "{title}" — {len(urls)} videos'})
        return urls

    def _download_single(self, url: str, index: int) -> DownloadResult:
        result = DownloadResult(url, index)

        if not is_valid_youtube_url(url):
            result.error = 'URL không hợp lệ'
            self._emit({'type': 'video_error', 'index': index,
                        'title': 'URL không hợp lệ', 'error': result.error})
            return result

        self._emit({'type': 'video_start', 'index': index})

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                with yt_dlp.YoutubeDL(self._ydl_base()) as ydl:
                    info = ydl.extract_info(url, download=False)
                    result.title = info.get('title', url)
                    duration = info.get('duration_string', '')

                self._emit({'type': 'video_info', 'index': index,
                            'title': result.title, 'duration': duration})

                if self.dry_run:
                    self._emit({'type': 'video_done', 'index': index,
                                'title': result.title, 'dry_run': True})
                    result.success = True
                    return result

                with yt_dlp.YoutubeDL(self._build_ydl_opts(index)) as ydl:
                    ydl.download([url])

                result.success = True
                self._emit({'type': 'video_done', 'index': index, 'title': result.title})
                with self.lock:
                    self.logger.info(f"✅ Downloaded: \"{result.title}\"")
                return result

            except yt_dlp.utils.DownloadError as e:
                err_msg = _clean(str(e))
                if any(x in err_msg for x in _PERMANENT_ERRORS):
                    if 'Join this channel' in err_msg or 'members-only' in err_msg:
                        if self.cookies_browser or self.cookies_file:
                            result.error = 'Video members-only — cookies không hợp lệ hoặc chưa tham gia kênh'
                        else:
                            result.error = 'Video members-only — chọn browser đã đăng nhập ở mục Xác thực'
                    else:
                        result.error = 'Video private hoặc đã bị xóa'
                    self._emit({'type': 'video_error', 'index': index,
                                'title': result.title or url, 'error': result.error})
                    return result

                result.error = err_msg[:150]
                if attempt < MAX_RETRIES:
                    self._emit({'type': 'log', 'level': 'warning',
                                'message': f'Retry {attempt}/{MAX_RETRIES}: "{result.title or url}"'})
                    time.sleep(RETRY_DELAY)
                else:
                    self._emit({'type': 'video_error', 'index': index,
                                'title': result.title or url, 'error': result.error})
                    with self.lock:
                        self.logger.error(f"❌ Failed: \"{result.title or url}\"")

            except Exception as e:
                result.error = str(e)[:120]
                self._emit({'type': 'video_error', 'index': index,
                            'title': result.title or url, 'error': result.error})
                return result

        return result

    def download_urls(self, urls: list[str]) -> list[DownloadResult]:
        total = len(urls)
        self._emit({
            'type': 'job_start', 'total': total,
            'quality': self.quality, 'workers': self.workers,
            'dry_run': self.dry_run, 'output_path': self.output_path,
        })
        self.logger.info(f"Start: {total} video(s), workers={self.workers}, quality={self.quality}")

        results = []
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(self._download_single, url, i): url
                       for i, url in enumerate(urls)}
            for future in as_completed(futures):
                results.append(future.result())

        return results
