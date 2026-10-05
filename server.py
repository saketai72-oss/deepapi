"""
DeepSeek API Server - OpenAI Compatible
Flask WSGI server (không dùng asyncio, không conflict với cloakbrowser)
"""

import sys
import os
import atexit
import subprocess

def cleanup_on_exit():
    print("\n[cleanup] Dang don dep tien trinh ngam va khoi phuc mang...")
    try:
        # Run stop command of ipv6_tool.py to restore Windows System Proxy if it was set
        ipv6_tool_path = os.path.join(os.path.dirname(__file__), "ip", "ipv6_tool.py")
        if os.path.exists(ipv6_tool_path):
            subprocess.run([sys.executable, ipv6_tool_path, "stop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Fallback kill
        subprocess.run(["taskkill", "/F", "/IM", "sing-box.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

atexit.register(cleanup_on_exit)

# Force UTF-8 encoding for stdout and stderr on Windows to avoid UnicodeEncodeError
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

def load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("=", 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip()
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    os.environ[key] = val

load_env()

import json
import re
import time
import uuid
import threading
from flask import Flask, request, Response, jsonify

from deepseek_client import (
    login, create_session, get_pow,
    call_completion, call_continue,
    delete_session, parse_sse_lines,
    collect_response, make_session, get_model_type,
    upload_context_file, delete_file,
)
from proxy_helper import ensure_warp_proxy


# ============================================================
# CONFIG
# ============================================================

VALID_API_KEYS = {
    os.environ.get("API_KEY", "sk-my-secret-key-1"),
    "sk-my-secret-key-1",
    "sk-f556947a5dd1906cc1d654c8de42c0bc355abacd4bdcad99",
}

ENABLE_CONTEXT_FILE = os.environ.get("ENABLE_CONTEXT_FILE", "true").lower() in ("true", "1", "yes")
CONTEXT_FILE_THRESHOLD = int(os.environ.get("CONTEXT_FILE_THRESHOLD", "30000"))

DEFAULT_PROXY = os.environ.get("DEEPSEEK_PROXY", "").strip() or None
if not DEFAULT_PROXY:
    try:
        DEFAULT_PROXY = ensure_warp_proxy()
    except Exception:
        pass

ACCOUNTS = []
accounts_env = os.environ.get("DEEPSEEK_ACCOUNTS", "")
if accounts_env:
    for acc_str in accounts_env.split(","):
        acc_str = acc_str.strip()
        if not acc_str:
            continue
        parts = acc_str.split(":")
        if len(parts) >= 2:
            acc_email = parts[0].strip()
            # If parts has proxy like http://127.0.0.1:2080 (contains colons)
            if len(parts) >= 3 and (parts[2].strip().startswith("http") or parts[2].strip().startswith("socks")):
                acc_pass = parts[1].strip()
                acc_proxy = ":".join(parts[2:]).strip()
            else:
                acc_pass = parts[1].strip()
                acc_proxy = DEFAULT_PROXY
            ACCOUNTS.append({
                "email": acc_email,
                "password": acc_pass,
                "proxy": acc_proxy,
                "token": None
            })

if not ACCOUNTS:
    email = os.environ.get("DEEPSEEK_EMAIL", "").strip()
    password = os.environ.get("DEEPSEEK_PASSWORD", "").strip()
    if email or password:
        ACCOUNTS.append({
            "email":    email,
            "password": password,
            "proxy":    DEFAULT_PROXY,
            "token":    None,
        })
    else:
        print("[warn] Chưa cấu hình DEEPSEEK_EMAIL hoặc DEEPSEEK_PASSWORD trong file .env")

AVAILABLE_MODELS = [
    "deepseek-reasoner",
]

MODEL_ALIASES = {
    # Tất cả các alias đều quy về 1 model duy nhất
    "deepseek-chat": "deepseek-reasoner",
}

# ============================================================
# TOKEN MANAGER (WITH DISK CACHE)
# ============================================================

TOKEN_CACHE_FILE = os.path.join(os.path.dirname(__file__), ".tokens.json")
_account_lock = threading.Lock()
_current_account_index = 0

def load_cached_tokens():
    if os.path.exists(TOKEN_CACHE_FILE):
        try:
            with open(TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
                existing_emails = {acc.get("email") for acc in ACCOUNTS}
                for email, tok in cached.items():
                    if email and tok:
                        if email not in existing_emails:
                            ACCOUNTS.append({
                                "email": email,
                                "password": "",
                                "proxy": DEFAULT_PROXY,
                                "token": tok
                            })
                            existing_emails.add(email)
                        else:
                            for acc in ACCOUNTS:
                                if acc.get("email") == email:
                                    acc["token"] = tok
                        print(f"[auth] Đã nạp token đệm từ file cho: {email}")
        except Exception as e:
            print(f"[auth] Không thể đọc token đệm: {e}")
            
    # Đăng ký proxy tương ứng cho từng tài khoản vào Playwright session
    for acc in ACCOUNTS:
        if acc.get("proxy") and acc.get("email"):
            try:
                make_session().register_account_proxy(acc.get("email"), acc.get("proxy"))
                print(f"[proxy] Gắn proxy {acc.get('proxy')} cho tài khoản {acc.get('email')}")
            except Exception as e:
                print(f"[proxy] Lỗi đăng ký proxy cho {acc.get('email')}: {e}")

def save_cached_tokens():
    try:
        data = {acc["email"]: acc["token"] for acc in ACCOUNTS if acc.get("email") and acc.get("token")}
        if data:
            with open(TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[auth] Không thể lưu token đệm: {e}")

load_cached_tokens()

def get_active_token() -> str:
    global _current_account_index
    with _account_lock:
        if not ACCOUNTS:
            raise RuntimeError("Không có tài khoản DeepSeek nào được cấu hình!")
            
        for _ in range(len(ACCOUNTS)):
            acc = ACCOUNTS[_current_account_index]
            if not acc.get("token"):
                try:
                    print(f"[auth] Đang login tài khoản #{_current_account_index + 1}: {acc.get('email')}")
                    if acc.get("proxy"):
                        try:
                            make_session().register_account_proxy(acc.get("email"), acc.get("proxy"))
                        except Exception:
                            pass
                    token = login(
                        email=acc.get("email"),
                        password=acc.get("password"),
                    )
                    acc["token"] = token
                    save_cached_tokens()
                    print(f"[auth] Login OK cho tài khoản #{_current_account_index + 1}: {token[:20]}...")
                except Exception as e:
                    print(f"[auth] Tài khoản #{_current_account_index + 1} ({acc.get('email')}) đăng nhập lỗi: {e}")
                    _current_account_index = (_current_account_index + 1) % len(ACCOUNTS)
                    continue
            
            token = acc["token"]
            _current_account_index = (_current_account_index + 1) % len(ACCOUNTS)
            return token
            
        raise RuntimeError("Tất cả các tài khoản DeepSeek được cấu hình đều đăng nhập thất bại!")

def invalidate_token(token: str = None, reason: str = ""):
    reason_l = str(reason).lower() if reason else ""
    if not any(k in reason_l for k in ("401", "unauthorized", "token invalid", "token_expired")):
        print(f"[auth] Giữ lại token, bỏ qua invalidate do lỗi không phải 401 Unauthorized: {reason[:100] if reason else 'No reason'}")
        return

    with _account_lock:
        if token:
            for acc in ACCOUNTS:
                if acc.get("token") == token:
                    print(f"[auth] Invalidate token của tài khoản: {acc.get('email')}")
                    acc["token"] = None
                    break
        else:
            for acc in ACCOUNTS:
                acc["token"] = None
        save_cached_tokens()

def cleanup_session_async(token: str, session_id: str, sess, file_ids: list = None):
    """Xóa session chat và file upload ngầm không để sót rác trên DeepSeek"""
    if not token and not session_id and not file_ids:
        return
    def _do_delete():
        try:
            time.sleep(1.0)
            if file_ids:
                for fid in file_ids:
                    try:
                        delete_file(token, fid, session=sess)
                    except Exception:
                        pass
            if session_id:
                delete_session(token, session_id, http_session=sess)
        except Exception:
            pass
    threading.Thread(target=_do_delete, daemon=True).start()


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# ============================================================
# AUTH
# ============================================================

def get_caller_key():
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        key = auth[7:].strip()
        if key:
            return key
    key = request.headers.get("x-api-key", "").strip()
    if key:
        return key
    key = request.headers.get("X-Api-Key", "").strip()
    if key:
        return key
    return None

def require_auth(is_anthropic=False):
    key = get_caller_key()
    if not key:
        if is_anthropic:
            return jsonify({"type": "error", "error": {"type": "authentication_error", "message": "Missing API key"}}), 401
        return jsonify({"error": {"message": "Missing API key", "type": "invalid_request_error"}}), 401
    if VALID_API_KEYS and key not in VALID_API_KEYS:
        if is_anthropic:
            return jsonify({"type": "error", "error": {"type": "authentication_error", "message": "Invalid API key"}}), 401
        return jsonify({"error": {"message": "Invalid API key", "type": "invalid_request_error"}}), 401
    return None

# ============================================================
# PROMPT BUILDER & TOOL CALL PARSER
# ============================================================

def parse_tool_calls_from_text(text: str):
    if not text:
        return False, [], text

    tool_calls = []
    clean_text = text

    # 0. Match DeepSeek DSML tool calls (<｜｜DSML｜｜ calls> ... </｜｜DSML｜｜ calls>)
    if "<" in text and "DSML" in text:
        pattern_invoke = r"<[|｜]{2}DSML[|｜]{2}\s*invoke\s+name=[\"'](.*?)[\"']\s*>([\s\S]*?)</[|｜]{2}DSML[|｜]{2}\s*invoke>"
        pattern_param = r"<[|｜]{2}DSML[|｜]{2}\s*parameter\s+name=[\"'](.*?)[\"'][^>]*>([\s\S]*?)</[|｜]{2}DSML[|｜]{2}\s*parameter>"
        matches_dsml = re.findall(pattern_invoke, text)
        if matches_dsml:
            for name, body in matches_dsml:
                raw_params = re.findall(pattern_param, body)
                params = {}
                for p_name, p_val in raw_params:
                    p_val = p_val.strip()
                    if (p_val.startswith("{") and p_val.endswith("}")) or (p_val.startswith("[") and p_val.endswith("]")):
                        try:
                            p_val = json.loads(p_val)
                        except Exception:
                            pass
                    params[p_name] = p_val
                tool_calls.append({
                    "id": f"call_{uuid.uuid4().hex[:16]}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(params, ensure_ascii=False)
                    }
                })
            pattern_calls_block = r"<[|｜]{2}DSML[|｜]{2}\s*calls>[\s\S]*?</[|｜]{2}DSML[|｜]{2}\s*calls>"
            clean_text = re.sub(pattern_calls_block, "", text).strip()
            return True, tool_calls, clean_text

    # 1. Match all ```json_tool_call ... ``` blocks
    pattern_json_tool_call = r"```json_tool_call\s*(\{[\s\S]*?\})\s*```"
    matches = re.findall(pattern_json_tool_call, text)
    if matches:
        for m in matches:
            try:
                data = json.loads(m)
                if isinstance(data, dict) and "name" in data:
                    func_name = data["name"]
                    args = data.get("arguments", {})
                    if not isinstance(args, str):
                        args = json.dumps(args, ensure_ascii=False)
                    tool_calls.append({
                        "id": f"call_{uuid.uuid4().hex[:16]}",
                        "type": "function",
                        "function": {
                            "name": func_name,
                            "arguments": args
                        }
                    })
            except Exception as e:
                print(f"[tool_parser] JSON parse error in block: {e}")
        
        if tool_calls:
            clean_text = re.sub(pattern_json_tool_call, "", text).strip()
            return True, tool_calls, clean_text

    # 2. Match general ```json ... ``` blocks containing "name" and "arguments"
    pattern_general_json = r"```json\s*(\{[\s\S]*?\"name\"[\s\S]*?\})\s*```"
    matches_general = re.findall(pattern_general_json, text)
    if matches_general:
        for m in matches_general:
            try:
                data = json.loads(m)
                if isinstance(data, dict) and "name" in data:
                    func_name = data["name"]
                    args = data.get("arguments", {})
                    if not isinstance(args, str):
                        args = json.dumps(args, ensure_ascii=False)
                    tool_calls.append({
                        "id": f"call_{uuid.uuid4().hex[:16]}",
                        "type": "function",
                        "function": {
                            "name": func_name,
                            "arguments": args
                        }
                    })
            except Exception:
                pass
        
        if tool_calls:
            clean_text = re.sub(pattern_general_json, "", text).strip()
            return True, tool_calls, clean_text

    # 3. Fallback: Entire text is a JSON object or array of objects
    stripped = text.strip()
    if (stripped.startswith("{") or stripped.startswith("[")) and '"name"' in stripped:
        try:
            data = json.loads(stripped)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "name" in item:
                        func_name = item["name"]
                        args = item.get("arguments", {})
                        if not isinstance(args, str):
                            args = json.dumps(args, ensure_ascii=False)
                        tool_calls.append({
                            "id": f"call_{uuid.uuid4().hex[:16]}",
                            "type": "function",
                            "function": {
                                "name": func_name,
                                "arguments": args
                            }
                        })
                if tool_calls:
                    return True, tool_calls, ""
            elif isinstance(data, dict) and "name" in data:
                func_name = data["name"]
                args = data.get("arguments", {})
                if not isinstance(args, str):
                    args = json.dumps(args, ensure_ascii=False)
                tool_calls.append({
                    "id": f"call_{uuid.uuid4().hex[:16]}",
                    "type": "function",
                    "function": {
                        "name": func_name,
                        "arguments": args
                    }
                })
                return True, tool_calls, ""
        except Exception:
            pass

    return False, [], text


def build_prompt(messages: list, tools: list = None, system: str = None) -> str:
    parts = []
    
    tool_system_prompt = ""
    if tools and isinstance(tools, list):
        tool_defs = []
        for t in tools:
            if isinstance(t, dict):
                if t.get("type") == "function" and "function" in t:
                    tool_defs.append(t["function"])
                elif "input_schema" in t:
                    tool_defs.append({
                        "name": t.get("name"),
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {})
                    })
                else:
                    tool_defs.append(t)
        
        if tool_defs:
            tool_system_prompt = (
                "\n\n[AVAILABLE TOOLS]\n"
                "You have access to the following tools:\n"
                "```json\n"
                f"{json.dumps(tool_defs, indent=2, ensure_ascii=False)}\n"
                "```\n\n"
                "[TOOL CALLING INSTRUCTIONS]\n"
                "If you need to call a tool, respond ONLY with a JSON block in the exact format:\n"
                "```json_tool_call\n"
                "{\n"
                '  "name": "function_name",\n'
                '  "arguments": { "param1": "value1" }\n'
                "}\n"
                "```\n"
                "If no tool call is needed, respond normally with plain text."
            )

    has_system_msg = False
    
    if system:
        sys_text = ""
        if isinstance(system, list):
            sys_text = "\n".join(
                it.get("text", "") for it in system if isinstance(it, dict) and it.get("type") == "text"
            )
        else:
            sys_text = str(system)
        
        if sys_text.strip():
            has_system_msg = True
            combined_sys = sys_text + tool_system_prompt if tool_system_prompt else sys_text
            parts.append(f"<system>\n{combined_sys}\n</system>")

    for msg in messages:
        role = msg.get("role", "user")
        raw_content = msg.get("content", "")

        text_parts = []
        tool_calls_in_msg = []
        tool_results_in_msg = []

        if isinstance(raw_content, list):
            for item in raw_content:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict):
                    itype = item.get("type")
                    if itype == "text":
                        text_parts.append(item.get("text", ""))
                    elif itype == "tool_use":
                        tool_calls_in_msg.append({
                            "name": item.get("name"),
                            "arguments": item.get("input", {})
                        })
                    elif itype == "tool_result":
                        res_c = item.get("content", "")
                        if isinstance(res_c, list):
                            res_c = "\n".join(
                                c.get("text", "") for c in res_c if isinstance(c, dict) and "text" in c
                            )
                        tool_results_in_msg.append({
                            "id": item.get("tool_use_id", ""),
                            "content": str(res_c)
                        })
        elif isinstance(raw_content, str):
            text_parts.append(raw_content)
        elif raw_content is not None:
            text_parts.append(str(raw_content))

        content_text = "\n".join(text_parts).strip()

        if role == "system":
            has_system_msg = True
            combined_sys = content_text + tool_system_prompt if tool_system_prompt else content_text
            parts.append(f"<system>\n{combined_sys}\n</system>")
        elif role == "user":
            user_subparts = []
            if content_text:
                user_subparts.append(content_text)
            for tr in tool_results_in_msg:
                user_subparts.append(f"[Tool Result for {tr['id']}]:\n{tr['content']}")
            if user_subparts:
                parts.append(f"Human: {'\n\n'.join(user_subparts)}")
        elif role == "assistant":
            asst_subparts = []
            if content_text:
                asst_subparts.append(content_text)
            
            oa_tool_calls = msg.get("tool_calls")
            if oa_tool_calls and isinstance(oa_tool_calls, list):
                for tc in oa_tool_calls:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    fn_args = fn.get("arguments", "")
                    asst_subparts.append(f'```json_tool_call\n{{\n  "name": "{fn_name}",\n  "arguments": {fn_args}\n}}\n```')
            
            for tu in tool_calls_in_msg:
                tu_name = tu.get("name", "")
                tu_args = tu.get("arguments", {})
                if not isinstance(tu_args, str):
                    tu_args = json.dumps(tu_args, ensure_ascii=False)
                asst_subparts.append(f'```json_tool_call\n{{\n  "name": "{tu_name}",\n  "arguments": {tu_args}\n}}\n```')
            
            if asst_subparts:
                parts.append(f"Assistant: {'\n\n'.join(asst_subparts)}")
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id", "")
            parts.append(f"Human: [Tool Result for {tool_call_id}]:\n{content_text}")

    if not has_system_msg and tool_system_prompt:
        parts.insert(0, f"<system>\n{tool_system_prompt}\n</system>")

    parts.append("Assistant:")
    return "\n\n".join(parts)

def prepare_prompt_and_files(token: str, messages: list, tools: list = None, system: str = None, sess = None) -> tuple:
    """
    Chuẩn bị prompt và ref_file_ids (Hướng A giống ds2api nhưng có chốt an toàn chống ban).
    Nếu context vượt quá CONTEXT_FILE_THRESHOLD (mặc định 30,000 ký tự), đóng gói các tin nhắn cũ
    thành tài liệu txt và upload lên DeepSeek qua API /api/v0/file/upload_file.
    """
    raw_prompt = build_prompt(messages, tools=tools, system=system)

    if not ENABLE_CONTEXT_FILE or len(raw_prompt) < CONTEXT_FILE_THRESHOLD or len(messages) <= 2:
        return raw_prompt, []

    try:
        history_msgs = messages[:-1]
        latest_msg = messages[-1]

        history_doc_parts = ["[CONVERSATION HISTORY - FOR REFERENCE]"]
        for msg in history_msgs:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    it.get("text", "") for it in content if isinstance(it, dict) and it.get("type") == "text"
                )
            history_doc_parts.append(f"<{role}>\n{content}\n</{role}>")

        history_content = "\n\n".join(history_doc_parts)

        file_id = upload_context_file(token, history_content, session=sess)
        if file_id:
            print(f"[context_file] Đã upload context ({len(history_content)} chars) thành file_id={file_id}")
            
            ref_notice = (
                "Notice: The prior conversation history has been uploaded as an attached reference file. "
                "Please consult the attached document for context and answer the latest user query below."
            )
            short_messages = []
            if messages[0].get("role") == "system":
                short_messages.append(messages[0])
            short_messages.append({"role": "system", "content": ref_notice})
            short_messages.append(latest_msg)

            short_prompt = build_prompt(short_messages, tools=tools, system=system)
            return short_prompt, [file_id]
    except Exception as e:
        print(f"[context_file] Fallback về prompt thường do lỗi upload file: {e}")

    return raw_prompt, []

def resolve_model(model: str = "") -> str:
    """
    Quy đổi toàn bộ tên model về 1 model duy nhất 'deepseek-reasoner' (với Full Thinking R1 bật sẵn).
    Bất kể client truyền vào 'deepseek-chat', 'gpt-4o', 'claude-3-7-sonnet', hay bất kỳ model nào khác.
    """
    return "deepseek-reasoner"

# ============================================================
# SSE CHUNK FORMATTER
# ============================================================

def make_chunk(completion_id: str, model: str, delta: dict,
               finish_reason=None) -> str:
    obj = {
        "id":      completion_id,
        "object":  "chat.completion.chunk",
        "created": int(time.time()),
        "model":   model,
        "choices": [{
            "index":         0,
            "delta":         delta,
            "finish_reason": finish_reason,
        }],
    }
    return f"data: {json.dumps(obj)}\n\n"

# ============================================================
# STREAM GENERATOR
# ============================================================

def stream_generator(token: str, prompt: str, model: str,
                      thinking_enabled: bool, completion_id: str,
                      has_tools: bool = False,
                      search_enabled: bool = False,
                      ref_file_ids: list = None,
                      sess = None):
    """Generator yield SSE strings theo OpenAI Reasoning Format (DeepSeek Reasoner / R1)"""

    if sess is None:
        sess = make_session()
    yield make_chunk(completion_id, model, {"role": "assistant", "content": ""})

    session_id     = None
    msg_id         = 0
    last_status    = ""
    accumulated_text = ""

    try:
        session_id = create_session(token, session=sess)
        pow_resp   = get_pow(token, session=sess)

        lines = call_completion(
            token=token, session_id=session_id, prompt=prompt,
            model=model, thinking=thinking_enabled, search=search_enabled,
            ref_file_ids=ref_file_ids,
            pow_response=pow_resp, http_session=sess,
        )

        def consume(lines_gen):
            nonlocal msg_id, last_status, accumulated_text
            for chunk in parse_sse_lines(lines_gen):
                if chunk.get("response_message_id"):
                    msg_id = int(chunk["response_message_id"])

                p = chunk.get("p", "")
                v = chunk.get("v")

                if "status" in p and isinstance(v, str):
                    last_status = v
                if "auto_continue" in p and v is True:
                    last_status = "AUTO_CONTINUE"

                if isinstance(v, str) and "content" in p:
                    if "thinking" in p.lower():
                        # Chuẩn OpenAI DeepSeek Reasoner (R1): xuất trường reasoning_content
                        yield make_chunk(completion_id, model, {"reasoning_content": v})
                    else:
                        accumulated_text += v
                        if not has_tools:
                            yield make_chunk(completion_id, model, {"content": v})

        yield from consume(lines)

        # Auto-continue
        for rnd in range(8):
            if last_status.upper() not in ("INCOMPLETE", "AUTO_CONTINUE"):
                break
            if msg_id <= 0:
                break
            print(f"[auto_continue] round {rnd+1}, msg_id={msg_id}")
            pow2 = get_pow(token, session=sess)
            cont = call_continue(token, session_id, msg_id,
                                 pow_response=pow2, http_session=sess)
            last_status = ""
            yield from consume(cont)

        if has_tools:
            has_tool_call, tool_calls, clean_text = parse_tool_calls_from_text(accumulated_text)
            if has_tool_call:
                yield make_chunk(completion_id, model, {"tool_calls": tool_calls}, finish_reason="tool_calls")
            else:
                if clean_text:
                    yield make_chunk(completion_id, model, {"content": clean_text})
                yield make_chunk(completion_id, model, {}, finish_reason="stop")
        else:
            yield make_chunk(completion_id, model, {}, finish_reason="stop")

        yield "data: [DONE]\n\n"

    except Exception as e:
        invalidate_token(token, reason=str(e))
        err = {"error": {"type": "api_error", "message": str(e)}}
        yield f"data: {json.dumps(err)}\n\n"
    finally:
        if session_id or ref_file_ids:
            cleanup_session_async(token, session_id, sess, file_ids=ref_file_ids)

# ============================================================
# ROUTES
# ============================================================

@app.get("/healthz")
@app.get("/readyz")
def health():
    return jsonify({"status": "ok"})


@app.get("/v1/models")
@app.get("/models")
def list_models():
    err = require_auth()
    if err:
        return err
    data = [
        {"id": m, "object": "model", "created": 1700000000, "owned_by": "deepseek"}
        for m in AVAILABLE_MODELS
    ]
    return jsonify({"object": "list", "data": data})


@app.post("/v1/chat/completions")
@app.post("/chat/completions")
def chat_completions():
    err = require_auth()
    if err:
        return err

    body = request.get_json(force=True, silent=True) or {}
    model   = resolve_model(body.get("model", "deepseek-reasoner"))
    msgs    = body.get("messages", [])
    tools   = body.get("tools", None)
    stream  = bool(body.get("stream", False))
    thinking_flag = body.get("thinking", None)
    search_flag = body.get("search", None) or body.get("web_search", None)

    if not msgs:
        return jsonify({"error": {"message": "messages required"}}), 400

    # Mặc định bật FULL SUY NGHĨ (DeepThink)
    thinking_enabled = True if thinking_flag is None else bool(thinking_flag)
    search_enabled = bool(search_flag) if search_flag is not None else False

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

    try:
        token = get_active_token()
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": {"message": f"Auth failed: {e}"}}), 500

    sess = make_session()
    prompt, ref_file_ids = prepare_prompt_and_files(token, msgs, tools=tools, sess=sess)

    # ── STREAM MODE ──
    if stream:
        return Response(
            stream_generator(
                token, prompt, model, thinking_enabled, completion_id,
                has_tools=bool(tools), search_enabled=search_enabled,
                ref_file_ids=ref_file_ids, sess=sess
            ),
            mimetype="text/event-stream",
            headers={
                "Cache-Control":    "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # ── NON-STREAM MODE ──
    session_id = None
    try:
        session_id = create_session(token, session=sess)
        result = collect_response(
            token=token, session_id=session_id, prompt=prompt,
            model=model, thinking=thinking_enabled, search=search_enabled,
            ref_file_ids=ref_file_ids, http_session=sess,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        invalidate_token(token, reason=str(e))
        return jsonify({"error": {"message": str(e)}}), 500
    finally:
        if session_id or ref_file_ids:
            cleanup_session_async(token, session_id, sess, file_ids=ref_file_ids)


    raw_text = result.get("text", "")
    prompt_tokens     = len(prompt) // 4
    completion_tokens = len(raw_text) // 4

    has_tool_call, tool_calls, clean_text = parse_tool_calls_from_text(raw_text) if tools else (False, [], raw_text)

    if has_tool_call:
        msg_obj = {
            "role": "assistant",
            "content": clean_text if clean_text else None,
            "tool_calls": tool_calls
        }
        finish_reason = "tool_calls"
    else:
        msg_obj = {
            "role": "assistant",
            "content": raw_text
        }
        finish_reason = result.get("finish_reason", "stop")

    if result.get("thinking"):
        msg_obj["reasoning_content"] = result["thinking"]
        msg_obj["thinking"] = result["thinking"]

    resp = {
        "id":      completion_id,
        "object":  "chat.completion",
        "created": int(time.time()),
        "model":   model,
        "choices": [{
            "index":         0,
            "message":       msg_obj,
            "finish_reason": finish_reason,
        }],
        "usage": {
            "prompt_tokens":     prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens":      prompt_tokens + completion_tokens,
        },
    }
    if result.get("thinking"):
        resp["choices"][0]["message"]["thinking"] = result["thinking"]
        resp["choices"][0]["message"]["reasoning_content"] = result["thinking"]

    return jsonify(resp)


# ============================================================
# ANTHROPIC MESSAGES API (CLAUDE CODE CLI COMPATIBILITY)
# ============================================================

def anthropic_event(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

def anthropic_stream_generator(token: str, prompt: str, model: str,
                               thinking_enabled: bool, msg_id: str,
                               has_tools: bool = False,
                               ref_file_ids: list = None,
                               sess = None):
    """Generator yield SSE strings theo chuẩn Anthropic Messages API cho Claude Code"""
    if sess is None:
        sess = make_session()

    prompt_tokens = max(1, len(prompt) // 4)

    # 1. message_start
    yield anthropic_event("message_start", {
        "type": "message_start",
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": prompt_tokens,
                "output_tokens": 1
            }
        }
    })

    session_id = None
    deepseek_msg_id = 0
    last_status = ""
    accumulated_text = ""
    started_text_block = False
    started_thinking_block = False
    block_index = 0

    try:
        session_id = create_session(token, session=sess)
        pow_resp = get_pow(token, session=sess)

        lines = call_completion(
            token=token, session_id=session_id, prompt=prompt,
            model=model, thinking=thinking_enabled,
            ref_file_ids=ref_file_ids,
            pow_response=pow_resp, http_session=sess,
        )

        def consume(lines_gen):
            nonlocal deepseek_msg_id, last_status, accumulated_text, started_text_block, started_thinking_block, block_index
            for chunk in parse_sse_lines(lines_gen):
                if chunk.get("response_message_id"):
                    deepseek_msg_id = int(chunk["response_message_id"])

                p = chunk.get("p", "")
                v = chunk.get("v")

                if "status" in p and isinstance(v, str):
                    last_status = v
                if "auto_continue" in p and v is True:
                    last_status = "AUTO_CONTINUE"

                if isinstance(v, str) and "content" in p:
                    if "thinking" in p.lower():
                        if not started_thinking_block:
                            started_thinking_block = True
                            yield anthropic_event("content_block_start", {
                                "type": "content_block_start",
                                "index": block_index,
                                "content_block": {"type": "thinking", "thinking": ""}
                            })
                        yield anthropic_event("content_block_delta", {
                            "type": "content_block_delta",
                            "index": block_index,
                            "delta": {"type": "thinking_delta", "thinking": v}
                        })
                    else:
                        if started_thinking_block:
                            yield anthropic_event("content_block_stop", {
                                "type": "content_block_stop",
                                "index": block_index
                            })
                            started_thinking_block = False
                            block_index += 1

                        accumulated_text += v
                        if not has_tools:
                            if not started_text_block:
                                started_text_block = True
                                yield anthropic_event("content_block_start", {
                                    "type": "content_block_start",
                                    "index": block_index,
                                    "content_block": {"type": "text", "text": ""}
                                })
                            yield anthropic_event("content_block_delta", {
                                "type": "content_block_delta",
                                "index": block_index,
                                "delta": {"type": "text_delta", "text": v}
                            })

        yield from consume(lines)

        # Auto-continue
        for rnd in range(8):
            if last_status.upper() not in ("INCOMPLETE", "AUTO_CONTINUE"):
                break
            if deepseek_msg_id <= 0:
                break
            print(f"[anthropic_stream] auto_continue round {rnd+1}, msg_id={deepseek_msg_id}")
            pow2 = get_pow(token, session=sess)
            cont = call_continue(token, session_id, deepseek_msg_id,
                                 pow_response=pow2, http_session=sess)
            last_status = ""
            yield from consume(cont)

        # Đóng thinking block nếu còn mở
        if started_thinking_block:
            yield anthropic_event("content_block_stop", {
                "type": "content_block_stop",
                "index": block_index
            })
            started_thinking_block = False
            block_index += 1

        # Tool parsing or finalizing blocks
        has_tool_call = False
        tool_calls = []
        clean_text = accumulated_text

        if has_tools:
            has_tool_call, tool_calls, clean_text = parse_tool_calls_from_text(accumulated_text)

        if has_tools:
            if clean_text:
                yield anthropic_event("content_block_start", {
                    "type": "content_block_start",
                    "index": block_index,
                    "content_block": {"type": "text", "text": ""}
                })
                yield anthropic_event("content_block_delta", {
                    "type": "content_block_delta",
                    "index": block_index,
                    "delta": {"type": "text_delta", "text": clean_text}
                })
                yield anthropic_event("content_block_stop", {
                    "type": "content_block_stop",
                    "index": block_index
                })
                block_index += 1

            if has_tool_call:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    fn_args = fn.get("arguments", "{}")
                    tool_id = tc.get("id") or f"toolu_{uuid.uuid4().hex[:16]}"
                    if not tool_id.startswith("toolu_"):
                        tool_id = f"toolu_{tool_id.replace('call_', '')}"

                    yield anthropic_event("content_block_start", {
                        "type": "content_block_start",
                        "index": block_index,
                        "content_block": {
                            "type": "tool_use",
                            "id": tool_id,
                            "name": fn_name,
                            "input": {}
                        }
                    })
                    yield anthropic_event("content_block_delta", {
                        "type": "content_block_delta",
                        "index": block_index,
                        "delta": {
                            "type": "input_json_delta",
                            "partial_json": fn_args
                        }
                    })
                    yield anthropic_event("content_block_stop", {
                        "type": "content_block_stop",
                        "index": block_index
                    })
                    block_index += 1
        else:
            if started_text_block:
                yield anthropic_event("content_block_stop", {
                    "type": "content_block_stop",
                    "index": block_index
                })

        output_tokens = max(1, len(accumulated_text) // 4)
        stop_reason = "tool_use" if has_tool_call else "end_turn"

        yield anthropic_event("message_delta", {
            "type": "message_delta",
            "delta": {
                "stop_reason": stop_reason,
                "stop_sequence": None
            },
            "usage": {
                "output_tokens": output_tokens
            }
        })
        yield anthropic_event("message_stop", {
            "type": "message_stop"
        })

    except Exception as e:
        invalidate_token(token, reason=str(e))
        err = {"type": "error", "error": {"type": "api_error", "message": str(e)}}
        yield anthropic_event("error", err)
    finally:
        if session_id or ref_file_ids:
            cleanup_session_async(token, session_id, sess, file_ids=ref_file_ids)


@app.post("/v1/messages")
@app.post("/messages")
def anthropic_messages():
    err = require_auth(is_anthropic=True)
    if err:
        return err

    body = request.get_json(force=True, silent=True) or {}
    model = resolve_model(body.get("model", "deepseek-reasoner"))
    msgs = body.get("messages", [])
    system_param = body.get("system", None)
    tools = body.get("tools", None)
    stream = bool(body.get("stream", False))

    if not msgs:
        return jsonify({"type": "error", "error": {"type": "invalid_request_error", "message": "messages required"}}), 400

    # Luôn bật FULL suy nghĩ mặc định (Extended Thinking)
    thinking_enabled = True
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

    try:
        token = get_active_token()
    except Exception as e:
        return jsonify({"type": "error", "error": {"type": "authentication_error", "message": str(e)}}), 500

    sess = make_session()
    prompt, ref_file_ids = prepare_prompt_and_files(token, msgs, tools=tools, system=system_param, sess=sess)

    # ── STREAM MODE (Used by Claude Code CLI) ──
    if stream:
        return Response(
            anthropic_stream_generator(
                token, prompt, model, thinking_enabled, msg_id,
                has_tools=bool(tools), ref_file_ids=ref_file_ids, sess=sess
            ),
            mimetype="text/event-stream",
            headers={
                "Cache-Control":    "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # ── NON-STREAM MODE ──
    session_id = None
    try:
        session_id = create_session(token, session=sess)
        result = collect_response(
            token=token, session_id=session_id, prompt=prompt,
            model=model, thinking=thinking_enabled,
            ref_file_ids=ref_file_ids, http_session=sess,
        )
    except Exception as e:
        invalidate_token(token, reason=str(e))
        return jsonify({"type": "error", "error": {"type": "api_error", "message": str(e)}}), 500
    finally:
        if session_id or ref_file_ids:
            cleanup_session_async(token, session_id, sess, file_ids=ref_file_ids)

    raw_text = result.get("text", "")
    prompt_tokens = max(1, len(prompt) // 4)
    completion_tokens = max(1, len(raw_text) // 4)

    has_tool_call, tool_calls, clean_text = parse_tool_calls_from_text(raw_text) if tools else (False, [], raw_text)

    content_blocks = []
    if result.get("thinking"):
        content_blocks.append({"type": "thinking", "thinking": result["thinking"]})
    if clean_text:
        content_blocks.append({"type": "text", "text": clean_text})

    if has_tool_call:
        for tc in tool_calls:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except Exception:
                args = fn.get("arguments", {})
            t_id = tc.get("id") or f"toolu_{uuid.uuid4().hex[:16]}"
            if not t_id.startswith("toolu_"):
                t_id = f"toolu_{t_id.replace('call_', '')}"
            content_blocks.append({
                "type": "tool_use",
                "id": t_id,
                "name": fn.get("name"),
                "input": args
            })
        stop_reason = "tool_use"
    else:
        stop_reason = "end_turn"

    resp = {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content_blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens
        }
    }
    return jsonify(resp)


@app.post("/v1/messages/count_tokens")
@app.post("/messages/count_tokens")
def anthropic_count_tokens():
    body = request.get_json(force=True, silent=True) or {}
    msgs = body.get("messages", [])
    system_param = body.get("system", None)
    prompt = build_prompt(msgs, system=system_param)
    return jsonify({"input_tokens": max(1, len(prompt) // 4)})


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5001"))
    api_key = os.environ.get("API_KEY", "sk-my-secret-key-1")

    print("=" * 60)
    print("DeepSeek API Bridge - Dual OpenAI & Anthropic Messages Support")
    print("=" * 60)
    print(f"OpenAI Endpoint:    http://{host if host != '0.0.0.0' else 'localhost'}:{port}/v1/chat/completions")
    print(f"Anthropic Endpoint: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/v1/messages")
    print(f"Models:             http://{host if host != '0.0.0.0' else 'localhost'}:{port}/v1/models")
    print(f"API Key:            {api_key}")
    if DEFAULT_PROXY:
        print(f"Active Proxy:       {DEFAULT_PROXY} (Cloudflare WARP / Sing-Box)")
    print("=" * 60)
    print("[Claude Code CLI Integration Guide]")
    print(f'  $env:ANTHROPIC_BASE_URL = "http://127.0.0.1:{port}"')
    print(f'  $env:ANTHROPIC_API_KEY  = "{api_key}"')
    print('  claude')
    print("=" * 60)
    print("[info] Khởi động trình duyệt và kiểm tra phiên DeepSeek trong nền...")
    threading.Thread(target=get_active_token, daemon=True).start()
    print("=" * 60)

    try:
        from waitress import serve
        print(f"[server] Khởi chạy sản phẩm WSGI server (Waitress) tại http://{host if host != '0.0.0.0' else 'localhost'}:{port}...")
        serve(app, host=host, port=port, threads=16)
    except ImportError:
        print("[server] Waitress chưa cài đặt, sử dụng Flask dev server...")
        app.run(
            host=host,
            port=port,
            threaded=True,
            debug=False,
        )
    except KeyboardInterrupt:
        pass
    finally:
        cleanup_on_exit()

