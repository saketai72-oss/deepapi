@echo off
chcp 65001 >nul
title BẬT IPV6 (START)
cd /d "%~dp0"
python ipv6_tool.py start
pause
