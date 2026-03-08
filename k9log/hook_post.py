# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
# AGPL-3.0
"""
K9log Hook Post - Claude Code PostToolUse integration

Registered via .claude/settings.json:
  hooks.PostToolUse -> python -m k9log.hook_post

Reads tool result from stdin, calls logger.update_outcome() to
record the actual execution result of the preceding PreToolUse.
Always exits 0 - never blocks Claude Code.
"""
import sys, json, time

def main():
    t0 = time.time()
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}

    tool_use_id = payload.get("tool_use_id", "")
    if not tool_use_id:
        sys.exit(0)

    # Extract outcome from PostToolUse payload
    tool_response = payload.get("tool_response", {})
    output        = tool_response.get("output", "")
    is_error      = tool_response.get("is_error", False)

    outcome = {
        "exit_code":    1 if is_error else 0,
        "stdout":       output if not is_error else "",
        "stderr":       "",
        "error":        output if is_error else "",
        "duration_sec": time.time() - t0,
    }

    try:
        from k9log.logger import get_logger
        get_logger().update_outcome(tool_use_id, outcome)
    except Exception as e:
        sys.stderr.write(f"[k9log] PostToolUse outcome write failed: {e}\n")

    sys.exit(0)

if __name__ == "__main__":
    main()
