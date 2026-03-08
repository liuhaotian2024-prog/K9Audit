# K9 Audit — Setup Script
# Creates C:\Users\liuha\OneDrive\桌面\K9Audit\ from K9Solo source
# ============================================================

$src  = "C:\Users\liuha\OneDrive\桌面\K9Solo"
$dst  = "C:\Users\liuha\OneDrive\桌面\K9Audit"
$klog = "k9log"

Write-Host "`n=== K9 Audit — Build from K9Solo ===" -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path "$dst\docs" | Out-Null
New-Item -ItemType Directory -Force -Path "$dst\challenge" | Out-Null
New-Item -ItemType Directory -Force -Path "$dst\$klog\governance" | Out-Null
Write-Host "  ✓ Directories ready" -ForegroundColor Green

$auditFiles = @("core.py","logger.py","tracer.py","verifier.py","causal_analyzer.py",
    "constraints.py","report.py","cli.py","alerting.py","identity.py","redact.py",
    "agents_md_parser.py","__init__.py","__main__.py")
foreach ($f in $auditFiles) {
    if (Test-Path "$src\$klog\$f") {
        Copy-Item "$src\$klog\$f" "$dst\$klog\$f"
        Write-Host "  ✓ k9log\$f" -ForegroundColor Green
    } else {
        Write-Host "  ✗ k9log\$f NOT FOUND" -ForegroundColor Red
    }
}

$closed = @("counterfactual.py","taint.py","federated.py","skill_recommender.py",
    "fuse.py","decision.py","mcp_server.py","policy_pack.py","metalearning.py")
$danger = $false
foreach ($f in $closed) {
    if (Test-Path "$dst\$klog\$f") {
        Write-Host "  ✗ DANGER: $f present!" -ForegroundColor Red
        $danger = $true
    }
}
if ($danger) { Write-Host "`n⛔ Safety check failed." -ForegroundColor Red; exit 1 }

Write-Host "`n✅ Done. K9Audit at: $dst" -ForegroundColor Cyan
