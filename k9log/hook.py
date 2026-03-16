# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
# AGPL-3.0
"""
K9log Hook - Claude Code PreToolUse integration (thin adapter)
Registered via .claude/settings.json:
  hooks.PreToolUse -> python -m k9log.hook

Responsibilities (adapter only):
  1. Parse PreToolUse payload from stdin
  2. Build X_t / U_t from Claude Code-specific fields
  3. Delegate to core: load_constraints, check_compliance, write_cieu

Everything else (hash chain, fuse, policy pin, alerting, rotation)
is handled by the core. This file contains zero business logic.
Always exits 0 - never blocks Claude Code.
"""
import sys
import json
import os
import time
import socket
from datetime import datetime, timezone
from pathlib import Path


def main():
    t0 = time.time()
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}

    tool_name  = payload.get("tool_name",  "Unknown")
    tool_input = payload.get("tool_input", {})
    session_id = payload.get("session_id", "unknown")
    tool_use_id = payload.get("tool_use_id", "")

    # ── Load constraints from core ────────────────────────────────────────
    try:
        from k9log.constraints import load_constraints, check_compliance
        y_star_t = load_constraints(tool_name)
    except Exception as e:
        sys.stderr.write(f"[k9log] load_constraints failed: {e}\n")
        sys.exit(0)

    # ── Build params for compliance check ────────────────────────────────
    # Flatten tool_input into params so check_compliance can evaluate
    params = {}
    if isinstance(tool_input, dict):
        params = tool_input
    else:
        params = {"input": str(tool_input)}

    # ── Check compliance via core ─────────────────────────────────────────
    try:
        r = check_compliance(params, {"result": None}, y_star_t)
    except Exception as e:
        sys.stderr.write(f"[k9log] check_compliance failed: {e}\n")
        r = {"passed": True, "violations": [], "overall_severity": 0.0,
             "risk_level": "LOW"}

    # ── Build CIEU record ─────────────────────────────────────────────────
    cieu = {
        "event_type": "PreToolUse",
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "X_t": {
            "agent_name":   "Claude Code",
            "agent_type":   "coding_assistant",
            "session_id":   session_id,
            "tool_use_id":  tool_use_id,
            "user":         os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
            "hostname":     socket.gethostname(),
            "pid":          os.getpid(),
            "action_class": _action_class(tool_name),
        },
        "U_t": {
            "skill":  tool_name,
            "params": _safe_params(tool_input),
        },
        "Y_star_t": y_star_t,
        "Y_t+1": {
            "status": "recorded",
            "note":   "PreToolUse - execution outcome not yet known",
        },
        "R_t+1": {
            **r,
            "duration_sec": time.time() - t0,
        },
    }

    # ── Write via core logger (hash chain, fuse, policy pin all handled) ──
    try:
        from k9log.logger import get_logger
        get_logger().write_cieu(cieu)
    except Exception as e:
        sys.stderr.write(f"[k9log] Ledger write failed: {e}\n")

    # ── 人话违规提示 ──────────────────────────────────────────────────────
    if not r["passed"]:
        violations = r.get("violations", [])
        top = violations[0] if violations else {}
        severity = r.get("overall_severity", 0)
        matched = top.get("matched", "")
        vtype = top.get("type", "")

        tool_desc = {
            "Write": "is about to write a file",
            "Edit": "is about to edit a file",
            "Bash": "is about to run a command",
            "Read": "is about to read a file",
            "create_file": "is about to create a file",
        }.get(tool_name, f"is about to use {tool_name}")

        file_path = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("command", "")[:60] or "unknown"

        if "STAGING" in vtype or (matched and "staging" in matched.lower()):
            problem = "staging/test server URL detected — should never appear in production"
        elif "DENY_CONTENT" in vtype:
            problem = f'forbidden content detected: "{matched}"'
        elif "PATH" in vtype or "SCOPE" in vtype:
            problem = "outside allowed file paths"
        elif "SECRET" in vtype:
            problem = "possible hardcoded secret detected"
        else:
            problem = top.get("message", "constraint violation")

        badge = "🚨 CRITICAL" if severity >= 0.9 else "⚠️  WARNING" if severity >= 0.7 else "ℹ️  NOTICE"

        # 读取上下文信息
        session_id = payload.get("session_id", "unknown")[:8]
        agent = "Claude Code"

        # Y*_t 意图合约描述
        deny = y_star_t.get("constraints", {}).get("deny_content", [])
        allowed = y_star_t.get("constraints", {}).get("allowed_paths", [])
        intended_desc = ""
        if deny:
            intended_desc = "deny: " + ", ".join(deny[:2])
        elif allowed:
            intended_desc = "only write to: " + ", ".join(allowed[:2])
        else:
            intended_desc = "no constraints defined"

        # 实际内容
        actual = matched or tool_input.get("content", tool_input.get("command", str(tool_input)))[:80]

        sys.stderr.write(f"\n[K9 Audit] {badge}\n")
        sys.stderr.write(f"  WHO:       {agent} (session: {session_id}) → {tool_name}\n")
        sys.stderr.write(f"  CONTEXT:   About to write to: {file_path}\n")
        sys.stderr.write(f"  INTENDED:  {intended_desc}\n")
        sys.stderr.write(f"  ACTUAL:    \"{actual}\"\n")
        sys.stderr.write(f"  DEVIATION: {severity:.2f} — {problem}\n")
        sys.stderr.write(f"  ACTION:    Recorded in tamper-proof ledger\n")
        sys.stderr.write(f"             → k9log trace --last\n\n")

        # 保留原来给 Claude Code 读的机器格式
        sys.stderr.write(
            "[k9log] VIOLATION - " + tool_name + ": " +
            "; ".join(v["message"] for v in r["violations"]) + "\n"
        )

    sys.exit(0)


def _action_class(tool_name):
    """Map Claude Code tool names to CIEU action classes."""
    mapping = {
        "Write":   "WRITE",
        "Edit":    "WRITE",
        "MultiEdit": "WRITE",
        "str_replace_based_edit_tool": "WRITE",
        "Read":    "READ",
        "Bash":    "EXECUTE",
        "WebFetch": "NETWORK",
        "WebSearch": "NETWORK",
        "Delete":  "DELETE",
        "TodoWrite": "WRITE",
    }
    return mapping.get(tool_name, "EXECUTE")


def _safe_params(tool_input):
    """Serialize tool_input safely for CIEU record."""
    if not isinstance(tool_input, dict):
        return {"input": str(tool_input)[:500]}
    out = {}
    for k, v in tool_input.items():
        try:
            json.dumps(v)
            # Truncate large content fields
            if isinstance(v, str) and len(v) > 500:
                out[k] = v[:500] + "...[truncated]"
            else:
                out[k] = v
        except Exception:
            out[k] = str(v)[:200]
    return out


if __name__ == "__main__":
    main()
