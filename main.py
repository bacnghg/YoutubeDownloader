import argparse
import sys
import time

from config import MAX_WORKERS, DOWNLOAD_PATH
from downloader import Downloader
from utils import setup_logger, read_urls_from_file, is_valid_youtube_url, is_playlist_url, format_duration


def print_summary(results, elapsed: float, log_file: str):
    success = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success and not r.skipped)
    skipped = sum(1 for r in results if r.skipped)

    print()
    print("=" * 47)
    print("  DOWNLOAD SUMMARY")
    print("=" * 47)
    print(f"  Thanh cong : {success} video(s)")
    print(f"  That bai   : {failed} video(s)")
    print(f"  Bo qua     : {skipped} video(s)")
    print("-" * 47)
    print(f"  Thoi gian  : {format_duration(elapsed)}")
    print(f"  Luu tai    : {DOWNLOAD_PATH}")
    print(f"  Log file   : {log_file}")
    print("=" * 47)

    if failed:
        print("\nVideo that bai:")
        for r in results:
            if not r.success and not r.skipped:
                print(f"  - {r.title or r.url}: {r.error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='YouTube Batch Video Downloader',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --url "https://www.youtube.com/watch?v=VIDEO_ID"
  python main.py --file urls.txt --quality 720p
  python main.py --playlist "https://www.youtube.com/playlist?list=ID"
  python main.py --file urls.txt --workers 5 --dry-run
        """
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--url', metavar='URL', help='Tai mot video don le')
    group.add_argument('--file', metavar='FILE', help='Doc danh sach URL tu file')
    group.add_argument('--playlist', metavar='URL', help='Tai toan bo playlist')

    parser.add_argument('--quality', choices=['best', '720p', '480p', 'audio'],
                        default='best', help='Chat luong video (default: best)')
    parser.add_argument('--workers', type=int, default=MAX_WORKERS,
                        help=f'So threads tai song song (default: {MAX_WORKERS})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Kiem tra ma khong tai thuc su')
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    logger = setup_logger()
    log_file = getattr(logger, 'log_file', 'N/A')

    if args.dry_run:
        logger.info("[DRY-RUN MODE] Se khong tai video thuc su.")

    downloader = Downloader(
        quality=args.quality,
        workers=args.workers,
        dry_run=args.dry_run,
        logger=logger,
    )

    start = time.time()
    results = []

    try:
        if args.url:
            if not is_valid_youtube_url(args.url):
                logger.error(f"URL khong hop le: {args.url}")
                sys.exit(1)
            if is_playlist_url(args.url):
                logger.info("Phat hien playlist URL, chuyen sang che do playlist...")
                results = downloader.download_playlist(args.url)
            else:
                results = downloader.download_urls([args.url])

        elif args.file:
            urls = read_urls_from_file(args.file)
            if not urls:
                logger.error(f"Khong tim thay URL nao trong file: {args.file}")
                sys.exit(1)
            logger.info(f"Doc duoc {len(urls)} URL tu {args.file}")
            results = downloader.download_urls(urls)

        elif args.playlist:
            results = downloader.download_playlist(args.playlist)

    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("\nNguoi dung huy. Dang luu log...")

    elapsed = time.time() - start
    print_summary(results, elapsed, log_file)


if __name__ == '__main__':
    main()
