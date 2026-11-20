param(
    [string]$InstallRoot = '',
    [switch]$SkipPrereqInstall
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Write-Step {
    param([string]$Message)
    Write-Host "[INSTALL] $Message"
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

function Set-EnvValue {
    param([string]$Path, [string]$Key, [string]$Value)
    $lines = @()
    $found = $false
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match "^\s*$([regex]::Escape($Key))\s*=") {
            $lines += "$Key=$Value"
            $found = $true
        } else {
            $lines += $line
        }
    }
    if (-not $found) { $lines += "$Key=$Value" }
    [System.IO.File]::WriteAllLines($Path, $lines, [System.Text.UTF8Encoding]::new($false))
}

function Set-YamlScalar {
    param([string]$Path, [string]$Key, [string]$Value)
    $lines = @()
    $found = $false
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match "^\s*$([regex]::Escape($Key))\s*:") {
            $indent = ''
            if ($line -match '^(\s*)') { $indent = $matches[1] }
            $lines += "$indent$Key`: $Value"
            $found = $true
        } else {
            $lines += $line
        }
    }
    if (-not $found) { $lines += "$Key`: $Value" }
    [System.IO.File]::WriteAllLines($Path, $lines, [System.Text.UTF8Encoding]::new($false))
}

function Copy-Tree {
    param([string]$From, [string]$To)
    if (-not (Test-Path -LiteralPath $From)) { throw "Missing source: $From" }
    $args = @($From, $To, '/E', '/COPY:DAT', '/DCOPY:DAT', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP')
    & robocopy @args | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed for $From (exit $LASTEXITCODE)" }
}

function Ensure-Command {
    param([string]$Name, [string]$WingetId)
    if (Get-Command $Name -ErrorAction SilentlyContinue) { return }
    if ($SkipPrereqInstall) { throw "Missing prerequisite: $Name" }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw "Missing prerequisite: $Name; winget not found" }
    Write-Step "Installing $Name via winget"
    & winget install --id $WingetId -e --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) { throw "Install failed: $Name" }
}

function Get-DockerComposeArgs {
    param([string]$ComposePath, [string]$EnvPath)
    return @('compose', '-f', $ComposePath, '--env-file', $EnvPath)
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

$sourceDir = Join-Path $packageRoot 'source'
$privateDir = Join-Path $packageRoot 'private'
$dataDir = Join-Path $packageRoot 'data'
if (-not (Test-Path -LiteralPath $sourceDir)) { throw "Package source not found: $sourceDir" }
if (-not (Test-Path -LiteralPath $privateDir)) { throw "Package private data not found: $privateDir" }
if (-not (Test-Path -LiteralPath $dataDir)) { throw "Package data not found: $dataDir" }

Write-Step "Package root: $packageRoot"
Write-Step "Install root: $InstallRoot"

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget not found. Install App Installer from Microsoft Store, then rerun."
}
Ensure-Command -Name docker -WingetId 'Docker.DockerDesktop'
Ensure-Command -Name node -WingetId 'OpenJS.NodeJS.LTS'
Ensure-Command -Name npm -WingetId 'OpenJS.NodeJS.LTS'

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    if ($SkipPrereqInstall) { throw 'Missing prerequisite: uv' }
    Write-Step 'Installing uv'
    & powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $uvBin = Join-Path $env:USERPROFILE '.local\bin'
    $env:Path = "$uvBin;$env:Path"
}
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Ensure-Command -Name cloudflared -WingetId 'Cloudflare.cloudflared'
}

Write-Step 'Copying source'
Copy-Tree -From $sourceDir -To $InstallRoot

$backendDir = Join-Path $InstallRoot 'backend'
$deployDir = Join-Path $InstallRoot 'deploy'
$packageDataDir = Join-Path $InstallRoot 'data'
$packagePrivateDir = Join-Path $InstallRoot 'private'
if (-not (Test-Path -LiteralPath $packageDataDir)) { New-Item -ItemType Directory -Force -Path $packageDataDir | Out-Null }
if (-not (Test-Path -LiteralPath $packagePrivateDir)) { New-Item -ItemType Directory -Force -Path $packagePrivateDir | Out-Null }

Write-Step 'Restoring private env files'
Copy-Item -LiteralPath (Join-Path $privateDir 'backend.env') -Destination (Join-Path $backendDir '.env') -Force
Copy-Item -LiteralPath (Join-Path $privateDir 'deploy.env') -Destination (Join-Path $deployDir '.env') -Force
Copy-Item -LiteralPath (Join-Path $privateDir 'requirements.lock.txt') -Destination (Join-Path $backendDir 'requirements.lock.txt') -Force -ErrorAction SilentlyContinue

Write-Step 'Restoring data'
Copy-Tree -From (Join-Path $dataDir 'storage') -To (Join-Path $packageDataDir 'storage')
Copy-Tree -From (Join-Path $dataDir 'models') -To (Join-Path $packageDataDir 'models')

Set-EnvValue -Path (Join-Path $backendDir '.env') -Key 'OH_STORAGE_ROOT' -Value (Join-Path $packageDataDir 'storage')
Set-EnvValue -Path (Join-Path $backendDir '.env') -Key 'OH_MODEL_ROOT' -Value (Join-Path $packageDataDir 'models')
Set-EnvValue -Path (Join-Path $backendDir '.env') -Key 'OH_FRONTEND_DIST' -Value (Join-Path $InstallRoot 'frontend\dist')

Write-Step 'Restoring tunnel config'
$tunnelSource = Join-Path $privateDir 'tunnel'
$tunnelTarget = Join-Path $packageDataDir 'tunnel'
if (Test-Path -LiteralPath $tunnelSource) {
    Copy-Tree -From $tunnelSource -To $tunnelTarget
    $configPath = Join-Path $tunnelTarget 'config.yml'
    if (Test-Path -LiteralPath $configPath) {
        $credPath = Join-Path $tunnelTarget 'credentials.json'
        if (Test-Path -LiteralPath $credPath) {
            Set-YamlScalar -Path $configPath -Key 'credentials-file' -Value ($credPath -replace '\\','/')
        }
        $varTunnelDir = Join-Path $InstallRoot 'var\cloudflared'
        if (-not (Test-Path -LiteralPath $varTunnelDir)) { New-Item -ItemType Directory -Force -Path $varTunnelDir | Out-Null }
        Copy-Item -LiteralPath $configPath -Destination (Join-Path $varTunnelDir 'config.yml') -Force
        Copy-Item -LiteralPath (Join-Path $tunnelTarget 'credentials.json') -Destination (Join-Path $varTunnelDir 'credentials.json') -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Warning 'No tunnel config in package; run setup-tunnel.ps1 on target after install.'
}

Write-Step 'Installing Python environment'
& uv python install 3.12
Push-Location $backendDir
& uv sync --frozen --extra pipeline
Pop-Location
if ($LASTEXITCODE -ne 0) { throw 'uv sync failed' }

Write-Step 'Building frontend'
Push-Location (Join-Path $InstallRoot 'frontend')
if (Test-Path -LiteralPath 'package-lock.json') {
    & npm ci
} else {
    & npm install
}
if ($LASTEXITCODE -ne 0) { Pop-Location; throw 'npm install failed' }
& npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; throw 'npm build failed' }
Pop-Location

Write-Step 'Starting infrastructure'
$composePath = Join-Path $deployDir 'compose.yaml'
$deployEnvPath = Join-Path $deployDir '.env'
$composeArgs = Get-DockerComposeArgs -ComposePath $composePath -EnvPath $deployEnvPath
& docker @composeArgs up -d --wait --wait-timeout 180
if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }

$deployEnv = Read-EnvFile -Path $deployEnvPath
$pgUser = if ($deployEnv.ContainsKey('POSTGRES_USER')) { $deployEnv['POSTGRES_USER'] } else { 'oh_app' }
$pgDb = if ($deployEnv.ContainsKey('POSTGRES_DB')) { $deployEnv['POSTGRES_DB'] } else { 'occupational_health' }
$pgPassword = if ($deployEnv.ContainsKey('POSTGRES_PASSWORD')) { $deployEnv['POSTGRES_PASSWORD'] } else { '' }

Write-Step 'Restoring PostgreSQL dump'
$drop = "DROP DATABASE IF EXISTS `"$pgDb`" WITH (FORCE);"
& docker @composeArgs exec -T -e "PGPASSWORD=$pgPassword" postgres psql -U $pgUser -d postgres -c $drop
& docker @composeArgs exec -T -e "PGPASSWORD=$pgPassword" postgres psql -U $pgUser -d postgres -c "CREATE DATABASE `"$pgDb`";"
Get-Content -LiteralPath (Join-Path $privateDir 'postgres.sql') -Raw -Encoding UTF8 | & docker @composeArgs exec -T -e "PGPASSWORD=$pgPassword" postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1 -f -
if ($LASTEXITCODE -ne 0) { throw 'postgres restore failed' }

Write-Step 'Restoring Qdrant snapshot'
$backendEnv = Read-EnvFile -Path (Join-Path $backendDir '.env')
$qdrantUrl = if ($backendEnv.ContainsKey('OH_QDRANT_URL')) { $backendEnv['OH_QDRANT_URL'] } else { 'http://127.0.0.1:6333' }
$qdrantKey = if ($backendEnv.ContainsKey('OH_QDRANT_API_KEY')) { $backendEnv['OH_QDRANT_API_KEY'] } else { '' }
$collection = 'oh_chunks_v1'
$snapshotPath = Join-Path $dataDir 'oh_chunks_v1.snapshot'
$qdrantContainer = (& docker @composeArgs ps -q qdrant).Trim()
if (-not $qdrantContainer) { throw 'qdrant container not found' }
& docker cp $snapshotPath "$qdrantContainer`:/qdrant/snapshots/oh_chunks_v1.snapshot"
if ($LASTEXITCODE -ne 0) { throw 'qdrant snapshot copy failed' }
$snapshotUri = 'file:///qdrant/snapshots/oh_chunks_v1.snapshot'
$pythonExe = Join-Path $backendDir '.venv\Scripts\python.exe'
$restoreCode = "from qdrant_client import QdrantClient; from qdrant_client.http import models; c=QdrantClient(url=r'$qdrantUrl', api_key=r'$qdrantKey');`nif not c.collection_exists('$collection'):`n    c.create_collection(collection_name='$collection', vectors_config={'masked_dense': models.VectorParams(size=1024, distance=models.Distance.COSINE)});`nc.recover_snapshot(collection_name='$collection', location=r'$snapshotUri', wait=True); print('QDRANT RESTORE OK')"
& $pythonExe -c $restoreCode
if ($LASTEXITCODE -ne 0) { throw 'qdrant snapshot restore failed' }

Write-Step 'Running migrations'
Push-Location $backendDir
& $pythonExe -m alembic upgrade head
Pop-Location
if ($LASTEXITCODE -ne 0) { throw 'alembic upgrade failed' }

Write-Step 'Starting application watchdogs'
$launcherName = [string]::Concat([char]0x542F, [char]0x52A8, [char]0x9879, [char]0x76EE, '.bat')
$launcher = Join-Path $InstallRoot $launcherName
if (-not (Test-Path -LiteralPath $launcher)) {
    $launcher = Join-Path $sourceDir $launcherName
}
Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', "`"$launcher`"" -WorkingDirectory $InstallRoot -WindowStyle Minimized

Write-Host "INSTALL OK: $InstallRoot"
Write-Host 'Run deploy/portable/verify-portable.ps1 to validate.'
