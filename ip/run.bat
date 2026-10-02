@echo off
chcp 65001 >nul
title BỘ CÔNG CỤ TẠO & SỬ DỤNG IPV6
cd /d "%~dp0"
python ipv6_tool.py
pause
