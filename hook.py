# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""
K9log Hook — Claude Code PreToolUse integration

Claude Code calls this script before every tool use via:
  .claude/settings.json → hooks.PreToolUse

This script:
  1. Reads the tool call from stdin (JSON)
  2. Maps it to a CIEU five-tuple
  3. Writes the record to the hash-chained Ledger
  4. Checks constraints and fires alerts on violations
  5. Always exits 0 — never blocks Claude Code execution

Usage:
  Registered automatically via .claude/settings.json.
  Do not call directly.
"""
import sys
import json
import os
import time
import socket
from datetime import datetime, timezone
from pathlib import Path


# ── Constraint config ────────────────────────────────────────────────────────
# Edit this section to define your intent contracts.
# These are the Y*_t rules that K9 Audit enforces.

INTENT_CONTRACTS = {
    # File write constraints
    "Write": {
        "deny_content": ["staging.internal", "sandbox.", ".env", "api_key", "secret"],
        "allowed_paths": ["./src/**", "./tests/**", "./docs/**", "./output/**"],
    },
    # File read — usually unconstrained, but log everything
    "Read": {},
    # Bash/shell command constraints
    "Bash": {
        "deny_content": ["rm -rf /", "sudo rm", "format c:", "> /dev/sda"],
    },
    # Web fetch constraints
    "WebFetch": {
        "deny_content": ["staging.internal", "localhost", "127.0.0.1", "169.254."],
    },
    # Default: log everything, no specific constraints
    "_default": {},
}


def load_intent_contract(tool_name: str) -> dict:
    """
    Load Y*_t for a given tool.
    Priority: ~/.k9log/intents/<tool_name>.json > INTENT_CONTRACTS > _default
    """
    # Check for external intent contract file first
    intent_file = Path.home() / ".k9log" / "intents" / f"{tool_name}.json"
    if intent_file.exists():
        try:
            with open(intent_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("constraints", {})
        except Exception:
            pass

    return INTENT_CONTRACTS.get(tool_name, INTENT_CONTRACTS["_default"])


def check_violations(tool_name: str, tool_input: dict, constraints: dict) -> list:
    """Check tool input against constraints. Returns list of violations."""
    violations = []

    deny_content = constraints.get("deny_content", [])
    allowed_paths = constraints.get("allowed_paths", [])

    # Flatten all string values from tool_input for content checking
    all_values = _flatten_strings(tool_input)

    for pattern in deny_content:
        for val in all_values:
            if pattern.lower() in val.lower():
                violations.append({
                    "type": "DENY_CONTENT",
                    "pattern": pattern,
                    "found_in": val[:120],
                    "severity": 0.9,
                    "message": f"Content contains forbidden pattern: '{pattern}'"
                })

    # Path constraint check (applies to Write, Read tools)
    file_path = tool_input.get("file_path") or tool_input.get("path") or ""
    if file_path and allowed_paths:
        if not _path_allowed(file_path, allowed_paths):
            violations.append({
                "type": "PATH_VIOLATION",
                "path": file_path,
                "allowed": allowed_paths,
                "severity": 0.7,
                "message": f"Path '{file_path}' is outside allowed directories"
            })

    return violations


def _flatten_strings(obj, depth=0) -> list:
    """Recursively extract all string values from a dict/list."""
    if depth > 5:
        return []
    results = []
    if isinstance(obj, str):
        results.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            results.extend(_flatten_strings(v, depth + 1))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_flatten_strings(item, depth + 1))
    return results


def _path_allowed(path: str, allowed_patterns: list) -> bool:
    """Check if path matches any allowed pattern (glob-style **)."""
    import fnmatch
    path = path.replace("\\", "/")
    for pattern in allowed_patterns:
        pattern = pattern.replace("\\", "/")
        # Handle ** glob
        if "**" in pattern:
            base = pattern.split("**")[0].rstrip("/")
            if path.startswith(base.lstrip("./")):
                return True
            if path.startswith(base):
                return True
        elif fnmatch.fnmatch(path, pattern):
            return True
    return False


def write_cieu_record(record: dict):
    """Write one CIEU record to the hash-chained Ledger."""
    log_dir = Path.home() / ".k9log" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "k9log.cieu.jsonl"

    # Load previous hash for chain
    prev_hash = "genesis"
    seq = 0
    if log_file.exists():
        try:
            lines = log_file.read_text(encoding="utf-8").strip().splitlines()
            if lines:
                last = json.loads(lines[-1])
                prev_hash = last.get("hash", "genesis")
                seq = last.get("seq", 0) + 1
        except Exception:
            pass

    # Compute hash for this record
    import hashlib
    record["seq"] = seq
    record["prev_hash"] = prev_hash
    chain_input = json.dumps(record, sort_keys=True, ensure_ascii=True)
    record["hash"] = hashlib.sha256(
        (prev_hash + chain_input).encode()
    ).hexdigest()

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def fire_alert(cieu_record: dict):
    """Send real-time alert on violation (Telegram/Slack if configured)."""
    try:
        from k9log.alerting import get_alert_manager
        manager = get_alert_manager()
        manager.on_violation(cieu_record)
    except Exception:
        pass  # alerting failure must never affect hook execution


def main():
    start_time = time.time()

    # ── Read Claude Code hook payload from stdin ─────────────────────────────
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    tool_name  = payload.get("tool_name", "Unknown")
    tool_input = payload.get("tool_input", {})
    session_id = payload.get("session_id", "unknown-session")

    # ── Load Y*_t (intent contract) ──────────────────────────────────────────
    constraints = load_intent_contract(tool_name)

    # ── Check compliance ─────────────────────────────────────────────────────
    violations = check_violations(tool_name, tool_input, constraints)
    passed     = len(violations) == 0
    severity   = max((v["severity"] for v in violations), default=0.0)
    risk       = "CRITICAL" if severity >= 0.9 else "HIGH" if severity >= 0.7 else "LOW"

    # ── Build CIEU record ────────────────────────────────────────────────────
    cieu = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "X_t": {
            "agent_name": "Claude Code",
            "agent_type": "coding_assistant",
            "session_id": session_id,
            "user": os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
        },
        "U_t": {
            "skill": tool_name,
            "params": tool_input,
        },
        "Y_star_t": {
            "constraints": constraints,
            "y_star_meta": {
                "source": "hook.py",
                "version": "1.0.0",
            }
        },
        "Y_t+1": {
            "status": "recorded",
            "note": "PreToolUse — execution outcome not yet known"
        },
        "R_t+1": {
            "passed": passed,
            "violations": violations,
            "overall_severity": severity,
            "risk_level": risk,
            "duration_sec": time.time() - start_time,
        }
    }

    # ── Write to Ledger ──────────────────────────────────────────────────────
    try:
        write_cieu_record(cieu)
    except Exception as e:
        # Never crash Claude Code
        sys.stderr.write(f"[k9log] Ledger write failed: {e}\n")

    # ── Fire alert on violation ──────────────────────────────────────────────
    if not passed:
        fire_alert(cieu)
        sys.stderr.write(
            f"[k9log] ⚠️  VIOLATION — {tool_name}: "
            + "; ".join(v["message"] for v in violations) + "\n"
        )

    # ── Always exit 0 — never block Claude Code ──────────────────────────────
    sys.exit(0)


if __name__ == "__main__":
    main()


# ── NOTE ──────────────────────────────────────────────────────────────────────
# This file is a standalone copy used by Install-K9Solo.ps1 when k9log is not
# yet installed as a package. It is kept here solely for that installer script.
#
# If you are using `pip install k9audit-hook`, use the package version instead:
#
#   python -m k9log.hook       ← PreToolUse
#   python -m k9log.hook_post  ← PostToolUse
#
# Do NOT reference this root-level hook.py directly in your .claude/settings.json.
# ──────────────────────────────────────────────────────────────────────────────
