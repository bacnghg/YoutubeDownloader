# YouTube Batch Downloader

Ứng dụng web tải video YouTube hàng loạt với giao diện trực quan, hỗ trợ tải song song, xác thực tài khoản và theo dõi tiến trình real-time.

---

## Tính năng

### Tải video
- Tải từ URL đơn lẻ, nhiều URL cùng lúc, hoặc toàn bộ playlist
- Tải song song nhiều video cùng lúc (tuỳ chỉnh số luồng 1–8)
- Tự động retry nếu tải thất bại (tối đa 3 lần)
- Hỗ trợ chế độ **Dry Run** — kiểm tra danh sách video mà không tải thực sự

### Chất lượng video
| Tuỳ chọn | Codec | Tương thích |
|----------|-------|-------------|
| Best H.264 / 1080p | H.264 + AAC | macOS QuickTime ✅ |
| 720p / 480p H.264 | H.264 + AAC | macOS QuickTime ✅ |
| Max quality 4K | AV1 / VP9 | VLC ✅ |
| Audio only | MP3 | — |

### Xác thực tài khoản (Members-only)
- Đọc cookies trực tiếp từ Chrome, Firefox, Safari, Brave, Edge
- Tự động detect tất cả Chrome profiles và liệt kê email từng profile
- Hỗ trợ chọn đúng account YouTube trong profile có nhiều tài khoản
- Hỗ trợ nhập file `cookies.txt` thủ công

### Giao diện web
- Real-time progress bar từng video qua WebSocket
- Log console hiển thị trạng thái từng bước
- Thống kê sau khi hoàn tất (thành công / thất bại / thời gian)
- Tuỳ chỉnh folder lưu video

### Kỹ thuật
- Node.js được tự động detect để giải YouTube JS challenge
- ffmpeg tự động ghép video + audio thành file MP4 hoàn chỉnh
- Bỏ qua ngay các video private, bị xóa, members-only (không retry vô ích)
- ANSI color codes từ yt-dlp được strip, log hiển thị sạch

---

## Cài đặt

### Yêu cầu
- Python 3.13+
- Node.js (để giải YouTube JS challenge)
- ffmpeg (để ghép video + audio)

```bash
# Cài Node.js và ffmpeg qua Homebrew (macOS)
brew install node ffmpeg
```

### Setup project

```bash
# Tạo virtual environment và cài dependencies
/opt/homebrew/bin/python3.13 -m venv venv
venv/bin/pip install -r requirements.txt
```

---

## Chạy ứng dụng

```bash
./run.sh
```

Mở trình duyệt: **http://127.0.0.1:8080**

---

## Sử dụng

### Tải video thường
1. Paste URL vào ô input (mỗi dòng một URL)
2. Chọn chất lượng và số luồng
3. Nhấn **Bắt đầu tải xuống** (hoặc `Ctrl+Enter`)

### Tải video Members-only
1. Mở Chrome → vào `youtube.com` → switch sang đúng account
2. **Đóng Chrome hoàn toàn** (`⌘Q`)
3. Mở panel **Xác thực** → chọn browser → chọn profile chứa account
4. Nhấn **Bắt đầu tải xuống**

### URL được hỗ trợ
```
https://www.youtube.com/watch?v=VIDEO_ID
https://www.youtube.com/playlist?list=PLAYLIST_ID
https://youtu.be/VIDEO_ID
```

---

## Cấu trúc dự án

```
youtube-downloader/
├── server.py          # FastAPI server, WebSocket, REST API
├── downloader.py      # Logic tải video (yt-dlp wrapper)
├── config.py          # Cấu hình format, path, workers
├── utils.py           # URL validation, logger, helpers
├── run.sh             # Script khởi động server
├── requirements.txt   # Python dependencies
├── static/
│   └── index.html     # Web UI (HTML + CSS + JS)
├── downloads/         # Video lưu tại đây
└── logs/              # Log files
```

---

## Tech Stack

| Thành phần | Công nghệ |
|-----------|-----------|
| Backend | Python 3.13, FastAPI, WebSocket |
| Video download | yt-dlp |
| Video merge | ffmpeg |
| JS challenge | Node.js + EJS (yt-dlp remote component) |
| Frontend | Vanilla HTML / CSS / JS |

---

## Lưu ý

- Chỉ tải video bạn có quyền truy cập hợp pháp
- Giảm số luồng (`--workers 1`) nếu YouTube rate-limit
- Chọn **Best H.264** để phát trực tiếp bằng QuickTime; chọn **Max 4K** nếu cần chất lượng cao nhất và dùng VLC
- Chrome cần đóng hoàn toàn trước khi đọc cookies
