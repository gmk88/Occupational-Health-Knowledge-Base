# 单服务看门狗：子进程退出按 5/15/30/60 秒退避重启；
# 5 分钟内快速失败超过 10 次则暂停 5 分钟；探活连续失败 3 次强制重启。
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('api', 'embedding', 'worker', 'worker-embedding', 'tunnel')]
    [string]$Service
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Backend = Join-Path $Root 'backend'
$Python = Join-Path $Backend '.venv\Scripts\python.exe'
$LogDir = Join-Path $Root 'var\log'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Executable = $Python
$WorkingDirectory = $Backend

switch ($Service) {
    'api' {
        $display = '后端 API'
        $serviceArgs = @(
            '-m', 'uvicorn', 'occupational_health.api.main:app',
            '--host', '127.0.0.1', '--port', '8000',
            '--proxy-headers', '--forwarded-allow-ips=127.0.0.1,::1'
        )
        $probeUrl = 'http://127.0.0.1:8000/health/live'
        $startupGrace = 60
        $logName = 'backend.log'
    }
    'embedding' {
        $display = '向量化服务'
        $serviceArgs = @(
            '-m', 'uvicorn', 'occupational_health.services.embedding.server:app',
            '--host', '127.0.0.1', '--port', '8001'
        )
        $probeUrl = 'http://127.0.0.1:8001/health'
        $startupGrace = 300
        $logName = 'embedding.log'
    }
    'worker' {
        $display = '文档处理 worker'
        $serviceArgs = @(
            '-m', 'celery', '-A', 'occupational_health.workers.celery_app',
            'worker', '--pool=solo', '--loglevel=info', '--concurrency=1',
            '--hostname=oh-parser@%h'
        )
        $probeUrl = $null
        $startupGrace = 0
        $logName = 'celery.log'
    }
    'worker-embedding' {
        $display = '向量化 worker'
        $serviceArgs = @(
            '-m', 'celery', '-A', 'occupational_health.workers.celery_app',
            'worker', '--pool=solo', '--loglevel=info', '--concurrency=1',
            '-Q', 'embedding', '--hostname=oh-embedding@%h'
        )
        $probeUrl = $null
        $startupGrace = 0
        $logName = 'celery-embedding.log'
    }
    'tunnel' {
        $display = 'Cloudflare Tunnel'
        $found = Get-Command cloudflared -ErrorAction SilentlyContinue
        if ($found) { $Executable = $found.Source } else {
            $candidates = @(
                "$env:ProgramFiles\cloudflared\cloudflared.exe",
                "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe"
            )
            $Executable = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
        }
        if (-not $Executable) { throw '未找到 cloudflared，请先安装或加入 PATH' }
        $config = Join-Path $Root 'var\cloudflared\config.yml'
        if (-not (Test-Path $config)) {
            $config = Join-Path $Root 'deploy\cloudflared\config.yml'
        }
        if (-not (Test-Path $config)) { throw "缺少隧道配置：$config" }
        $serviceArgs = @('tunnel', '--config', $config, 'run')
        $WorkingDirectory = $Root
        $probeUrl = $null
        $startupGrace = 0
        $logName = 'cloudflared.log'
    }
}

$outLog = Join-Path $LogDir $logName
$errLog = Join-Path $LogDir ([IO.Path]::GetFileNameWithoutExtension($logName) + '.err.log')
$Host.UI.RawUI.WindowTitle = "OH-$Service-watchdog"

function Test-Probe {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300)
    } catch {
        return $false
    }
}

$fastFailures = 0
$windowStart = Get-Date

while ($true) {
    # 保留上一次运行的日志，方便定位崩溃原因。
    if (Test-Path $outLog) { Move-Item -Force $outLog "$outLog.prev" }
    if (Test-Path $errLog) { Move-Item -Force $errLog "$errLog.prev" }

    $started = Get-Date
    Write-Host ("[{0}] 启动 {1}" -f $started.ToString('HH:mm:ss'), $display)
    $proc = Start-Process -FilePath $Executable -ArgumentList $serviceArgs `
        -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog

    $probeFailures = 0
    while (-not $proc.HasExited) {
        Start-Sleep -Seconds 5
        $proc.Refresh()
        if ($proc.HasExited -or -not $probeUrl) { continue }
        if (Test-Probe $probeUrl) {
            $probeFailures = 0
        } elseif (((Get-Date) - $started).TotalSeconds -ge $startupGrace) {
            $probeFailures++
            Write-Host ("[{0}] {1} 探活失败 {2}/3" -f (Get-Date).ToString('HH:mm:ss'), $display, $probeFailures)
            if ($probeFailures -ge 3) {
                Write-Host "[$Service] 连续探活失败，强制重启"
                Stop-Process -Id $proc.Id -Force
            }
        }
    }

    $runtime = ((Get-Date) - $started).TotalSeconds
    Write-Host ("[{0}] {1} 已退出（运行 {2:N0} 秒）" -f (Get-Date).ToString('HH:mm:ss'), $display, $runtime)

    if ($runtime -lt 60) {
        if (((Get-Date) - $windowStart).TotalMinutes -ge 5) {
            $fastFailures = 0
            $windowStart = Get-Date
        }
        $fastFailures++
        if ($fastFailures -gt 10) {
            Write-Host "[$Service] 5 分钟内快速失败超过 10 次，暂停 5 分钟后再试"
            Start-Sleep -Seconds 300
            $fastFailures = 0
            $windowStart = Get-Date
            continue
        }
        $delay = @(5, 15, 30, 60)[[Math]::Min($fastFailures - 1, 3)]
    } else {
        $fastFailures = 0
        $windowStart = Get-Date
        $delay = 5
    }

    Write-Host "[$Service] $delay 秒后重启"
    Start-Sleep -Seconds $delay
}
