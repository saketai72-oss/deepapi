@echo off
chcp 65001 >nul
title DeepSeek API Bridge - Dual OpenAI ^& Claude Code
echo ============================================================
echo   KHỞI ĐỘNG HỆ THỐNG DEEPSEEK API BRIDGE (WAITRESS WSGI)
echo ============================================================
echo.

:: 1. Kiểm tra proxy WARP sing-box (127.0.0.1:2080)
netstat -ano | findstr 127.0.0.1:2080 >nul
if %errorlevel% neq 0 (
    echo [*] Đang khởi chạy Cloudflare WARP Proxy tại 127.0.0.1:2080...
    if exist "%~dp0ip\bin\sing-box.exe" (
        start /b "WARP-SingBox" "%~dp0ip\bin\sing-box.exe" run -c "%~dp0ip\singbox_config.json" >nul 2>&1
        timeout /t 2 >nul
    ) else if exist "%~dp0ip\ipv6_tool.py" (
        echo [*] Tự động thiết lập engine WARP và cấu hình...
        start /b "WARP-SingBox" python "%~dp0ip\ipv6_tool.py" start
        timeout /t 4 >nul
    ) else if exist "C:\code\python\ip\bin\sing-box.exe" (
        start /b "WARP-SingBox" "C:\code\python\ip\bin\sing-box.exe" run -c "C:\code\python\ip\singbox_config.json" >nul 2>&1
        timeout /t 2 >nul
    ) else (
        echo [!] Chưa tìm thấy engine proxy trong thư mục .\ip. Bạn có thể mở .\ip\run.bat để khởi tạo thủ công.
    )
) else (
    echo [+] Cloudflare WARP Proxy đã sẵn sàng trên 127.0.0.1:2080
)

:: 2. Khởi chạy DeepSeek Bridge Server
echo.
echo [*] Khởi chạy DeepSeek Bridge Server tại http://127.0.0.1:5001...
python server.py
pause
