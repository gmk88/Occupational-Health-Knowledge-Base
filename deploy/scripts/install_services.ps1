# 安装开机自启计划任务：API / 向量服务 / 解析 worker / 向量化 worker / Cloudflare Tunnel。
# 需要以管理员身份运行。
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Supervise = Join-Path $Root 'deploy\scripts\supervise.ps1'
$TaskPrefix = 'OH-KB'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '请以管理员身份运行本脚本。'
}

$services = @(
    @{ Name = 'API'; Service = 'api' },
    @{ Name = 'Embedding'; Service = 'embedding' },
    @{ Name = 'Parser'; Service = 'worker' },
    @{ Name = 'EmbeddingWorker'; Service = 'worker-embedding' },
    @{ Name = 'Tunnel'; Service = 'tunnel' }
)

foreach ($item in $services) {
    $taskName = "$TaskPrefix-$($item.Name)"
    $action = New-ScheduledTaskAction `
        -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Supervise`" -Service $($item.Service)" `
        -WorkingDirectory $Root
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $trigger.Delay = 'PT30S'
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $taskPrincipal -Settings $settings -Force | Out-Null
    Write-Host "installed $taskName"
}

Write-Host 'All OH-KB startup tasks installed.'
