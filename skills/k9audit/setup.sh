#!/bin/bash
# K9Audit OpenClaw Setup Script
# ================================
# Installs K9Audit and registers it as an OpenClaw gateway:startup hook.
# After running this script, K9Audit automatically monitors all OpenClaw
# skill calls with zero code changes needed.
#
# Usage:
#   bash setup.sh
#
# What this script does:
#   1. Installs k9audit-hook via pip
#   2. Registers k9log openclaw-watch in OpenClaw's gateway:startup hook
#   3. Starts the watcher immediately (without gateway restart)

set -e

echo ""
echo "======================================"
echo "  K9Audit OpenClaw Setup"
echo "======================================"
echo ""

# ── Step 1: Install k9audit-hook ─────────────────────────────────────────────

echo "[1/3] Installing k9audit-hook..."
if ! command -v k9log &>/dev/null; then
    pip install k9audit-hook --quiet
    echo "  ✅ k9audit-hook installed"
else
    echo "  ✅ k9audit-hook already installed ($(k9log --version 2>/dev/null || echo 'ok'))"
fi

# ── Step 2: Register gateway:startup hook in OpenClaw ────────────────────────

echo ""
echo "[2/3] Registering gateway:startup hook in OpenClaw..."

HOOKS_DIR="$HOME/.openclaw/hooks/k9audit"
HOOK_MD="$HOOKS_DIR/HOOK.md"

mkdir -p "$HOOKS_DIR"

cat > "$HOOK_MD" << 'HOOKEOF'
---
name: k9audit
description: K9Audit causal audit — monitors all OpenClaw tool calls automatically
events:
  - gateway:startup
enabled: true
---

# K9Audit Background Watcher

When OpenClaw gateway starts, launch the K9Audit session watcher in background.
The watcher monitors all agent session files and writes CIEU audit records.

```bash
python -m k9log.openclaw_watcher &
```
HOOKEOF

echo "  ✅ Hook registered at: $HOOK_MD"

# ── Step 3: Start watcher immediately ────────────────────────────────────────

echo ""
echo "[3/3] Starting K9Audit watcher now..."

# Check if already running
PIDFILE="$HOME/.k9log/openclaw_watcher.pid"
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "  ✅ Watcher already running (pid=$PID)"
    else
        rm -f "$PIDFILE"
        python -m k9log.openclaw_watcher &
        echo "  ✅ Watcher started (pid=$!)"
    fi
else
    python -m k9log.openclaw_watcher &
    echo "  ✅ Watcher started (pid=$!)"
fi

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "======================================"
echo "  K9Audit is now active!"
echo "======================================"
echo ""
echo "  Every OpenClaw skill call is now:"
echo "  • Recorded in the CIEU ledger"
echo "  • Checked against your AGENTS.md constraints"
echo "  • Traceable with k9log trace --last"
echo ""
echo "  Commands:"
echo "    k9log stats              — violation summary"
echo "    k9log verify-log         — verify hash chain"
echo "    k9log trace --last       — trace last violation"
echo "    k9log report --output report.html"
echo ""
echo "  Watcher runs automatically on future gateway restarts."
echo ""
