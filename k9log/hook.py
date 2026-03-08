# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
# AGPL-3.0
"""
K9log Hook - Claude Code PreToolUse integration

Registered via .claude/settings.json:
  hooks.PreToolUse -> python -m k9log.hook

Reads tool call from stdin, writes CIEU record to Ledger, fires alerts on violations.
Always exits 0 - never blocks Claude Code.
"""
import sys, json, os, time, socket, hashlib
from datetime import datetime, timezone
from pathlib import Path

INTENT_CONTRACTS = {
    "Write":    {"deny_content": ["staging.internal", "sandbox.", ".env", "api_key", "secret"],
                 "allowed_paths": ["./src/**", "./tests/**", "./docs/**", "./output/**"]},
    "Read":     {},
    "Bash":     {"deny_content": ["rm -rf /", "sudo rm", "format c:"]},
    "WebFetch": {"deny_content": ["staging.internal", "localhost", "127.0.0.1"]},
    "_default": {},
}

def load_contract(tool_name):
    f = Path.home() / ".k9log" / "intents" / f"{tool_name}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8")).get("constraints", {})
        except Exception:
            pass
    return INTENT_CONTRACTS.get(tool_name, INTENT_CONTRACTS["_default"])

def flatten_strings(obj, depth=0):
    if depth > 5: return []
    if isinstance(obj, str): return [obj]
    if isinstance(obj, dict): return [s for v in obj.values() for s in flatten_strings(v, depth+1)]
    if isinstance(obj, list): return [s for i in obj for s in flatten_strings(i, depth+1)]
    return []

def path_allowed(path, patterns):
    import fnmatch
    path = path.replace("\\", "/")
    for p in patterns:
        p = p.replace("\\", "/")
        if "**" in p:
            base = p.split("**")[0].rstrip("/")
            if path.startswith(base.lstrip("./")):  return True
            if path.startswith(base):               return True
        elif fnmatch.fnmatch(path, p): return True
    return False

def check_violations(tool_name, tool_input, constraints):
    violations = []
    for pattern in constraints.get("deny_content", []):
        for val in flatten_strings(tool_input):
            if pattern.lower() in val.lower():
                violations.append({"type": "DENY_CONTENT", "pattern": pattern,
                    "found_in": val[:120], "severity": 0.9,
                    "message": f"Content contains forbidden pattern: '{pattern}'"})
    file_path = tool_input.get("file_path") or tool_input.get("path") or ""
    allowed   = constraints.get("allowed_paths", [])
    if file_path and allowed and not path_allowed(file_path, allowed):
        violations.append({"type": "PATH_VIOLATION", "path": file_path,
            "allowed": allowed, "severity": 0.7,
            "message": f"Path '{file_path}' is outside allowed directories"})
    return violations

def write_cieu(record):
    log_dir  = Path.home() / ".k9log" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "k9log.cieu.jsonl"
    prev_hash, seq = "genesis", 0
    if log_file.exists():
        try:
            lines = log_file.read_text(encoding="utf-8").strip().splitlines()
            if lines:
                last = json.loads(lines[-1])
                prev_hash = last.get("hash", "genesis")
                seq       = last.get("seq", 0) + 1
        except Exception: pass
    record["seq"] = seq
    record["prev_hash"] = prev_hash
    chain_input = json.dumps(record, sort_keys=True, ensure_ascii=True)
    record["hash"] = hashlib.sha256((prev_hash + chain_input).encode()).hexdigest()
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def main():
    t0 = time.time()
    try:
        payload    = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload    = {}
    tool_name  = payload.get("tool_name",  "Unknown")
    tool_input = payload.get("tool_input", {})
    session_id = payload.get("session_id", "unknown")
    constraints = load_contract(tool_name)
    violations  = check_violations(tool_name, tool_input, constraints)
    passed      = not violations
    severity    = max((v["severity"] for v in violations), default=0.0)
    risk        = "CRITICAL" if severity >= 0.9 else "HIGH" if severity >= 0.7 else "LOW"
    cieu = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "X_t":       {"agent_name": "Claude Code", "agent_type": "coding_assistant",
                      "session_id": session_id,
                      "user": os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
                      "hostname": socket.gethostname(), "pid": os.getpid()},
        "U_t":       {"skill": tool_name, "params": tool_input},
        "Y_star_t":  {"constraints": constraints,
                      "y_star_meta": {"source": "hook.py", "version": "1.0.0"}},
        "Y_t+1":     {"status": "recorded",
                      "note": "PreToolUse - execution outcome not yet known"},
        "R_t+1":     {"passed": passed, "violations": violations,
                      "overall_severity": severity, "risk_level": risk,
                      "duration_sec": time.time() - t0},
    }
    try:
        write_cieu(cieu)
    except Exception as e:
        sys.stderr.write(f"[k9log] Ledger write failed: {e}\n")
    if not passed:
        try:
            from k9log.alerting import get_alert_manager
            get_alert_manager().on_violation(cieu)
        except Exception: pass
        sys.stderr.write("[k9log] VIOLATION - " + tool_name + ": " +
            "; ".join(v["message"] for v in violations) + "\n")
    sys.exit(0)

if __name__ == "__main__":
    main()
