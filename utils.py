import re
import logging
import os
from datetime import datetime
from config import LOG_PATH


def is_valid_youtube_url(url: str) -> bool:
    pattern = re.compile(
        r'(https?://)?(www\.)?(youtube\.com/(watch\?v=|playlist\?list=|shorts/)|youtu\.be/)[\w\-_?=&]+'
    )
    return bool(pattern.match(url.strip()))


def is_valid_facebook_url(url: str) -> bool:
    return bool(re.match(
        r'https?://(www\.|m\.)?facebook\.com/.+|https?://fb\.watch/.+',
        url.strip()
    ))


def detect_source(url: str) -> str:
    """Returns 'youtube', 'facebook', or 'unknown'."""
    u = url.strip()
    if is_valid_youtube_url(u):
        return 'youtube'
    if is_valid_facebook_url(u):
        return 'facebook'
    return 'unknown'


def is_playlist_url(url: str) -> bool:
    return 'playlist?list=' in url


def read_urls_from_file(filepath: str) -> list[str]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    urls = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                urls.append(line)
    return urls


def setup_logger(name: str = 'downloader') -> logging.Logger:
    os.makedirs(LOG_PATH, exist_ok=True)
    timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
    log_file = os.path.join(LOG_PATH, f'download_{timestamp}.log')

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    fmt = logging.Formatter('[%(asctime)s] %(levelname)-8s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.log_file = log_file
    return logger


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} giờ {m} phút {s} giây"
    if m:
        return f"{m} phút {s} giây"
    return f"{s} giây"
