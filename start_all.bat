@echo off
cd /d "%~dp0"
title TilinX - Proxy + Web Dashboard

start "TilinX Proxy" "C:\Users\Chichi\AppData\Local\Programs\Python\Python311\Scripts\mitmweb.exe" --listen-port 9999 -s "C:\Users\Chichi\Downloads\TilinX_Proxy_Windows\hunter_proxy.py" --set block_global=false
start "TilinX Web" "C:\Users\Chichi\AppData\Local\Programs\Python\Python311\python.exe" "%~dp0website\app.py"

echo ========================================
echo   TilinX Running
echo ========================================
echo   Proxy  : http://localhost:9999
echo   Web    : http://localhost:8080
echo.
echo   Press any key to stop...
pause >nul

taskkill /f /fi "WINDOWTITLE eq TilinX*" >nul 2>&1
echo Stopped.
