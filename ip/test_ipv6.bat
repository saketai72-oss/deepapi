@echo off
chcp 65001 >nul
title KIỂM TRA IPV6 (TEST)
cd /d "%~dp0"
python ipv6_tool.py test
pause
