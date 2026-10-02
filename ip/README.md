# BỘ CÔNG CỤ TỰ ĐỘNG TẠO & SỬ DỤNG IPV6 TRÊN WINDOWS

Công cụ này giúp bạn tự động tạo và cấp địa chỉ **IPv6 Public miễn phí** từ hạ tầng Cloudflare WARP, tích hợp sẵn engine chạy nền tốc độ cao (không cần cài đặt driver kernel phức tạp hay phân quyền Admin).

---

## 🚀 Cách sử dụng nhanh nhất (Dành cho mọi người)

Trong thư mục `c:\python\ip`, bạn chỉ cần nhấp đúp chuột vào các file:

1. **`run.bat`**: Mở Menu điều khiển trực quan (Bật/Tắt, Đổi IP mới, Kiểm tra, Xuất file WireGuard).
2. **`start_ipv6.bat`**: Bật ngay IPv6 cho toàn bộ máy tính (Trình duyệt Chrome, Edge sẽ tự nhận IPv6).
3. **`stop_ipv6.bat`**: Tắt IPv6 và đưa thiết lập mạng về trạng thái bình thường.
4. **`test_ipv6.bat`**: Kiểm tra địa chỉ IPv6 thực tế và độ trễ ping.

---

## 💻 Sử dụng qua dòng lệnh (CLI)

Mở PowerShell hoặc CMD tại thư mục `c:\python\ip`:

* **Mở menu tương tác:**
  ```powershell
  python ipv6_tool.py
  ```

* **Bật IPv6:**
  ```powershell
  python ipv6_tool.py start
  ```

* **Tắt IPv6:**
  ```powershell
  python ipv6_tool.py stop
  ```

* **Kiểm tra trạng thái IPv6:**
  ```powershell
  python ipv6_tool.py test
  ```

* **Cấp một địa chỉ IPv6 mới:**
  ```powershell
  python ipv6_tool.py new
  ```

---

## 📂 Các file được tạo ra trong thư mục:

* `warp_ipv6.conf`: File cấu hình định dạng WireGuard tiêu chuẩn. Bạn có thể copy file này để nạp vào Router (OpenWrt, MikroTik), điện thoại (WireGuard App) hoặc máy tính khác.
* `account.json`: Chứa thông tin Private Key, Public Key, địa chỉ IPv6 và IPv4 được cấp.
* `bin/sing-box.exe`: Engine mạng portable độc lập giúp kết nối tunnel WireGuard mà không cần cài đặt driver.

---

## 🌐 Cấu hình Proxy thủ công (Nếu bạn chỉ muốn một số ứng dụng dùng IPv6)
Nếu không muốn bật System Proxy toàn hệ thống, bạn có thể trỏ phần mềm (trình duyệt, IDM, Telegram, Python script...) vào Proxy nội bộ:
* **Protocol:** SOCKS5 hoặc HTTP
* **Host:** `127.0.0.1`
* **Port:** `2080`
