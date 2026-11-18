# 安全推送公开仓库：只推送 public-clean 分支，不使用 --force。
# 前提：当前目录为项目根目录，且 public-clean 分支存在。
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

$branch = 'public-clean'
$remote = 'gmk'

if (-not (git rev-parse --verify --quiet "refs/heads/$branch")) {
    throw "本地缺少分支：$branch"
}

# 拉取远程 main，随后以 ours 策略合并其 README 初始提交，避免使用强制推送。
git fetch $remote main
if ($LASTEXITCODE -ne 0) { throw 'git fetch 失败，请检查网络或 GitHub 凭据' }

git checkout $branch
git merge --allow-unrelated-histories -X ours $remote/main -m "Merge upstream README before public release"
if ($LASTEXITCODE -ne 0) { throw 'git merge 失败，请手动检查冲突' }

git push $remote "${branch}:main"
if ($LASTEXITCODE -ne 0) { throw 'git push 失败，请检查 GitHub 权限' }

Write-Host 'Public release pushed to main.'
