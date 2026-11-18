# 健康检查：本地 API / 向量服务 / 前端 + 公网 MCP。
# 可设置 OH_KB_ALERT_WEBHOOK，将异常推送到企业微信/钉钉机器人。
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Log = Join-Path $Root 'var\log\health-check.log'
$Webhook = $env:OH_KB_ALERT_WEBHOOK

function Test-Status {
    param([string]$Url, [int]$Expected, [string]$Method = 'GET')
    try {
        $response = Invoke-WebRequest -Uri $Url -Method $Method -UseBasicParsing -TimeoutSec 10
        return ($response.StatusCode -eq $Expected)
    } catch {
        $status = $null
        if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
        return ($status -eq $Expected)
    }
}

$checks = @(
    @{ Name = 'backend'; Url = 'http://127.0.0.1:8000/api/v1/docs'; Expected = 200; Method = 'GET' },
    @{ Name = 'embedding'; Url = 'http://127.0.0.1:8001/health'; Expected = 200; Method = 'GET' },
    @{ Name = 'frontend'; Url = 'http://127.0.0.1:5173'; Expected = 200; Method = 'GET' },
    @{ Name = 'public-mcp-anon'; Url = 'https://kb.guanmingkun.ltd/mcp/'; Expected = 401; Method = 'POST' }
)

$failures = @()
foreach ($check in $checks) {
    $ok = Test-Status -Url $check.Url -Expected $check.Expected -Method $check.Method
    $line = '{0} {1} expected={2} ok={3}' -f (Get-Date -Format o), $check.Name, $check.Expected, $ok
    Add-Content -LiteralPath $Log -Value $line -Encoding utf8
    if (-not $ok) { $failures += $check.Name }
}

if ($failures.Count -gt 0 -and $Webhook) {
    $body = @{ msgtype = 'text'; text = @{ content = "职业健康知识库健康检查失败：$($failures -join ', ')" } } | ConvertTo-Json -Depth 3
    try {
        Invoke-RestMethod -Uri $Webhook -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 10 | Out-Null
    } catch {
        Add-Content -LiteralPath $Log -Value "$((Get-Date -Format o)) webhook failed: $($_.Exception.Message)" -Encoding utf8
    }
}

if ($failures.Count -gt 0) { exit 1 }
exit 0
