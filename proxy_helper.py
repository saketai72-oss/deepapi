"""
Proxy Helper for DeepSeek API
- Quản lý Cloudflare WARP Proxy (từ C:\\code\\python\\ip, cổng 2080)
- Kiểm tra tốc độ, độ trễ và độ sạch của Proxy với DeepSeek
- Tìm kiếm và lọc proxy công cộng tốc độ cao trên thế giới
"""

import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.error

# Force UTF-8 on Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

WARP_DIR = r"C:\code\python\ip"
SING_BOX_EXE = os.path.join(WARP_DIR, "bin", "sing-box.exe")
SING_BOX_CONFIG = os.path.join(WARP_DIR, "singbox_config.json")
LOCAL_WARP_PROXY = "http://127.0.0.1:2080"

_warp_process = None

def is_port_open(host="127.0.0.1", port=2080, timeout=1.0) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0

def start_warp_service() -> bool:
    """Khởi động Cloudflare WARP sing-box ở chế độ chạy nền không mở cửa sổ"""
    global _warp_process
    if is_port_open("127.0.0.1", 2080):
        print("[warp] Dịch vụ WARP Proxy (127.0.0.1:2080) đã đang chạy!")
        return True

    if not os.path.exists(SING_BOX_EXE) or not os.path.exists(SING_BOX_CONFIG):
        print(f"[warp] Không tìm thấy sing-box hoặc cấu hình tại {WARP_DIR}")
        return False

    print("[warp] Đang khởi động Cloudflare WARP Proxy tại 127.0.0.1:2080...")
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_NO_WINDOW = 0x08000000
    creation_flags = (CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW) if sys.platform == "win32" else 0
    _warp_process = subprocess.Popen(
        [SING_BOX_EXE, "run", "-c", SING_BOX_CONFIG],
        creationflags=creation_flags,
    )
    for _ in range(12):
        time.sleep(0.5)
        if is_port_open("127.0.0.1", 2080):
            print("[warp] WARP Proxy đã sẵn sàng trên 127.0.0.1:2080!")
            return True
            
    print("[warp] Khởi động WARP thất bại hoặc quá thời gian chờ.")
    return False

def ensure_warp_proxy() -> str:
    """Đảm bảo WARP proxy chạy trên 127.0.0.1:2080 và trả về URL proxy"""
    if is_port_open("127.0.0.1", 2080):
        return LOCAL_WARP_PROXY
    if start_warp_service():
        return LOCAL_WARP_PROXY
    return None

def test_proxy(proxy_url: str, test_url: str = "https://chat.deepseek.com") -> dict:
    """Kiểm tra độ trễ và IP của proxy khi kết nối tới DeepSeek"""
    proxy_handler = urllib.request.ProxyHandler({
        "http": proxy_url,
        "https": proxy_url,
    })
    opener = urllib.request.build_opener(proxy_handler)

    res = {"proxy": proxy_url, "alive": False, "ip": None, "latency_ms": None, "error": None}
    try:
        t0 = time.time()
        # 1. Kiểm tra IP
        req_ip = urllib.request.Request("https://api.ipify.org?format=json", headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req_ip, timeout=5) as r:
            ip_data = json.loads(r.read().decode())
            res["ip"] = ip_data.get("ip")
        
        # 2. Kiểm tra DeepSeek
        t1 = time.time()
        req_ds = urllib.request.Request(test_url, headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req_ds, timeout=6) as r:
            latency = (time.time() - t1) * 1000
            res["latency_ms"] = round(latency, 1)
            res["alive"] = (r.status == 200)
    except Exception as e:
        res["error"] = str(e)

    return res

def fetch_free_proxies(max_candidates=15) -> list:
    """Lấy danh sách proxy quốc tế miễn phí từ các nguồn uy tín và kiểm tra độ trễ"""
    print("[proxy] Đang quét danh sách proxy quốc tế...")
    urls = [
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all&ssl=yes&anonymity=elite",
        "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    ]
    candidates = []
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                lines = resp.read().decode("utf-8", errors="ignore").splitlines()
                for line in lines:
                    line = line.strip()
                    if line and ":" in line and not line.startswith("#"):
                        candidates.append(f"http://{line}")
                    if len(candidates) >= max_candidates * 3:
                        break
            if len(candidates) >= max_candidates:
                break
        except Exception:
            pass

    import concurrent.futures
    valid_proxies = []
    print(f"[proxy] Đang kiểm tra {min(len(candidates), 20)} proxy với DeepSeek...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(test_proxy, p): p for p in candidates[:20]}
        for f in concurrent.futures.as_completed(futures):
            r = f.result()
            if r["alive"] and r["latency_ms"] and r["latency_ms"] < 2500:
                valid_proxies.append(r)
                print(f" -> Proxy sống: {r['proxy']} (IP: {r['ip']}, Ping: {r['latency_ms']}ms)")

    valid_proxies.sort(key=lambda x: x["latency_ms"] or 9999)
    return valid_proxies

if __name__ == "__main__":
    print("=== KIỂM TRA PROXY HỆ THỐNG ===")
    start_warp_service()
    warp_result = test_proxy(LOCAL_WARP_PROXY)
    print("\nKết quả Cloudflare WARP (C:\\code\\python\\ip):")
    print(json.dumps(warp_result, indent=2))
