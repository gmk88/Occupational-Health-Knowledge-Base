@echo off
chcp 65001 >nul
title 停止职业健康知识库
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0停止项目.ps1"
echo.
pause
