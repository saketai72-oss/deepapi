@echo off
rem -------------------------------------------------
rem Auto‑run DeepAPI: start Sing‑Box proxy + Python server
rem -------------------------------------------------

set "SCRIPT_DIR=%~dp0"

rem Start sing‑box (port 2083)
start "sing-box" "%SCRIPT_DIR%ip\bin\sing-box.exe" run -c "%SCRIPT_DIR%ip\singbox_config.json"
timeout /t 2 /nobreak >nul

rem Launch DeepAPI server
pushd "%SCRIPT_DIR%"
python server.py
popd
