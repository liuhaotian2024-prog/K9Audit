# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
# AGPL-3.0
"""
K9log OpenClaw Watcher — zero-friction background audit for OpenClaw agents.

Monitors ~/.openclaw/agents/*/sessions/*.jsonl in real-time.
Every toolCall entry is translated via openclaw_adapter → NormalizedEvent
and written to the K9Audit CIEU ledger.

No code changes needed in skills. No PreToolUse hook needed.
Works by tailing OpenClaw's own session files.

Usage:
    # Start watcher (runs in background)
    k9log openclaw-watch start

    # Stop watcher
    k9log openclaw-watch stop

    # Status
    k9log openclaw-watch status

Or programmatically:
    from k9log.openclaw_watcher import start_watcher, stop_watcher
"""
from __future__ import annotations

import json
import os
import sys
import time
import signal
import logging
import threading
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Set

_log = logging.getLogger("k9log.openclaw_watcher")

# ── Paths ─────────────────────────────────────────────────────────────────────

OPENCLAW_DIR   = Path.home() / ".openclaw"
SESSIONS_GLOB  = "agents/*/sessions/*.jsonl"
PID_FILE       = Path.home() / ".k9log" / "openclaw_watcher.pid"
STATE_FILE     = Path.home() / ".k9log" / "openclaw_watcher_state.json"

# Poll interval in seconds (how often to check for new lines)
POLL_INTERVAL  = 0.5

# ── State: tracks read position per file ──────────────────────────────────────

class FileState:
    """Tracks read position and seen tool_call IDs for one session file."""
    def __init__(self, path: Path):
        self.path     = path
        self.position = path.stat().st_size  # start at end (don't replay history)
        self.seen_ids: Set[str] = set()      # deduplicate toolCallIds


class WatcherState:
    """All tracked session files."""
    def __init__(self):
        self.files: Dict[str, FileState] = {}
        self.lock = threading.Lock()

    def get_or_create(self, path: Path) -> FileState:
        key = str(path)
        with self.lock:
            if key not in self.files:
                self.files[key] = FileState(path)
            return self.files[key]

    def cleanup_missing(self) -> None:
        with self.lock:
            missing = [k for k in self.files if not Path(k).exists()]
            for k in missing:
                del self.files[k]


# ── JSONL line parser ──────────────────────────────────────────────────────────

def _parse_tool_call(line: str) -> Optional[dict]:
    """
    Parse one JSONL line from an OpenClaw session file.
    Returns a dict with tool_name, tool_input, tool_call_id if it's a toolCall.
    Returns None for all other line types.

    OpenClaw session JSONL formats:
      {"message": {"role": "assistant", "content": [{"type": "toolCall", "name": "...", "input": {...}, "id": "toolu_..."}]}}
      {"role": "toolResult", "toolCallId": "toolu_...", "content": [...]}
    """
    try:
        data = json.loads(line.strip())
    except (json.JSONDecodeError, ValueError):
        return None

    # Format 1: message wrapper
    msg = data.get("message", data)
    role = msg.get("role", "")

    if role == "assistant":
        content = msg.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "toolCall":
                    return {
                        "tool_name":    block.get("name", "unknown"),
                        "tool_input":   block.get("input", {}),
                        "tool_call_id": block.get("id", ""),
                        "stop_reason":  msg.get("stopReason", ""),
                    }
    return None


def _parse_tool_result(line: str) -> Optional[dict]:
    """
    Parse a toolResult line to get execution outcome.
    Returns dict with tool_call_id, is_error, content or None.
    """
    try:
        data = json.loads(line.strip())
    except (json.JSONDecodeError, ValueError):
        return None

    msg = data.get("message", data)
    role = msg.get("role", data.get("role", ""))

    if role == "toolResult":
        return {
            "tool_call_id": msg.get("toolCallId", data.get("toolCallId", "")),
            "is_error":     msg.get("isError", data.get("isError", False)),
            "content":      msg.get("content", data.get("content", [])),
        }
    return None


# ── CIEU writer ───────────────────────────────────────────────────────────────

def _write_cieu(tool_name: str, tool_input: dict, session_file: Path,
                agent_id: str) -> None:
    """Translate a toolCall into a CIEU record and write to ledger."""
    try:
        from k9log.logger import get_logger
        from k9log.constraints import load_constraints, check_compliance
        from k9log.identity import get_agent_identity
        from k9log.skill_source import get_active_skill_source

        # Normalize via openclaw_adapter
        x_t = {
            "agent_name":  "OpenClaw",
            "agent_type":  "openclaw",
            "agent_id":    agent_id,
            "session_id":  session_file.stem,
            "user":        os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
            "hostname":    socket.gethostname(),
            "pid":         os.getpid(),
            "watcher":     "k9log.openclaw_watcher",
        }

        # Add skill_source if set
        skill_src = get_active_skill_source(session_id=session_file.stem)
        if skill_src:
            x_t["skill_source"] = skill_src

        # Use openclaw_adapter to map tool_name → ActionClass
        try:
            from k9log.openclaw_adapter import normalize_openclaw
            event = normalize_openclaw(tool_name, tool_input, x_t=x_t)
            action_class = event.action_class
        except Exception:
            action_class = "EXECUTE"

        u_t = {
            "skill":        tool_name,
            "skill_module": "openclaw",
            "params":       _safe_params(tool_input),
        }

        # Load constraints — search agent-specific workspace first
        agent_workspace = Path.home() / '.openclaw' / 'agents' / agent_id / 'workspace'
        if agent_workspace.exists():
            os.chdir(agent_workspace)
        y_star_t = load_constraints(tool_name)

        # Check compliance
        r_t_plus_1 = check_compliance(u_t["params"], {"result": None}, y_star_t)

        import uuid as _uuid
        cieu = {
            "event_type": "PreToolUse",
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "call_id":    str(_uuid.uuid4()),
            "X_t":        x_t,
            "U_t":        u_t,
            "Y_star_t":   y_star_t,
            "Y_t+1":      {"status": "recorded", "note": "OpenClaw watcher — outcome pending"},
            "R_t+1":      r_t_plus_1,
        }

        get_logger().write_cieu(cieu)

        if not r_t_plus_1.get("passed", True):
            violations = r_t_plus_1.get("violations", [])
            msgs = "; ".join(v.get("message", "") for v in violations)
            _log.warning("[k9-openclaw] VIOLATION %s: %s", tool_name, msgs)
            print(f"\n[K9 Audit] ⚠️  VIOLATION detected in OpenClaw tool call: {tool_name}")
            print(f"  Constraint: {msgs}")
            print(f"  Run: k9log trace --last\n")

    except Exception as e:
        _log.debug("k9log openclaw_watcher: write_cieu failed: %s", e)


def _safe_params(tool_input: dict) -> dict:
    """Serialize tool_input safely."""
    if not isinstance(tool_input, dict):
        return {"input": str(tool_input)[:500]}
    out = {}
    for k, v in tool_input.items():
        try:
            json.dumps(v)
            out[k] = v[:500] if isinstance(v, str) and len(v) > 500 else v
        except Exception:
            out[k] = str(v)[:200]
    return out


# ── File tail reader ──────────────────────────────────────────────────────────

def _read_new_lines(fstate: FileState) -> list[str]:
    """Read any new lines appended since last read."""
    try:
        current_size = fstate.path.stat().st_size
        if current_size <= fstate.position:
            return []
        with open(fstate.path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(fstate.position)
            new_lines = f.readlines()
        fstate.position = current_size
        return new_lines
    except (OSError, IOError):
        return []


# ── Main watcher loop ─────────────────────────────────────────────────────────

_stop_event = threading.Event()


def _watcher_loop() -> None:
    """Main loop: poll all session files for new toolCall entries."""
    state = WatcherState()
    _log.info("k9log openclaw_watcher: started, watching %s", OPENCLAW_DIR / SESSIONS_GLOB)

    # Set skill source env vars for this watcher process
    os.environ.setdefault("K9LOG_SKILL_NAME",    "k9audit")
    os.environ.setdefault("K9LOG_SKILL_SOURCE",  "clawhub")
    os.environ.setdefault("K9LOG_SKILL_SLUG",    "liuhaotian2024-prog/k9audit")

    while not _stop_event.is_set():
        # Discover all session files
        for session_file in OPENCLAW_DIR.glob(SESSIONS_GLOB):
            if not session_file.is_file():
                continue
            if session_file.name.endswith(".deleted"):
                continue

            # Extract agent_id from path: agents/<agentId>/sessions/<sid>.jsonl
            try:
                agent_id = session_file.parts[-3]  # agents/<agentId>/sessions
            except IndexError:
                agent_id = "unknown"

            fstate = state.get_or_create(session_file)
            new_lines = _read_new_lines(fstate)

            for line in new_lines:
                if not line.strip():
                    continue
                tool_call = _parse_tool_call(line)
                if tool_call:
                    tool_call_id = tool_call.get("tool_call_id", "")
                    # Deduplicate
                    if tool_call_id and tool_call_id in fstate.seen_ids:
                        continue
                    if tool_call_id:
                        fstate.seen_ids.add(tool_call_id)

                    _write_cieu(
                        tool_name=tool_call["tool_name"],
                        tool_input=tool_call["tool_input"],
                        session_file=session_file,
                        agent_id=agent_id,
                    )

        state.cleanup_missing()
        _stop_event.wait(POLL_INTERVAL)

    _log.info("k9log openclaw_watcher: stopped")


# ── Public API ────────────────────────────────────────────────────────────────

_watcher_thread: Optional[threading.Thread] = None


def start_watcher(background: bool = True) -> None:
    """
    Start the OpenClaw session watcher.

    Args:
        background: If True (default), runs in a daemon thread.
                    If False, blocks until stop_watcher() is called.
    """
    global _watcher_thread

    if _watcher_thread and _watcher_thread.is_alive():
        _log.info("k9log openclaw_watcher: already running")
        return

    _stop_event.clear()

    if background:
        _watcher_thread = threading.Thread(
            target=_watcher_loop,
            name="k9log-openclaw-watcher",
            daemon=True,
        )
        _watcher_thread.start()
        _log.info("k9log openclaw_watcher: started in background thread")
        print("✅ K9Audit OpenClaw watcher started — monitoring all skill calls")
        print(f"   Watching: {OPENCLAW_DIR / 'agents/*/sessions/*.jsonl'}")
        print("   Constraints: auto-loaded from AGENTS.md")
        print("   Run 'k9log stats' to see audit results\n")
    else:
        _watcher_loop()


def stop_watcher() -> None:
    """Stop the OpenClaw session watcher."""
    _stop_event.set()
    if _watcher_thread:
        _watcher_thread.join(timeout=3.0)
    print("✅ K9Audit OpenClaw watcher stopped")


def watcher_status() -> dict:
    """Return watcher status dict."""
    running = bool(_watcher_thread and _watcher_thread.is_alive())
    session_count = len(list(OPENCLAW_DIR.glob(SESSIONS_GLOB))) if OPENCLAW_DIR.exists() else 0
    return {
        "running":       running,
        "session_files": session_count,
        "watching":      str(OPENCLAW_DIR / SESSIONS_GLOB),
    }


# ── Standalone process entry point ───────────────────────────────────────────
# Called by: k9log openclaw-watch start (via CLI)
# Also called by setup.sh via: python -m k9log.openclaw_watcher

def main() -> None:
    """Run watcher as a standalone process (for daemon mode)."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [k9-watcher] %(message)s")

    # Write PID file
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))

    def _handle_sigterm(signum, frame):
        _log.info("Received SIGTERM, stopping watcher")
        stop_watcher()
        PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT,  _handle_sigterm)

    print(f"[K9Audit] OpenClaw watcher running (pid={os.getpid()})")
    print(f"[K9Audit] Watching: {OPENCLAW_DIR / SESSIONS_GLOB}")
    print("[K9Audit] Press Ctrl+C to stop\n")

    # Run in foreground (blocking)
    start_watcher(background=False)


if __name__ == "__main__":
    main()
