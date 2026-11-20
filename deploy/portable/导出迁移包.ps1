param()

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Write-Step {
    param([string]$Message)
    Write-Host "[EXPORT] $Message"
}

function Read-EnvFile {
    param([string]$Path)
    $values = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $values }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match '^\s*#') { continue }
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            $key = $matches[1]
            $value = $matches[2].Trim()
            if ($value.StartsWith('"') -and $value.EndsWith('"')) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            $values[$key] = $value
        }
    }
    return $values
}

function Resolve-EnvPath {
    param([string]$Value, [string]$BaseDir)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $null }
    if ([System.IO.Path]::IsPathRooted($Value)) { return [System.IO.Path]::GetFullPath($Value) }
    return [System.IO.Path]::GetFullPath((Join-Path $BaseDir $Value))
}

function Copy-Tree {
    param([string]$From, [string]$To, [string[]]$ExcludeDirs = @(), [string[]]$ExcludeFiles = @())
    if (-not (Test-Path -LiteralPath $From)) { throw "Missing source: $From" }
    if (-not (Test-Path -LiteralPath $To)) { New-Item -ItemType Directory -Force -Path $To | Out-Null }
    $args = @($From, $To, '/E', '/COPY:DAT', '/DCOPY:DAT', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP')
    foreach ($d in $ExcludeDirs) { $args += @('/XD', $d) }
    foreach ($f in $ExcludeFiles) { $args += @('/XF', $f) }
    & robocopy @args | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed for $From (exit $LASTEXITCODE)" }
}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$backendDir = Join-Path $root 'backend'
$deployDir = Join-Path $root 'deploy'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outRoot = Join-Path $root 'var\portable'
$packageName = "oh-kb-migration-$stamp"
$packageRoot = Join-Path $outRoot $packageName
$sourceDir = Join-Path $packageRoot 'source'
$privateDir = Join-Path $packageRoot 'private'
$dataDir = Join-Path $packageRoot 'data'
$tunnelDir = Join-Path $privateDir 'tunnel'

Write-Step "Root: $root"
Write-Step "Package: $packageRoot"

foreach ($dir in @($outRoot, $packageRoot, $sourceDir, $privateDir, $dataDir, $tunnelDir)) {
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
}

Write-Step 'Copying source tree'
Copy-Tree -From $root -To $sourceDir -ExcludeDirs @(
    '.git',
    'node_modules',
    '.venv',
    '__pycache__',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
    'var'
) -ExcludeFiles @(
    '.env',
    'cookies.txt',
    '*.pyc',
    '*.pyo',
    '*.log',
    '*.tmp'
)

Write-Step 'Copying private env files'
$backendEnvPath = Join-Path $backendDir '.env'
$deployEnvPath = Join-Path $deployDir '.env'
if (-not (Test-Path -LiteralPath $backendEnvPath)) { throw "Missing backend .env: $backendEnvPath" }
if (-not (Test-Path -LiteralPath $deployEnvPath)) { throw "Missing deploy .env: $deployEnvPath" }
Copy-Item -LiteralPath $backendEnvPath -Destination (Join-Path $privateDir 'backend.env') -Force
Copy-Item -LiteralPath $deployEnvPath -Destination (Join-Path $privateDir 'deploy.env') -Force

$backendEnv = Read-EnvFile -Path $backendEnvPath
$deployEnv = Read-EnvFile -Path $deployEnvPath

Write-Step 'Exporting Python dependency lock'
$python = Join-Path $backendDir '.venv\Scripts\python.exe'
$lockPath = Join-Path $privateDir 'requirements.lock.txt'
if (Test-Path -LiteralPath $python) {
    $code = "import importlib.metadata as md; rows=sorted((d.metadata['Name'],d.version) for d in md.distributions() if d.metadata['Name'] and d.metadata['Name'] != 'occupational-health'); open(r'$lockPath','w',encoding='utf-8').write('\n'.join(f'{n}=={v}' for n,v in rows))"
    & $python -c $code
} else {
    Write-Warning 'Current venv python not found; uv.lock is still included.'
}

Write-Step 'Copying stored files and model weights'
$storageRoot = Resolve-EnvPath -Value $backendEnv['OH_STORAGE_ROOT'] -BaseDir $backendDir
$modelRoot = Resolve-EnvPath -Value $backendEnv['OH_MODEL_ROOT'] -BaseDir $backendDir
if ($storageRoot -and (Test-Path -LiteralPath $storageRoot)) {
    Copy-Tree -From $storageRoot -To (Join-Path $dataDir 'storage')
} else {
    Write-Warning "Storage root not copied: $storageRoot"
}
if ($modelRoot -and (Test-Path -LiteralPath $modelRoot)) {
    Copy-Tree -From $modelRoot -To (Join-Path $dataDir 'models')
} else {
    Write-Warning "Model root not copied: $modelRoot"
}

Write-Step 'Dumping PostgreSQL database'
$composePath = Join-Path $deployDir 'compose.yaml'
if (-not (Test-Path -LiteralPath $composePath)) { throw "Missing compose file: $composePath" }
$pgUser = if ($deployEnv.ContainsKey('POSTGRES_USER')) { $deployEnv['POSTGRES_USER'] } else { 'oh_app' }
$pgDb = if ($deployEnv.ContainsKey('POSTGRES_DB')) { $deployEnv['POSTGRES_DB'] } else { 'occupational_health' }
$dumpPath = Join-Path $privateDir 'postgres.sql'
& docker compose -f $composePath exec -T postgres pg_dump -U $pgUser -d $pgDb --no-owner --no-privileges | Set-Content -LiteralPath $dumpPath -Encoding UTF8
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed" }

Write-Step 'Creating Qdrant snapshot'
$qdrantUrl = if ($backendEnv.ContainsKey('OH_QDRANT_URL')) { $backendEnv['OH_QDRANT_URL'] } else { 'http://127.0.0.1:6333' }
$qdrantKey = if ($backendEnv.ContainsKey('OH_QDRANT_API_KEY')) { $backendEnv['OH_QDRANT_API_KEY'] } else { '' }
$collection = 'oh_chunks_v1'
$headers = @{}
if ($qdrantKey -and $qdrantKey -ne 'replace-me') { $headers['api-key'] = $qdrantKey }
$snapshotUri = "$qdrantUrl/collections/$collection/snapshots?wait=true"
$snapshotResponse = Invoke-RestMethod -Method Post -Uri $snapshotUri -Headers $headers -TimeoutSec 180
$snapshotName = $snapshotResponse.result.name
if (-not $snapshotName) {
    $snapshotList = Invoke-RestMethod -Method Get -Uri "$qdrantUrl/collections/$collection/snapshots" -Headers $headers -TimeoutSec 60
    $last = @($snapshotList.result)[-1]
    if ($last) { $snapshotName = $last.name }
}
if (-not $snapshotName) { throw 'Unable to resolve Qdrant snapshot name' }
$snapshotFile = Join-Path $dataDir 'oh_chunks_v1.snapshot'
Invoke-WebRequest -Method Get -Uri "$qdrantUrl/collections/$collection/snapshots/$([uri]::EscapeDataString($snapshotName))" -Headers $headers -OutFile $snapshotFile -TimeoutSec 300

Write-Step 'Copying Cloudflare Tunnel config and credential'
$tunnelCandidates = @(
    (Join-Path $root 'var\cloudflared\config.yml'),
    (Join-Path $deployDir 'cloudflared\config.yml')
)
$tunnelConfig = $tunnelCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $tunnelConfig) {
    Write-Warning 'No real tunnel config found; public MCP will need setup on target.'
} else {
    Copy-Item -LiteralPath $tunnelConfig -Destination (Join-Path $tunnelDir 'config.yml') -Force
    $credPath = $null
    foreach ($line in Get-Content -LiteralPath $tunnelConfig -Encoding UTF8) {
        if ($line -match '^\s*credentials-file:\s*(.+?)\s*$') { $credPath = $matches[1].Trim() }
    }
    if ($credPath -and $credPath.StartsWith('~/')) {
        $credPath = Join-Path $env:USERPROFILE $credPath.Substring(2)
    }
    if ($credPath -and (Test-Path -LiteralPath $credPath)) {
        Copy-Item -LiteralPath $credPath -Destination (Join-Path $tunnelDir 'credentials.json') -Force
    } else {
        Write-Warning "Tunnel credential not copied: $credPath"
    }
}

Write-Step 'Copying portable helpers to package root'
foreach ($name in @('INSTALL.bat','VERIFY.bat','MIGRATION.md','install-portable.ps1','verify-portable.ps1')) {
    $from = Join-Path $PSScriptRoot $name
    if (Test-Path -LiteralPath $from) {
        Copy-Item -LiteralPath $from -Destination (Join-Path $packageRoot $name) -Force
    }
}

$manifest = [ordered]@{
    schema = 'oh-kb-portable-v1'
    generated_at = (Get-Date).ToString('o')
    source_root = $root
    postgres_user = $pgUser
    postgres_database = $pgDb
    qdrant_url = $qdrantUrl
    qdrant_collection = $collection
    qdrant_snapshot = 'data/oh_chunks_v1.snapshot'
    model_root_source = $modelRoot
    storage_root_source = $storageRoot
    tunnel_config_included = [bool]$tunnelConfig
    python_lock = 'private/requirements.lock.txt'
}
Write-Utf8NoBom -Path (Join-Path $packageRoot 'manifest.json') -Content ($manifest | ConvertTo-Json -Depth 6)

Write-Step 'Compressing package'
$zipPath = Join-Path $outRoot "$packageName.zip"
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
$7zCandidates = @(
    (Join-Path $env:ProgramFiles '7-Zip\7z.exe'),
    (Join-Path ${env:ProgramFiles(x86)} '7-Zip\7z.exe')
)
$7z = $7zCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($7z) {
    & $7z a -tzip -mx=3 $zipPath (Join-Path $packageRoot '*') | Out-Null
} else {
    Compress-Archive -Path (Join-Path $packageRoot '*') -DestinationPath $zipPath -CompressionLevel Optimal -Force
}

$zipSize = [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 1)
Write-Host "EXPORT OK: $zipPath ($zipSize MB)"
