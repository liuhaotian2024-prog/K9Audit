# K9Audit 发布脚本
# 用法: powershell -ExecutionPolicy Bypass -File release.ps1 -Version 0.2.6

param(
    [Parameter(Mandatory=$true)]
    [string]$Version
)

$base = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. 改版本号
$cli = "$base\k9log\cli.py"
$pyp = "$base\pyproject.toml"
(Get-Content $cli -Raw) -replace "version='[^']*'", "version='$Version'" | Set-Content $cli -NoNewline
(Get-Content $pyp -Raw) -replace 'version = "[^"]*"', "version = `"$Version`"" | Set-Content $pyp -NoNewline
Write-Host "OK  版本号已改为 $Version" -ForegroundColor Green

# 2. 打包
python -m build
if ($LASTEXITCODE -ne 0) { Write-Host "ERR 打包失败" -ForegroundColor Red; exit 1 }

# 3. 上传
python -m twine upload "dist\k9audit_hook-$Version*"
if ($LASTEXITCODE -eq 0) {
    Write-Host "OK  https://pypi.org/project/k9audit-hook/$Version/" -ForegroundColor Green
    git add k9log/cli.py pyproject.toml
    git commit -m "chore: release v$Version"
    git push
    Write-Host "OK  Git 已推送" -ForegroundColor Green
}
