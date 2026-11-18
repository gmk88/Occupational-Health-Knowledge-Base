@echo off
chcp 65001 >nul
title 职业健康知识库 - 启动器
cd /d "%~dp0"

rem 依赖下载统一走国内镜像（慢速官方源的替代）
set "UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
set "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"
set "NPM_CONFIG_REGISTRY=https://registry.npmmirror.com"
set "PYTHONPATH="
rem 6GB 显存机器：减小向量化批次并缓解显存碎片，避免与 MinerU 争抢时 OOM
set "PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True"
set "OH_EMBEDDING_BATCH_SIZE=8"

if not exist "var\log" mkdir "var\log"

echo ============================================
echo   职业健康知识库 - 一键启动
echo ============================================
echo.

echo [0/7] 清理上次残留的 API / 向量化 / worker 进程...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0停止项目.ps1" >nul 2>&1
ping -n 3 127.0.0.1 >nul

echo [1/7] 启动基础设施 (PostgreSQL / Redis / Qdrant)...
docker compose -f deploy\compose.yaml up -d --wait --wait-timeout 120
if errorlevel 1 (
  echo     [错误] 基础设施启动失败，请确认 Docker Desktop 已运行且 deploy\.env 已填写。
  pause
  exit /b 1
)

echo [2/7] 等待 PostgreSQL 就绪（最多 60 秒）...
call :wait_postgres 60
if errorlevel 1 (
  echo     [错误] PostgreSQL 未在 60 秒内就绪。
  pause
  exit /b 1
)

echo [3/7] 应用数据库迁移...
pushd backend
.venv\Scripts\python.exe -m alembic upgrade head
if errorlevel 1 (
  popd
  echo     [错误] 数据库迁移失败，已中止启动。请查看上方错误信息。
  pause
  exit /b 1
)
popd

echo [4/7] 构建前端生产版本...
pushd frontend
if not exist node_modules (
  echo     首次构建，安装前端依赖...
  call npm install
  if errorlevel 1 (
    popd
    echo     [错误] 前端依赖安装失败，已中止启动。
    pause
    exit /b 1
  )
)
call npm run build
if errorlevel 1 (
  popd
  echo     [错误] 前端构建失败，已中止启动。
  pause
  exit /b 1
)
popd

echo [5/7] 启动向量化服务（端口 8001，模型加载可能需要数分钟）...
start "oh-embedding-watchdog" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\scripts\supervise.ps1" -Service embedding
echo     等待向量化服务就绪（最多 300 秒）...
call :wait_http "http://127.0.0.1:8001/health" 300
if errorlevel 1 (
  echo     [警告] 向量化服务未在 300 秒内就绪，稍后看门狗会继续尝试；检索暂不可用。
) else (
  echo     向量化服务已就绪。
)

echo [6/7] 启动后端 API（端口 8000）...
start "oh-api-watchdog" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\scripts\supervise.ps1" -Service api
echo     等待后端就绪（最多 120 秒）...
call :wait_http "http://127.0.0.1:8000/api/v1/docs" 120
if errorlevel 1 (
  echo     [错误] 后端未在 120 秒内就绪，请查看 var\log\backend.log 与 backend.err.log。
  echo     看门狗仍在后台重试，修复问题后无需重新运行本脚本。
  pause
  exit /b 1
)

echo [7/7] 启动文档处理 / 向量化 worker...
start "oh-worker-watchdog" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\scripts\supervise.ps1" -Service worker
start "oh-embedding-watchdog" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\scripts\supervise.ps1" -Service worker-embedding

echo.
echo 打开浏览器...
start "" "http://127.0.0.1:8000"

echo.
echo ============================================
echo  启动完成！
echo  访问地址 : http://127.0.0.1:8000
echo  默认账号 : admin
echo  默认密码 : admin123
echo  日志目录 : var\log
echo  运行状态 : API / 向量化 / worker 均由看门狗自动重启
echo  停止方式 : 运行 停止项目.bat
echo ============================================
echo.
echo 基础设施检查：
curl -s http://127.0.0.1:8000/api/v1/docs -o nul -w "API HTTP %%{http_code}"
echo.
pause
exit /b 0

:wait_postgres
set /a WAITED=0
:wait_postgres_loop
docker compose -f deploy\compose.yaml exec -T postgres pg_isready -q >nul 2>&1
if not errorlevel 1 exit /b 0
set /a WAITED+=2
if %WAITED% geq %~1 exit /b 1
ping -n 3 127.0.0.1 >nul
goto :wait_postgres_loop

:wait_http
set /a WAITED=0
:wait_http_loop
curl -sf -o nul --max-time 2 %~1 >nul 2>&1
if not errorlevel 1 exit /b 0
set /a WAITED+=2
if %WAITED% geq %~2 exit /b 1
ping -n 3 127.0.0.1 >nul
goto :wait_http_loop
