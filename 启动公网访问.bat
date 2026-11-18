@echo off
chcp 65001 >nul
setlocal

set "ROOT=%~dp0"
set "CFG=%ROOT%deploy\cloudflared\config.yml"
set "PATH=%PATH%;C:\Program Files (x86)\cloudflared;C:\Program Files\cloudflared"

where cloudflared >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 cloudflared，请先安装：
  echo   winget install --id Cloudflare.cloudflared -e
  pause
  exit /b 1
)

curl.exe -s -m 5 -o NUL http://127.0.0.1:8000/api/v1/docs
if errorlevel 1 (
  echo [错误] 后端未运行，请先双击「启动项目.bat」或启动 uvicorn。
  pause
  exit /b 1
)

if not "%OH_TUNNEL_TOKEN%"=="" (
  echo 使用 Tunnel Token 启动...
  cloudflared tunnel run --token %OH_TUNNEL_TOKEN%
  goto :eof
)

if not exist "%CFG%" (
  echo [错误] 缺少配置文件：%CFG%
  echo 请先按文件内说明创建隧道，或设置 OH_TUNNEL_TOKEN。
  pause
  exit /b 1
)

findstr /C:"REPLACE_WITH" "%CFG%" >nul
if not errorlevel 1 (
  echo [警告] 配置文件里仍有 REPLACE_WITH 占位符，隧道可能启动失败。
  echo 请先把 tunnel ID、credentials-file 和域名换成实际值。
  echo.
)

echo 使用配置文件启动：%CFG%
echo 公网 MCP 地址：https://你的域名/mcp/
cloudflared tunnel --config "%CFG%" run

endlocal
