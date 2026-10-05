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

## 🔰 Hướng Dẫn Cài Đặt Chi Tiết Cho Người Mới

Nếu bạn là người mới bắt đầu, hãy làm theo từng bước sau để đảm bảo hệ thống hoạt động trơn tru nhất:

### Bước 1: Cài đặt Python & Tải Code
1. Cài đặt **[Python 3.8+](https://www.python.org/downloads/)** (Quan trọng: Phải nhớ tích chọn ô `Add Python to PATH` trong màn hình cài đặt đầu tiên).
2. Tải toàn bộ mã nguồn của dự án này về máy và giải nén (hoặc dùng `git clone`).

### Bước 2: Cài đặt Thư Viện Bắt Buộc
Mở Terminal (Command Prompt / PowerShell) tại thư mục chứa mã nguồn và chạy lệnh:
```bash
pip install -r requirements.txt
playwright install chromium
```

### Bước 3: Cấu Hình Tài Khoản (`.env`)
1. Đổi tên file `.env.example` thành `.env` (hoặc tạo một file `.env` mới hoàn toàn).
2. Mở file `.env` bằng Notepad và sửa lại biến `DEEPSEEK_ACCOUNTS` theo tài khoản của bạn:
   ```ini
   # Định dạng: email:password (bạn có thể thêm proxy ở cuối nếu muốn)
   DEEPSEEK_ACCOUNTS=your_email@gmail.com:your_password
   
   # Proxy sạch mặc định: Cloudflare WARP via sing-box (tích hợp trong ./ip)
   DEEPSEEK_PROXY=http://127.0.0.1:2080
   
   # API Key mà bạn tự đặt ra để gọi từ app khác (Claude, Cursor...)
   API_KEY=sk-my-secret-key-1
   PORT=5001
   HOST=0.0.0.0
   ```

### Bước 4: Đăng Nhập Lần Đầu Để Lấy Token (Tránh Lỗi RISK_DEVICE)
Vì DeepSeek bảo mật rất gắt, nếu bạn để script tự động chạy ngầm, rất dễ bị báo lỗi `RISK_DEVICE_DETECTED`. Lần đầu tiên, bạn hãy đăng nhập thủ công:
1. Mở Terminal và chạy lệnh:
   ```bash
   python login_helper.py
   ```
2. Một cửa sổ trình duyệt (có giao diện) sẽ hiện lên và tự động điền Email/Mật khẩu. 
3. Nếu xuất hiện xác minh hình ảnh (Captcha), bạn **chỉ cần dùng chuột kéo mảnh ghép**. 
4. Script sẽ tự động lấy Token và lưu vào file `.tokens.json` (Khi màn hình terminal báo `[THÀNH CÔNG]` là xong).

### Bước 5: Khởi Động Máy Chủ (Bridge)
Sau khi đã có token, những lần sau bạn không cần đăng nhập lại nữa. Chỉ cần chạy:
```bash
start_bridge.bat
```
Script sẽ tự động bật proxy WARP độc lập và khởi chạy máy chủ API tại `http://127.0.0.1:5001`.

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

### Cách 2: Thiết lập thủ công qua file `settings.json` của Claude

Bạn có thể cấu hình cố định bằng cách chỉnh sửa hoặc tạo file `settings.json` tại thư mục gốc của Claude (thường nằm ở `~/.claude/settings.json` đối với Linux/macOS, hoặc `%USERPROFILE%\.claude\settings.json` đối với Windows).

Hãy cấu hình phần `"env"` trong file JSON đó như sau:

```json
{
  "env": {
    "OPENAI_API_KEY": "sk-my-secret-key-1",
    "OPENAI_BASE_URL": "http://127.0.0.1:5001",
    "OPENAI_MODEL": "gpt-4o",
    "ANTHROPIC_API_KEY": "sk-my-secret-key-1",
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:5001",
    "ANTHROPIC_MODEL": "gpt-4o"
  }
}
```

Việc này giúp bạn khai báo sẵn các thông số backend để điều hướng Claude Code qua hệ thống cục bộ. Ở các lần tiếp theo, bạn chỉ cần gọi lệnh `claude` mà không cần thiết lập lại.

### Cách 3: Thiết lập thủ công qua biến môi trường (Terminal tạm thời)
Nếu không muốn ghi vào file `settings.json`, bạn có thể khai báo tạm thời qua Terminal cho từng phiên làm việc:
```powershell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:5001"
$env:ANTHROPIC_API_KEY  = "sk-my-secret-key-1"
$env:ANTHROPIC_MODEL    = "gpt-4o"
claude
```

---

## 📡 Danh Sách Model Hỗ Trợ

Hệ thống đã được tối ưu hóa về **1 Model Duy Nhất** để đảm bảo luôn bật tư duy sâu (DeepThink) cao nhất cho coding:

| Model Trực Tiếp | Các Tên Alias Hỗ Trợ | Chế Độ Suy Nghĩ (Reasoning) |
| :--- | :--- | :--- |
| **`deepseek-reasoner`** | `claude-3-7-sonnet`, `claude-3-5-sonnet`, `gpt-4o`, `deepseek-chat`, `deepseek-r1`, `qwen-max` | **BẬT 100% (Full DeepThink R1)** |

> **Lưu ý:** Bất kể ứng dụng hoặc client bên ngoài (Claude Code, Cursor, Cline, NextChat, Chatbox,...) truyền vào tên model nào, server đều tự động ánh xạ về `deepseek-reasoner` và kích hoạt chuỗi suy nghĩ Extended Thinking / Reasoning Content.

