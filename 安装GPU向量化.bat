@echo off
chcp 65001 >nul
title 安装 GPU 向量化依赖
cd /d "%~dp0backend"

rem 国内镜像：PyPI 用清华，PyTorch CUDA wheel 用阿里云直链
rem 注意：以后执行 uv sync 会按 uv.lock 还原成 CPU 版 torch，需重新运行本脚本
set "PYTHONPATH="
set "UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
set "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"

echo ============================================
echo   安装 CUDA 版 torch - cu126 / RTX 3060
echo ============================================
echo.
echo [1/3] 停止正在运行的向量化服务 (端口 8001)...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

echo [2/3] 从阿里云镜像安装（约 2.4 GiB，支持断点续传）...
uv pip install --python .venv\Scripts\python.exe --reinstall-package torch --index-url https://pypi.tuna.tsinghua.edu.cn/simple "https://mirrors.aliyun.com/pytorch-wheels/cu126/torch-2.14.1+cu126-cp312-cp312-win_amd64.whl"
if errorlevel 1 (
  echo 安装失败，请检查网络或磁盘空间。
  pause
  exit /b 1
)

echo [3/3] 验证 CUDA...
.venv\Scripts\python.exe -c "import torch; print('torch:', torch.__version__); print('CUDA:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
echo.
echo 完成。重新运行 启动项目.bat 后向量化会自动使用显卡。
echo 如需强制用 CPU，把 backend\.env 里 OH_EMBEDDING_DEVICE 改成 cpu。
pause
