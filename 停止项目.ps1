$ErrorActionPreference = 'SilentlyContinue'

Write-Host "正在停止服务..."

# 先停止看门狗，否则子进程退出后会被它重新拉起。
Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -in @('powershell.exe', 'pwsh.exe') -and
        $_.CommandLine -match 'supervise\.ps1'
    } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Milliseconds 500

# 按端口停止后端(8000)/向量化(8001)/旧版前端(5173)
$pids = Get-NetTCPConnection -LocalPort 8000, 8001, 5173 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $pids) {
    Stop-Process -Id $procId -Force
}

# 停止 celery 文档处理 worker（无固定端口，按命令行匹配）
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'celery' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host "服务已停止。"
Write-Host "基础设施 (PostgreSQL/Redis/Qdrant) 仍在运行。"
Write-Host "如需一并停止，请运行: docker compose -f deploy\compose.yaml down"
