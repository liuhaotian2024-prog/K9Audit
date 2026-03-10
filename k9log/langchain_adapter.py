# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
# AGPL-3.0
import time
import logging
from typing import Any, Dict, List, Optional, Union
from uuid import UUID
from k9log.core import get_logger
from k9log.identity import get_agent_identity
from k9log.constraints import load_constraints

_log = logging.getLogger("k9log")

try:
    from langchain_core.callbacks.base import BaseCallbackHandler
    _LANGCHAIN_AVAILABLE = True
except ImportError:
    try:
        from langchain.callbacks.base import BaseCallbackHandler
        _LANGCHAIN_AVAILABLE = True
    except ImportError:
        _LANGCHAIN_AVAILABLE = False
        class BaseCallbackHandler:
            pass

if not _LANGCHAIN_AVAILABLE:
    _log.warning("k9log: langchain not installed")


class K9CallbackHandler(BaseCallbackHandler):
    """LangChain callback handler writing CIEU records to K9log Ledger.
    on_tool_start: pre-execution constraint check + opens record
    on_tool_end:   closes with actual output (passed=True)
    on_tool_error: closes with error (passed=False)
    Thread-safe: each run_id has its own pending slot.
    """

    def __init__(self, agent_name=None, agent_type=None):
        super().__init__()
        self._agent_name = agent_name
        self._agent_type = agent_type
        self._pending = {}

    def on_tool_start(self, serialized, input_str, *, run_id,
                      parent_run_id=None, tags=None, metadata=None, **kwargs):
        tool_name = serialized.get("name", "unknown_tool")
        t0 = __import__("time").time()
        # Generate tool_use_id for Pre+OUTCOME merge in causal chain
        import uuid
        tool_use_id = str(uuid.uuid4())
        identity = get_agent_identity() or {}
        x_t = {
            "agent_name": self._agent_name or identity.get("agent_name", "langchain_agent"),
            "agent_id":   identity.get("agent_id"),
            "agent_type": self._agent_type or identity.get("agent_type", "langchain"),
            "run_id":     str(run_id),
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "tags":       tags or [],
            "metadata":   metadata or {},
        }
        u_t = {"skill": tool_name, "skill_module": "langchain", "params": {"input": input_str}}
        y_star = load_constraints(tool_name, {})
        constraints = y_star.get("constraints", {})
        violations = self._check_violations(input_str, constraints)
        passed = not violations
        severity = max((v.get("severity", 0.5) for v in violations), default=0.0)
        record = {
            "event_type": "PreToolUse",
            "X_t": {**x_t, "tool_use_id": tool_use_id},
            "U_t": u_t, "Y_star_t": y_star,
            "Y_t+1": {"status": "pending", "output": None},
            "R_t+1": {"passed": passed, "violations": violations,
                      "overall_severity": severity,
                      "risk_level": self._risk(severity),
                      "phase": "pre_execution"},
            "_t0": t0,
            "_tool_use_id": tool_use_id,
        }
        self._pending[str(run_id)] = record
        if not passed:
            _log.warning("k9log [%s] pre-execution violation: %s",
                         tool_name, "; ".join(v["message"] for v in violations))
            self._fire_alert(record)


    def on_tool_end(self, output, *, run_id, parent_run_id=None, **kwargs):
        record = self._pending.pop(str(run_id), None)
        if record is None: return
        duration = time.time() - record.pop("_t0", time.time())
        tool_use_id = record.pop("_tool_use_id", "")
        record["Y_t+1"] = {"status": "success", "output": output[:2000]}
        record["R_t+1"]["duration_sec"] = duration
        record["R_t+1"]["phase"] = "post_execution"
        self._write(record)
        if tool_use_id:
            self._update_outcome(tool_use_id, {
                "exit_code": 0, "stdout": output[:2000],
                "stderr": "", "error": "", "duration_sec": duration,
            })

    def on_tool_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        record = self._pending.pop(str(run_id), None)
        if record is None: return
        duration = time.time() - record.pop("_t0", time.time())
        tool_use_id = record.pop("_tool_use_id", "")
        record["Y_t+1"] = {"status": "error", "error": str(error)}
        record["R_t+1"]["passed"] = False
        record["R_t+1"]["duration_sec"] = duration
        record["R_t+1"]["phase"] = "post_execution"
        if not any(v["type"] == "TOOL_ERROR" for v in record["R_t+1"]["violations"]):
            record["R_t+1"]["violations"].append(
                {"type": "TOOL_ERROR", "message": str(error), "severity": 0.6})
        self._write(record)
        if tool_use_id:
            self._update_outcome(tool_use_id, {
                "exit_code": 1, "stdout": "", "stderr": str(error),
                "error": str(error), "duration_sec": duration,
            })

    def _update_outcome(self, tool_use_id, outcome):
        try:
            from k9log.logger import get_logger
            get_logger().update_outcome(tool_use_id, outcome)
        except Exception:
            pass

    def _check_violations(self, input_str, constraints):
        import re
        violations = []
        for pattern in constraints.get("deny_content", []):
            if pattern.lower() in input_str.lower():
                violations.append({"type": "DENY_CONTENT", "pattern": pattern,
                    "found_in": input_str[:120], "severity": 0.9,
                    "message": f"Input contains forbidden pattern: {repr(pattern)}"})
        allowed = constraints.get("allowed_paths", [])
        if allowed:
            from k9log.hook import path_allowed
            for path in re.findall(r"[\w./\\-]+\.[\w]+", input_str):
                if not path_allowed(path, allowed):
                    violations.append({"type": "PATH_VIOLATION", "path": path,
                        "allowed": allowed, "severity": 0.7,
                        "message": f"Path {repr(path)} outside allowed directories"})
        return violations

    def _risk(self, severity):
        if severity >= 0.9: return "CRITICAL"
        if severity >= 0.7: return "HIGH"
        if severity >= 0.4: return "MEDIUM"
        return "LOW"

    def _write(self, record):
        from datetime import datetime, timezone
        try:
            cieu = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "X_t":       record["X_t"],
                "U_t":       record["U_t"],
                "Y_star_t":  record["Y_star_t"],
                "Y_t+1":     record["Y_t+1"],
                "R_t+1":     record["R_t+1"],
            }
            get_logger().write_cieu(cieu)
        except Exception as e:
            _log.error("k9log: failed to write CIEU record: %s", e)

    def _update_outcome(self, tool_use_id, outcome):
        """Call core update_outcome for causal chain merge."""
        try:
            from k9log.logger import get_logger
            get_logger().update_outcome(tool_use_id, outcome)
        except Exception:
            pass

    def _fire_alert(self, record):
        try:
            from k9log.alerting import get_alert_manager
            get_alert_manager().on_violation(record)
        except Exception:
            pass