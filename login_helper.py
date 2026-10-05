"""
DeepSeek Auto-Login Helper
Mở trình duyệt, tự động điền Email và Password. 
Người dùng chỉ cần kéo mảnh ghép Captcha (nếu có), script sẽ tự bắt token và lưu vào .tokens.json mà KHÔNG CẦN bấm F12!
"""

import sys
import os
import json
import time
import re

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

from cloakbrowser import launch

TOKEN_FILE = os.path.join(os.path.dirname(__file__), ".tokens.json")

def save_token(email: str, token: str):
    tokens = {}
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                tokens = json.load(f)
        except Exception:
            pass
    tokens[email] = token
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)
    print(f"\n[THÀNH CÔNG] Đã lưu token cho {email} vào file .tokens.json!")

def login_account(email: str, password: str):
    print("=" * 60)
    print(f"ĐANG KHỞI CHẠY ĐĂNG NHẬP CHO: {email}")
    print("Trình duyệt sẽ mở lên và tự động điền tài khoản...")
    print("Nếu có Captcha kéo mảnh ghép, bạn chỉ cần kéo mảnh ghép 1 giây.")
    print("=" * 60)

    browser = launch(
        headless=False,  # Mở cửa sổ trực quan để người dùng thấy và kéo captcha nếu có
        humanize=True,
        args=['--fingerprint-platform=windows']
    )
    context = browser.new_context()
    page = context.new_page()

    captured_token = None

    # Lắng nghe request network để bắt token nếu API trả về
    def on_response(resp):
        nonlocal captured_token
        if "/api/v0/users/login" in resp.url:
            try:
                data = resp.json()
                t = data.get("data", {}).get("biz_data", {}).get("user", {}).get("token") or \
                    data.get("data", {}).get("biz_data", {}).get("token")
                if t:
                    captured_token = t
            except Exception:
                pass

    page.on("response", on_response)

    try:
        page.goto("https://chat.deepseek.com/sign_in", wait_until="commit", timeout=60000)
    except Exception as e:
        print(f"Lỗi tải trang: {e}")

    # Đợi form đăng nhập xuất hiện
    print("Đang đợi form đăng nhập...")
    for _ in range(15):
        time.sleep(1)
        try:
            inputs = page.query_selector_all("input")
            if len(inputs) >= 2:
                break
        except Exception:
            pass

    try:
        inputs = page.query_selector_all("input")
        if len(inputs) >= 2:
            print("Đang tự động điền Email và Password...")
            inputs[0].fill(email)
            time.sleep(0.5)
            inputs[1].fill(password)
            time.sleep(0.5)
    except Exception as e:
        print(f"Lỗi khi truy vấn inputs: {e}")
        inputs = []

        try:
            # Check checkbox điều khoản nếu có
            checkboxes = page.query_selector_all("input[type='checkbox']")
            for cb in checkboxes:
                try:
                    if not cb.is_checked():
                        cb.check()
                except Exception:
                    pass

            # Tìm và click nút đăng nhập
            buttons = page.query_selector_all("button")
            for btn in buttons:
                txt = btn.inner_text().strip().lower()
                if any(k in txt for k in ["đăng nhập", "login", "sign in", "tiếp tục", "continue"]):
                    print(f"Tự động click nút: '{btn.inner_text().strip()}'")
                    btn.click()
                    break
        except Exception as e:
            print(f"Lỗi khi điền form/click nút: {e}")

    print("\nĐang chờ đăng nhập thành công để tự động lấy token...")
    print("(Nếu màn hình hiện hình xếp hình / Captcha, bạn hãy kéo vào đúng vị trí nhé)")

    # Chờ lấy token từ localStorage hoặc network (tối đa 60s)
    success = False
    for i in range(60):
        time.sleep(1)
        
        # Cách 1: Bắt qua network
        if captured_token and len(captured_token.strip()) > 20:
            save_token(email, captured_token.strip())
            success = True
            break

        # Cách 2: Lấy từ LocalStorage
        try:
            raw_token = page.evaluate("() => window.localStorage.getItem('userToken')")
            if raw_token:
                tok = None
                if raw_token.startswith("{"):
                    try:
                        parsed = json.loads(raw_token)
                        if isinstance(parsed, dict):
                            val = parsed.get("value")
                            if isinstance(val, str) and len(val.strip()) > 20 and "null" not in val.lower():
                                tok = val.strip()
                    except Exception:
                        pass
                elif len(raw_token.strip()) > 20 and "null" not in raw_token.lower():
                    tok = raw_token.strip()

                if tok:
                    save_token(email, tok)
                    success = True
                    break
        except Exception:
            pass

        # Kiểm tra nếu đã chuyển vào trang chat chính
        if "/sign_in" not in page.url and ("chat" in page.url):
            try:
                raw_token = page.evaluate("() => window.localStorage.getItem('userToken')")
                if raw_token:
                    tok = None
                    if raw_token.startswith("{"):
                        try:
                            parsed = json.loads(raw_token)
                            if isinstance(parsed, dict):
                                val = parsed.get("value")
                                if isinstance(val, str) and len(val.strip()) > 20 and "null" not in val.lower():
                                    tok = val.strip()
                        except Exception:
                            pass
                    elif len(raw_token.strip()) > 20 and "null" not in raw_token.lower():
                        tok = raw_token.strip()

                    if tok:
                        save_token(email, tok)
                        success = True
                        break
            except Exception:
                pass

    if not success:
        print("\n[HẾT THỜI GIAN] Chưa lấy được token. Vui lòng kiểm tra lại tài khoản hoặc thao tác trên màn hình.")

    time.sleep(2)
    browser.close()

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        email = sys.argv[1]
        password = sys.argv[2]
    else:
        # Lấy từ biến môi trường .env
        email = os.environ.get("DEEPSEEK_EMAIL", "")
        password = os.environ.get("DEEPSEEK_PASSWORD", "")

    if not email or not password:
        print("[!] Thiếu thông tin tài khoản. Vui lòng truyền: python login_helper.py <email> <password> hoặc cấu hình .env")
        sys.exit(1)

    login_account(email, password)
