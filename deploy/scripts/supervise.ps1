# Single-service watchdog with restart backoff and optional HTTP probe.
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
        $display = 'Backend API'
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
        $display = 'Embedding Service'
        $serviceArgs = @(
            '-m', 'uvicorn', 'occupational_health.services.embedding.server:app',
            '--host', '127.0.0.1', '--port', '8001'
        )
        $probeUrl = 'http://127.0.0.1:8001/health'
        $startupGrace = 300
        $logName = 'embedding.log'
    }
    'worker' {
        $display = 'Document Worker'
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
        $display = 'Embedding Worker'
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
        if (-not $Executable) { throw 'cloudflared not found' }
        $config = Join-Path $Root 'var\cloudflared\config.yml'
        if (-not (Test-Path $config)) {
            $config = Join-Path $Root 'deploy\cloudflared\config.yml'
        }
        if (-not (Test-Path $config)) { throw "Tunnel config not found: $config" }
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
    try {
        if (Test-Path $outLog) { Move-Item -Force $outLog "$outLog.prev" -ErrorAction Stop }
    } catch { }
    try {
        if (Test-Path $errLog) { Move-Item -Force $errLog "$errLog.prev" -ErrorAction Stop }
    } catch { }

    $started = Get-Date
    Write-Host ("[{0}] START {1}" -f $started.ToString('HH:mm:ss'), $display)
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
            Write-Host ("[{0}] PROBE FAIL {1} {2}/3" -f (Get-Date).ToString('HH:mm:ss'), $display, $probeFailures)
            if ($probeFailures -ge 3) {
                Write-Host "[$Service] restart after probe failures"
                Stop-Process -Id $proc.Id -Force
            }
        }
    }

    $runtime = ((Get-Date) - $started).TotalSeconds
    Write-Host ("[{0}] EXIT {1} ({2:N0}s)" -f (Get-Date).ToString('HH:mm:ss'), $display, $runtime)

    if ($runtime -lt 60) {
        if (((Get-Date) - $windowStart).TotalMinutes -ge 5) {
            $fastFailures = 0
            $windowStart = Get-Date
        }
        $fastFailures++
        if ($fastFailures -gt 10) {
            Write-Host "[$Service] pause 5 minutes after repeated fast failures"
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

    Write-Host "[$Service] restart in $delay seconds"
    Start-Sleep -Seconds $delay
}
