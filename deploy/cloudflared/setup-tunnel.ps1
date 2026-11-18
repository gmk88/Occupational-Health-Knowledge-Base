param(
  [string]$Domain = "kb.guanmingkun.ltd",
  [string]$TunnelName = "oh-kb"
)

# 一次性创建 Cloudflare Tunnel、绑定域名，并写好 config.yml。
# 用法：
#   powershell -ExecutionPolicy Bypass -File deploy\cloudflared\setup-tunnel.ps1 -Domain kb.guanmingkun.ltd

$ErrorActionPreference = "Stop"

$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (-not (Test-Path $cf)) {
  $command = Get-Command cloudflared -ErrorAction SilentlyContinue
  if ($command) { $cf = $command.Source } else { throw "未找到 cloudflared，请先执行 winget install --id Cloudflare.cloudflared -e" }
}

$configPath = Join-Path $PSScriptRoot "config.yml"
$cloudflaredDir = Join-Path $env:USERPROFILE ".cloudflared"
$certPath = Join-Path $cloudflaredDir "cert.pem"

if (-not (Test-Path $certPath)) {
  Write-Host "浏览器将打开 Cloudflare 登录页，请登录后选择kb.guanmingkun.ltd。" -ForegroundColor Yellow
  & $cf tunnel login
  if ($LASTEXITCODE -ne 0) { throw "cloudflared tunnel login 失败" }
}

$list = (& $cf tunnel list 2>&1 | Out-String)
$id = ""
$existing = [regex]::Match(
  $list,
  "([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\s+$([regex]::Escape($TunnelName))"
)
if ($existing.Success) {
  $id = $existing.Groups[1].Value
  Write-Host "复用已有隧道 $TunnelName ($id)"
} else {
  $created = (& $cf tunnel create $TunnelName 2>&1 | Out-String)
  if ($LASTEXITCODE -ne 0) { throw "创建隧道失败：$created" }
  $match = [regex]::Match($created, "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
  if (-not $match.Success) { throw "无法从输出解析隧道 ID：$created" }
  $id = $match.Value
  Write-Host "已创建隧道 $TunnelName ($id)"
}

try {
  & $cf tunnel route dns $TunnelName $Domain | Out-Null
  Write-Host "已把 $Domain 指向隧道" -ForegroundColor Green
} catch {
  Write-Host "DNS 记录可能已存在，请到 Cloudflare DNS 面板确认 $Domain 的 CNAME 指向 $id.cfargotunnel.com" -ForegroundColor Yellow
}

$credentials = Join-Path $cloudflaredDir "$id.json"
if (-not (Test-Path $credentials)) { throw "找不到凭证文件：$credentials" }

$content = [System.IO.File]::ReadAllText($configPath, [System.Text.Encoding]::UTF8)
$content = $content.Replace("C:\Users\ASUS\.cloudflared", $cloudflaredDir)
$content = $content.Replace("REPLACE_WITH_TUNNEL_ID", $id)
$content = $content.Replace("kb.guanmingkun.ltd", $Domain)
[System.IO.File]::WriteAllText($configPath, $content, [System.Text.UTF8Encoding]::new($false))

& $cf tunnel --config $configPath ingress validate

Write-Host ""
Write-Host "配置完成。接下来：" -ForegroundColor Green
Write-Host "  1. 确认后端已启动（启动项目.bat）"
Write-Host "  2. 双击 启动公网访问.bat"
Write-Host "  3. 对方使用 https://$Domain/mcp/ 接入"
