import os
import sys

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import json
import time
import base64
import datetime
import subprocess
import urllib.request
import urllib.error

# Ensure dependencies
try:
    from nacl.public import PrivateKey
    import requests
    import psutil
except ImportError:
    print("[*] Đang cài đặt thư viện phụ thuộc (PyNaCl, requests, psutil)...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyNaCl", "requests", "psutil"])
    from nacl.public import PrivateKey
    import requests
    import psutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(BASE_DIR, "bin")
SING_BOX_EXE = os.path.join(BIN_DIR, "sing-box.exe")
ACCOUNT_FILE = os.path.join(BASE_DIR, "account.json")
WG_CONF_FILE = os.path.join(BASE_DIR, "warp_ipv6.conf")
CONFIG_FILE = os.path.join(BASE_DIR, "singbox_config.json")
PID_FILE = os.path.join(BASE_DIR, "service.pid")
LOG_FILE = os.path.join(BASE_DIR, "singbox.log")
PROXY_PORT = 2080

def refresh_windows_proxy():
    """Báo hiệu cho Windows và trình duyệt cập nhật lại thiết lập Proxy ngay lập tức"""
    if sys.platform == "win32":
        try:
            import ctypes
            INTERNET_OPTION_SETTINGS_CHANGED = 39
            INTERNET_OPTION_REFRESH = 37
            ctypes.windll.Wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
            ctypes.windll.Wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
        except Exception:
            pass

def set_windows_system_proxy(enable=True, host="127.0.0.1", port=PROXY_PORT):
    """Bật hoặc tắt System Proxy của Windows trong Registry"""
    if sys.platform != "win32":
        return
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            0, winreg.KEY_SET_VALUE
        )
        if enable:
            proxy_server = f"{host}:{port}"
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, proxy_server)
            winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, "<-loopback>;<local>")
        else:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        refresh_windows_proxy()
    except Exception as e:
        print(f"[!] Không thể cập nhật Windows Proxy Registry: {e}")

def ensure_binaries():
    """Tải sing-box portable nếu chưa có"""
    if os.path.exists(SING_BOX_EXE):
        return
    print("[*] Đang tải engine sing-box portable...")
    os.makedirs(BIN_DIR, exist_ok=True)
    url = "https://github.com/SagerNet/sing-box/releases/download/v1.14.0/sing-box-1.14.0-windows-amd64.zip"
    import zipfile, io
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        content = resp.read()
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for name in z.namelist():
            if name.endswith("sing-box.exe"):
                with open(SING_BOX_EXE, "wb") as f:
                    f.write(z.read(name))
                print(f"[+] Đã giải nén: {SING_BOX_EXE}")
                break

def generate_warp_account():
    """Tạo tài khoản WARP mới và lấy địa chỉ IPv6 chính chủ từ Cloudflare"""
    print("[*] 1. Khởi tạo cặp khóa mật mã Curve25519...")
    priv = PrivateKey.generate()
    priv_b64 = base64.b64encode(bytes(priv)).decode()
    pub_b64 = base64.b64encode(bytes(priv.public_key)).decode()

    print("[*] 2. Đăng ký tài khoản Cloudflare WARP để nhận dải IPv6...")
    url = "https://api.cloudflareclient.com/v0a2158/reg"
    headers = {
        "User-Agent": "okhttp/3.12.1",
        "Content-Type": "application/json; charset=UTF-8"
    }
    data = {
        "key": pub_b64,
        "install_id": "",
        "fcm_token": "",
        "tos": datetime.datetime.now(datetime.timezone.utc).isoformat()[:19] + "Z",
        "model": "PC",
        "serial_number": "",
        "locale": "en_US"
    }
    resp = requests.post(url, json=data, headers=headers, timeout=15)
    if resp.status_code not in (200, 201):
        raise Exception(f"Lỗi đăng ký Cloudflare API (HTTP {resp.status_code}): {resp.text}")

    res = resp.json()
    client_id = res.get("config", {}).get("client_id", "")
    reserved = list(base64.b64decode(client_id)) if client_id else [0, 0, 0]
    ipv4 = res["config"]["interface"]["addresses"]["v4"]
    ipv6 = res["config"]["interface"]["addresses"]["v6"]
    peer_pub = res["config"]["peers"][0]["public_key"]

    account_data = {
        "private_key": priv_b64,
        "public_key": pub_b64,
        "peer_public_key": peer_pub,
        "ipv4": ipv4,
        "ipv6": ipv6,
        "client_id": client_id,
        "reserved": reserved,
        "endpoint": "162.159.192.1",
        "port": 2408,
        "created_at": str(datetime.datetime.now())
    }

    with open(ACCOUNT_FILE, "w", encoding="utf-8") as f:
        json.dump(account_data, f, indent=2)

    # 3. Tạo file WireGuard tiêu chuẩn (.conf) để dùng cho router / WireGuard App
    reserved_str = f"{reserved[0]}, {reserved[1]}, {reserved[2]}"
    wg_content = f"""[Interface]
PrivateKey = {priv_b64}
Address = {ipv4}/32, {ipv6}/128
DNS = 1.1.1.1, 2606:4700:4700::1111
MTU = 1280

[Peer]
PublicKey = {peer_pub}
Endpoint = 162.159.192.1:2408
AllowedIPs = 0.0.0.0/0, ::/0
# Reserved = [{reserved_str}]
"""
    with open(WG_CONF_FILE, "w", encoding="utf-8") as f:
        f.write(wg_content)

    build_singbox_config(account_data)

    print("\n" + "="*50)
    print(" [THÀNH CÔNG] ĐÃ CẤP IPV6 MỚI!")
    print(f" -> IPv6 Public: {ipv6}")
    print(f" -> IPv4 Client: {ipv4}")
    print(f" -> File WireGuard config: {WG_CONF_FILE}")
    print("="*50 + "\n")
    return account_data

def build_singbox_config(account_data):
    """Tạo file cấu hình sing-box tương thích v1.14+"""
    cfg = {
        "log": {
            "level": "warn",
            "output": LOG_FILE
        },
        "dns": {
            "servers": [
                {
                    "tag": "dns-cloudflare",
                    "type": "udp",
                    "server": "1.1.1.1",
                    "detour": "warp-ep"
                },
                {
                    "tag": "dns-google",
                    "type": "udp",
                    "server": "8.8.8.8",
                    "detour": "warp-ep"
                }
            ],
            "strategy": "prefer_ipv6"
        },
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": PROXY_PORT
            }
        ],
        "endpoints": [
            {
                "type": "wireguard",
                "tag": "warp-ep",
                "domain_strategy": "prefer_ipv6",
                "address": [
                    f"{account_data['ipv4']}/32",
                    f"{account_data['ipv6']}/128"
                ],
                "private_key": account_data["private_key"],
                "peers": [
                    {
                        "address": account_data.get("endpoint", "162.159.192.1"),
                        "port": account_data.get("port", 2408),
                        "public_key": account_data["peer_public_key"],
                        "allowed_ips": ["0.0.0.0/0", "::/0"],
                        "reserved": account_data["reserved"]
                    }
                ],
                "mtu": 1280
            }
        ],
        "route": {
            "default_domain_resolver": "dns-cloudflare",
            "rules": [
                {"outbound": "warp-ep", "action": "route"}
            ]
        }
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def is_running():
    """Kiểm tra xem sing-box có đang chạy hay không"""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                if "sing-box" in proc.name().lower():
                    return True
        except Exception:
            pass

    for p in psutil.process_iter(["pid", "name"]):
        try:
            if "sing-box" in p.info["name"].lower():
                with open(PID_FILE, "w") as f:
                    f.write(str(p.info["pid"]))
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False

def start_ipv6(system_proxy=True, run_test=False):
    """Bật kết nối IPv6 chạy nền"""
    ensure_binaries()

    if not os.path.exists(ACCOUNT_FILE):
        print("[*] Chưa có tài khoản, đang tự động tạo IPv6...")
        generate_warp_account()

    if is_running():
        print("[!] Dịch vụ IPv6 đã đang hoạt động!")
        if system_proxy:
            set_windows_system_proxy(enable=True)
        if run_test: test_ipv6()
        return

    with open(ACCOUNT_FILE, "r", encoding="utf-8") as f:
        account_data = json.load(f)

    build_singbox_config(account_data)

    print("[*] Đang khởi động tunnel IPv6...")
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    log_file_obj = open(LOG_FILE, "a", encoding="utf-8")
    proc = subprocess.Popen(
        [SING_BOX_EXE, "run", "-c", CONFIG_FILE],
        stdout=log_file_obj,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags,
        close_fds=True
    )

    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))

    print("[*] Đang thiết lập kết nối (khoảng 2 giây)...")
    time.sleep(2)

    if is_running():
        print("[+] Tunnel IPv6 ĐÃ BẬT THÀNH CÔNG!")
        print(f" -> Proxy nội bộ (SOCKS5/HTTP): 127.0.0.1:{PROXY_PORT}")
        if system_proxy:
            set_windows_system_proxy(enable=True)
            print(" -> Chế độ Windows System Proxy: [ĐÃ BẬT] (Tất cả trình duyệt Chrome, Edge sẽ dùng IPv6)")
        if run_test: test_ipv6()
    else:
        print("[-] Không thể khởi động tunnel. Chi tiết log:")
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                print(f.read())

def stop_ipv6():
    """Dừng dịch vụ IPv6 và hoàn trả cấu hình mạng"""
    print("[*] Đang tắt kết nối IPv6...")
    stopped = False

    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                p = psutil.Process(pid)
                p.terminate()
                p.wait(timeout=3)
                stopped = True
        except Exception:
            pass
        finally:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)

    for p in psutil.process_iter(["pid", "name"]):
        try:
            if "sing-box" in p.info["name"].lower():
                p.terminate()
                stopped = True
        except Exception:
            pass

    set_windows_system_proxy(enable=False)
    print("[+] Đã tắt dịch vụ IPv6.")
    print("[+] Đã hoàn trả Windows System Proxy về trạng thái bình thường.")

def test_ipv6():
    """Kiểm tra địa chỉ IPv6 thực tế"""
    print("\n" + "="*45)
    print("         KẾT QUẢ KIỂM TRA IPV6")
    print("="*45)
    
    running = is_running()
    proxies = {
        "http": f"http://127.0.0.1:{PROXY_PORT}",
        "https": f"http://127.0.0.1:{PROXY_PORT}"
    } if running else None

    # 1. Kiểm tra IPv6 Public thực tế
    try:
        t0 = time.time()
        r = requests.get("https://v6.ident.me", proxies=proxies, timeout=6)
        latency = int((time.time() - t0) * 1000)
        print(f" [OK] IPv6 Public: {r.text.strip()}")
        print(f" [OK] Độ trễ (Ping IPv6): {latency} ms")
    except Exception:
        print(" [-] Không kết nối được IPv6 qua v6.ident.me")

    # 2. Kiểm tra Cloudflare Trace
    try:
        r = requests.get("https://1.1.1.1/cdn-cgi/trace", proxies=proxies, timeout=6)
        lines = dict(line.split("=", 1) for line in r.text.strip().split("\n") if "=" in line)
        print(f" [OK] Trạng thái WARP: {lines.get('warp', 'off').upper()}")
        print(f" [OK] Server Hub: {lines.get('colo', 'Unknown')} (Quốc gia: {lines.get('loc', 'Unknown')})")
    except Exception:
        pass

    # 3. Kiểm tra IP tổng thể
    try:
        r = requests.get("https://api64.ipify.org?format=json", proxies=proxies, timeout=6)
        print(f" [OK] IP Nhận diện: {r.json().get('ip')}")
    except Exception:
        pass

    status = "ĐANG BẬT (ON)" if running else "ĐANG TẮT (OFF)"
    print(f" [INFO] Trạng thái Tunnel: {status}")
    print("="*45 + "\n")

def show_menu():
    while True:
        status_str = "ĐANG BẬT [ON]" if is_running() else "ĐANG TẮT [OFF]"
        print("="*48)
        print("      BỘ CÔNG CỤ TẠO & SỬ DỤNG IPV6 TỰ ĐỘNG")
        print(f"           Trạng thái: {status_str}")
        print("="*48)
        print("  1. Bật IPv6 (Start - Cho toàn bộ máy tính)")
        print("  2. Tắt IPv6 (Stop - Khôi phục mạng ban đầu)")
        print("  3. Kiểm tra kết nối IPv6 (Test)")
        print("  4. Cấp lại IPv6 mới (Reset/Generate New IP)")
        print("  5. Xuất file cấu hình WireGuard (.conf)")
        print("  0. Thoát")
        print("="*48)

        choice = input("Nhập lựa chọn của bạn [0-5]: ").strip()
        if choice == "1":
            start_ipv6(system_proxy=True)
        elif choice == "2":
            stop_ipv6()
        elif choice == "3":
            test_ipv6()
        elif choice == "4":
            confirm = input("Bạn có muốn tạo lại địa chỉ IPv6 mới không? (y/n): ").strip().lower()
            if confirm == "y":
                stop_ipv6()
                generate_warp_account()
                start_ipv6(system_proxy=True)
        elif choice == "5":
            if os.path.exists(WG_CONF_FILE):
                with open(WG_CONF_FILE, "r") as f:
                    print("\n--- NỘI DUNG FILE WARP_IPV6.CONF ---")
                    print(f.read())
                    print("------------------------------------\n")
            else:
                print("[!] Chưa có file cấu hình. Vui lòng chọn 4 để tạo trước.")
        elif choice == "0":
            print("Tạm biệt!")
            break
        else:
            print("[!] Lựa chọn không hợp lệ.")
        input("Nhấn Enter để tiếp tục...")
        os.system("cls" if os.name == "nt" else "clear")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "start":
            start_ipv6(system_proxy=True)
            print("\n[i] Tunnel đang hoạt động. Nhấn Ctrl+C để dừng dịch vụ và khôi phục mạng...")
            try:
                while is_running():
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n[*] Đang dừng theo yêu cầu...")
                stop_ipv6()
        elif cmd == "stop":
            stop_ipv6()
        elif cmd == "test":
            test_ipv6()
        elif cmd == "new":
            generate_warp_account()
        elif cmd == "status":
            print("RUNNING" if is_running() else "STOPPED")
        else:
            print("Lệnh hợp lệ: start | stop | test | new | status")
    else:
        show_menu()
