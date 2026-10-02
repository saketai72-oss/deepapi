# 🚀 DeepSeek Web-to-API Bridge (Dual OpenAI & Claude Code Compatible)

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-windows%20%7C%20linux%20%7C%20macos-lightgrey.svg)]()

Cầu nối trung gian hiệu năng cao chuyển đổi giao diện web của **DeepSeek Chat (V3 / Reasoner / R1)** thành 2 chuẩn API:
1. **Anthropic Messages API (`/v1/messages`)**: Tương thích trực tiếp 100% với **Claude Code CLI**, hỗ trợ streaming SSE và Tool Calling (Bash, FileEdit, FileRead,...).
2. **OpenAI Compatible API (`/v1/chat/completions`)**: Dành cho các AI coding agent như **Cline, Roo Code, Cursor, Qwen Code Companion...**.

---

## ✨ Tính Năng Nổi Bật

- 🛡️ **Tích Hợp Proxy Độc Lập Cho Từng Account**:
  - Tích hợp sẵn bộ công cụ **Cloudflare WARP** siêu sạch, độ trễ cực thấp trong thư mục `./ip` (cổng `127.0.0.1:2080`).
  - Hỗ trợ gán proxy riêng cho từng tài khoản: `email1:pass1:proxy1,email2:pass2:proxy2`.
  - Mỗi tài khoản chạy trên một isolated Playwright Browser Context riêng biệt với IP khác nhau, không bị xung đột cookie hay dính vạ IP.
- 💻 **Tương Thích Native Với Claude Code CLI**:
  - Hỗ trợ chuẩn Anthropic Messages API (`POST /v1/messages` & `POST /v1/messages/count_tokens`).
  - Tự động dịch và xử lý các tool call định dạng **DeepSeek DSML (`<｜｜DSML｜｜ invoke>`)** thành Anthropic `tool_use` blocks.
- 📦 **Cơ Chế Đóng Gói Context Thành File (Hướng A - Giống ds2api)**:
  - Khi hội thoại vượt quá ngưỡng (mặc định 30,000 ký tự), ngữ cảnh lịch sử được tự động đóng gói thành file `.txt` và upload qua API DeepSeek.
  - Giúp task code dài hàng giờ không bị tràn context hay quên chỉ thị.
- 🥷 **Bypass Cloudflare & Bot-Detection**:
  - Dùng `cloakbrowser` mô phỏng vân tay Windows/Chrome thật, kèm giải Proof-of-Work (PoW) trực tiếp qua Web Worker đa luồng.
- 🔄 **Xoay Vòng Nhiều Tài Khoản & Disk Cache Token**:
  - Token được lưu đệm trong `.tokens.json`, tự động phục hồi khi khởi động mà không cần nhập lại mật khẩu hay giải captcha.

---

## ⚙️ Cấu Hình Môi Trường (`.env`)

Mở file `.env` và tùy chỉnh:

```ini
# DeepSeek Account mặc định (hoặc tự động tải từ .tokens.json)
DEEPSEEK_EMAIL=your_deepseek_email@example.com
DEEPSEEK_PASSWORD="your_password_here"

# Gán Proxy riêng cho từng tài khoản: email:password:proxy (ngăn cách bằng dấu phẩy)
# DEEPSEEK_ACCOUNTS=acc1@domain.com:pass1:http://127.0.0.1:2080,acc2@domain.com:pass2:socks5://127.0.0.1:1080

# Proxy sạch mặc định: Cloudflare WARP via sing-box (tích hợp trong ./ip)
DEEPSEEK_PROXY=http://127.0.0.1:2080

# Cấu hình API Server
API_KEY=sk-my-secret-key-1
PORT=5001
HOST=0.0.0.0

# Cơ chế gửi Context dạng File (chống tràn context cho task dài)
ENABLE_CONTEXT_FILE=true
CONTEXT_FILE_THRESHOLD=30000
```

---

## 🚀 Khởi Động Nhanh (1-Click)

Bạn chỉ cần chạy file:
```bash
start_bridge.bat
```
Script sẽ tự động:
1. Kiểm tra và khởi chạy engine proxy Cloudflare WARP trong `./ip` tại `127.0.0.1:2080` (tự tải sing-box portable nếu chưa có).
2. Khởi chạy máy chủ DeepSeek API Bridge WSGI tại `http://127.0.0.1:5001`.

---

## 🌐 Bộ Công Cụ Quản Lý IP Riêng Biệt (`./ip`)

Nếu muốn điều khiển hoặc đổi IP độc lập:
- Mở thư mục [./ip](file:///c:/code/python/bowers/deepapi/ip):
  - **`run.bat`**: Menu tương tác đầy đủ (Bật/Tắt, đổi IP mới, kiểm tra ping).
  - **`start_ipv6.bat`**: Bật ngay IPv6 cho toàn máy (hỗ trợ cả trình duyệt Chrome/Edge).
  - **`stop_ipv6.bat`**: Tắt proxy, khôi phục mạng ban đầu.
  - **`test_ipv6.bat`**: Kiểm tra địa chỉ IP hiện tại và độ trễ.
- Dòng lệnh: `python ip/ipv6_tool.py new` để đổi sang một địa chỉ IP mới hoàn toàn.


---

## 🤖 Điều Khiển Claude Code CLI Thực Hiện Coding Task

Để Claude Code sử dụng backend DeepSeek:

### Cách 1: Sử dụng cấu hình tự động (Đã được cấu hình sẵn trong `~/.claude/settings.json`)
Chỉ cần mở Terminal và gõ:
```bash
claude
```
Hoặc chạy headless với quyền tự động thực thi tool:
```bash
claude -p "Viết một module scraper tin tức có cache và test đầy đủ" --dangerously-skip-permissions
```

### Cách 2: Thiết lập thủ công qua biến môi trường
```powershell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:5001"
$env:ANTHROPIC_API_KEY  = "sk-my-secret-key-1"
claude
```

---

## 📡 Danh Sách Model Hỗ Trợ

Hệ thống đã được tối ưu hóa về **1 Model Duy Nhất** để đảm bảo luôn bật tư duy sâu (DeepThink) cao nhất cho coding:

| Model Trực Tiếp | Các Tên Alias Hỗ Trợ | Chế Độ Suy Nghĩ (Reasoning) |
| :--- | :--- | :--- |
| **`deepseek-reasoner`** | `claude-3-7-sonnet`, `claude-3-5-sonnet`, `gpt-4o`, `deepseek-chat`, `deepseek-r1`, `qwen-max` | **BẬT 100% (Full DeepThink R1)** |

> **Lưu ý:** Bất kể ứng dụng hoặc client bên ngoài (Claude Code, Cursor, Cline, NextChat, Chatbox,...) truyền vào tên model nào, server đều tự động ánh xạ về `deepseek-reasoner` và kích hoạt chuỗi suy nghĩ Extended Thinking / Reasoning Content.

