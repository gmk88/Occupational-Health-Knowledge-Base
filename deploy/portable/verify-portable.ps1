param(
    [string]$InstallRoot = ''
)

$ErrorActionPreference = 'Stop'

function Write-Check {
    param([string]$Name, [bool]$Ok, [string]$Detail = '')
    $mark = if ($Ok) { 'OK  ' } else { 'FAIL' }
    Write-Host "[$mark] $Name $Detail"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Test-Path -LiteralPath (Join-Path $scriptDir 'source')) {
    $packageRoot = $scriptDir
} elseif (Test-Path -LiteralPath (Join-Path $scriptDir '..\..')) {
    $packageRoot = (Resolve-Path (Join-Path $scriptDir '..\..')).Path
} else {
    $packageRoot = $scriptDir
}
if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    $InstallRoot = Join-Path $packageRoot 'installed'
}
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)

Write-Host "VERIFY ROOT: $InstallRoot"

$checks = @(
    @{ Name = 'backend docs'; Url = 'http://127.0.0.1:8000/api/v1/docs'; Expected = 200 },
    @{ Name = 'backend health'; Url = 'http://127.0.0.1:8000/health/live'; Expected = 200 },
    @{ Name = 'frontend root'; Url = 'http://127.0.0.1:8000/'; Expected = 200 },
    @{ Name = 'embedding health'; Url = 'http://127.0.0.1:8001/health'; Expected = 200 },
    @{ Name = 'qdrant root'; Url = 'http://127.0.0.1:6333/'; Expected = 200 }
)
foreach ($check in $checks) {
    $code = $null
    try {
        $code = [int](curl.exe -s -m 10 -o NUL -w '%{http_code}' $check.Url)
    } catch {
        $code = 0
    }
    Write-Check -Name $check.Name -Ok ($code -eq $check.Expected) -Detail "HTTP $code"
}

$backendDir = Join-Path $InstallRoot 'backend'
$pythonExe = Join-Path $backendDir '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $pythonExe) {
    $code = @'
import httpx, json
base = "http://127.0.0.1:8000/api/v1"
c = httpx.Client(base_url=base, timeout=60)
r = c.post("/auth/login", json={"login_name":"admin","password":"admin123"})
if r.status_code != 200:
    print(json.dumps({"login":False,"documents":0,"search":0}))
else:
    d = c.get("/documents?page=1&page_size=1")
    docs = d.json()["data"]["meta"]["total"] if d.status_code == 200 else -1
    s = c.post("/search", json={"query":"苯 PC-TWA","mode":"hybrid","top_k":3,"filters":{}})
    items = len(s.json()["data"]["items"]) if s.status_code == 200 else -1
    print(json.dumps({"login":True,"documents":docs,"search":items}))
'@
    $raw = $code | & $pythonExe -
    try {
        $result = $raw | ConvertFrom-Json
        Write-Check -Name 'login' -Ok ([bool]$result.login)
        Write-Check -Name 'documents=60' -Ok ($result.documents -eq 60) -Detail "count=$($result.documents)"
        Write-Check -Name 'search smoke' -Ok ($result.search -gt 0) -Detail "items=$($result.search)"
    } catch {
        Write-Check -Name 'api smoke' -Ok $false -Detail ([string]$raw)
    }
} else {
    Write-Check -Name 'python venv' -Ok $false -Detail $pythonExe
}

$publicCode = 0
try {
    $publicCode = [int](curl.exe -s -m 20 -o NUL -w '%{http_code}' -X POST https://kb.guanmingkun.ltd/mcp/ -H 'Content-Type: application/json' -d '{}')
} catch {
    $publicCode = 0
}
Write-Check -Name 'public MCP anonymous' -Ok ($publicCode -eq 401) -Detail "HTTP $publicCode"

$watchdogNames = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*supervise.ps1*' } | ForEach-Object { (($_.CommandLine -split ' -Service ')[-1]).Trim() })
foreach ($service in @('api','embedding','worker','worker-embedding','tunnel')) {
    Write-Check -Name "watchdog $service" -Ok ($watchdogNames -contains $service)
}
