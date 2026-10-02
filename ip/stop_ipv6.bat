@echo off
chcp 65001 >nul
title TẮT IPV6 (STOP)
cd /d "%~dp0"
python ipv6_tool.py stop
pause
