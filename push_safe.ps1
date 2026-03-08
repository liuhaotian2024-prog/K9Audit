# K9 Audit — GitHub Push Script
# Run from: C:\Users\liuha\OneDrive\桌面\K9Solo\
# ============================================================

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repo = "C:\Users\liuha\OneDrive\桌面\K9Solo"
Set-Location $repo

# ── Step 1: Safety check — closed-source files must not be tracked ──
Write-Host "`n=== Step 1: Safety Check ===" -ForegroundColor Cyan
$closed = @(
    "k9log\counterfactual.py",
    "k9log\taint.py",
    "k9log\federated.py",
    "k9log\skill_recommender.py"
)
$danger = $false
foreach ($f in $closed) {
    $ignored = git check-ignore -v $f 2>&1
    if ($ignored) {
        Write-Host "  ✓ Excluded: $f" -ForegroundColor Green
    } else {
        Write-Host "  ✗ DANGER — NOT excluded: $f" -ForegroundColor Red
        $danger = $true
    }
}
if ($danger) {
    Write-Host "`n⛔ Closed-source files would be pushed. Aborting." -ForegroundColor Red
    exit 1
}

# ── Step 2: Stage and show what will be committed ───────────
Write-Host "`n=== Step 2: Files to be committed ===" -ForegroundColor Cyan
git add .
git status --short

Write-Host "`n--- Review the list above carefully ---" -ForegroundColor Yellow
$confirm = Read-Host "Proceed with commit? (yes/no)"
if ($confirm -ne "yes") { Write-Host "Aborted."; exit 0 }

# ── Step 3: Commit ───────────────────────────────────────────
$msg = "feat: K9 Audit v1.0 — CIEU engine, governance core, metalearning (AGPL-3.0)"
git commit -m $msg
Write-Host "`n✓ Committed: $msg" -ForegroundColor Green

# ── Step 4: Push ─────────────────────────────────────────────
Write-Host "`n=== Step 4: Pushing to GitHub ===" -ForegroundColor Cyan
git remote set-url origin https://github.com/liuhaotian2024-prog/k9-solo-hook.git 2>$null
git push -u origin main
Write-Host "`n✓ Done." -ForegroundColor Green
