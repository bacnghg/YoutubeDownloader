import asyncio
import json
import logging
import os
import queue
import threading
import time
import uuid
from pathlib import Path

# Ensure Homebrew / common bin dirs are in PATH so yt-dlp can find node/deno
for _p in ('/opt/homebrew/bin', '/usr/local/bin', '/usr/bin'):
    if _p not in os.environ.get('PATH', ''):
        os.environ['PATH'] = _p + ':' + os.environ.get('PATH', '')

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import DOWNLOAD_PATH
from downloader import Downloader
from utils import setup_logger, is_playlist_url, format_duration

BASE_DIR = Path(__file__).parent
app = FastAPI(title="YouTube Downloader")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

jobs: dict = {}


class DownloadRequest(BaseModel):
    urls: list[str] = []
    quality: str = "best"
    workers: int = 3
    dry_run: bool = False
    output_path: str = ""
    cookies_browser: str = ""
    cookies_profile: str = ""   # path to browser profile directory
    cookies_file: str = ""


@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/config")
async def get_config():
    return {"download_path": str(DOWNLOAD_PATH)}


# ── Browser profile detection ─────────────────────────────────────────────────

_CHROMIUM_BASES = {
    'chrome':   Path.home() / 'Library/Application Support/Google/Chrome',
    'chromium': Path.home() / 'Library/Application Support/Chromium',
    'brave':    Path.home() / 'Library/Application Support/BraveSoftware/Brave-Browser',
    'edge':     Path.home() / 'Library/Application Support/Microsoft Edge',
}

def _read_chromium_profiles(base: Path) -> list[dict]:
    profiles = []
    if not base.exists():
        return profiles

    # Read primary emails from Local State (faster, no per-file parsing needed)
    primary_emails: dict[str, str] = {}
    local_state = base / 'Local State'
    if local_state.exists():
        try:
            ls    = json.loads(local_state.read_text(encoding='utf-8', errors='ignore'))
            cache = ls.get('profile', {}).get('info_cache', {})
            for dir_name, info in cache.items():
                primary_emails[dir_name] = info.get('user_name', '')
        except Exception:
            pass

    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        if d.name != 'Default' and not d.name.startswith('Profile'):
            continue
        prefs_file = d / 'Preferences'
        if not prefs_file.exists():
            continue
        try:
            prefs  = json.loads(prefs_file.read_text(encoding='utf-8', errors='ignore'))
            name   = prefs.get('profile', {}).get('name', d.name)
            # ALL Google accounts signed into this profile
            accts  = prefs.get('account_info', [])
            emails = [a['email'] for a in accts if a.get('email')]
            primary = primary_emails.get(d.name) or (emails[0] if emails else '')
            profiles.append({
                'dir':     d.name,
                'name':    name,
                'email':   primary,           # primary/sync account
                'emails':  emails,            # ALL accounts (may include secondary)
                'path':    str(d),
            })
        except Exception:
            profiles.append({'dir': d.name, 'name': d.name, 'email': '',
                             'emails': [], 'path': str(d)})
    return profiles

def _read_firefox_profiles() -> list[dict]:
    base = Path.home() / 'Library/Application Support/Firefox/Profiles'
    if not base.exists():
        return []
    profiles = []
    for d in sorted(base.iterdir()):
        if d.is_dir():
            profiles.append({'dir': d.name, 'name': d.name.split('.')[-1],
                             'email': '', 'path': str(d), 'avatar': ''})
    return profiles

@app.get("/api/browsers/profiles")
async def get_browser_profiles(browser: str = "chrome"):
    browser = browser.lower().strip()
    if browser in _CHROMIUM_BASES:
        profiles = _read_chromium_profiles(_CHROMIUM_BASES[browser])
    elif browser == 'firefox':
        profiles = _read_firefox_profiles()
    elif browser == 'safari':
        # Safari has a single shared cookie store — no per-profile selection
        profiles = [{'dir': 'default', 'name': 'Safari (mặc định)',
                     'email': '', 'path': '', 'avatar': ''}]
    else:
        profiles = []
    return {"browser": browser, "profiles": profiles}


@app.post("/api/jobs")
async def create_job(req: DownloadRequest):
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        'id': job_id,
        'status': 'pending',
        'config': req,
        'queue': queue.Queue(),
        'thread': None,
        'start_time': None,
    }
    return {"job_id": job_id}


def _blocking_get(q: queue.Queue, thread: threading.Thread):
    while True:
        try:
            return q.get(timeout=1.0)
        except queue.Empty:
            if not thread.is_alive():
                return None


@app.websocket("/ws/{job_id}")
async def ws_endpoint(websocket: WebSocket, job_id: str):
    await websocket.accept()

    job = jobs.get(job_id)
    if not job:
        await websocket.send_json({"type": "error", "message": "Job not found"})
        await websocket.close()
        return

    thread = threading.Thread(target=_run_download, args=(job,), daemon=True)
    job['thread'] = thread
    job['start_time'] = time.time()
    thread.start()

    q: queue.Queue = job['queue']
    loop = asyncio.get_event_loop()

    try:
        while True:
            msg = await loop.run_in_executor(None, _blocking_get, q, thread)
            if msg is None:
                break
            await websocket.send_json(msg)
            if msg.get('type') == 'job_done':
                break
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


def _run_download(job: dict):
    config = job['config']
    q: queue.Queue = job['queue']

    def on_event(event):
        q.put(event)

    logger = setup_logger(f"job_{job['id']}")
    start_time = job.get('start_time') or time.time()

    try:
        raw_path = (config.output_path or '').strip()
        if raw_path:
            raw_path = os.path.abspath(os.path.expanduser(raw_path))
        cookies_file = (config.cookies_file or '').strip()
        if cookies_file:
            cookies_file = os.path.abspath(os.path.expanduser(cookies_file))

        downloader = Downloader(
            quality=config.quality,
            workers=config.workers,
            dry_run=config.dry_run,
            on_event=on_event,
            logger=logger,
            output_path=raw_path,
            cookies_browser=config.cookies_browser or '',
            cookies_profile=config.cookies_profile or '',
            cookies_file=cookies_file,
        )

        all_urls: list[str] = []
        for url in config.urls:
            url = url.strip()
            if not url or url.startswith('#'):
                continue
            if is_playlist_url(url):
                all_urls.extend(downloader.get_playlist_urls(url))
            else:
                all_urls.append(url)

        if not all_urls:
            q.put({'type': 'error', 'message': 'Không tìm thấy URL hợp lệ'})
            return

        results = downloader.download_urls(all_urls)

        elapsed = time.time() - start_time
        success = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success and not r.skipped)
        skipped = sum(1 for r in results if r.skipped)

        q.put({
            'type': 'job_done',
            'success': success,
            'failed': failed,
            'skipped': skipped,
            'elapsed': round(elapsed, 1),
            'elapsed_str': format_duration(elapsed),
        })

    except Exception as e:
        logger.error(f"Job error: {e}")
        q.put({'type': 'error', 'message': str(e)})
    finally:
        q.put(None)
        job['status'] = 'done'


if __name__ == '__main__':
    uvicorn.run("server:app", host="127.0.0.1", port=8080, reload=False)
