# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
# AGPL-3.0
"""
K9log Contract Builder
======================
Simplifies Y*_t intent contract definition with:

1. Simple alias parameters for @k9 decorator:
   @k9(deny=[".env"], only_paths=["./projects/"], deny_commands=["rm -rf"])
   instead of the verbose nested dict format.

2. Auto-prefill from 4 deterministic sources (zero LLM):
   - Source 1: AGENTS.md pattern matcher
   - Source 2: AST analysis of the function
   - Source 3: Local CIEU history statistics
   - Source 4: Built-in security pattern library

3. Interactive fill-in-the-blank template (CLI):
   k9log contract add my_function

4. Bidirectional projection:
   Natural language template ↔ @k9 params ↔ Y*_t JSON ↔ SHA256

All 8 dimensions:
  deny          → deny_content (substring blocklist)
  only_paths    → allowed_paths (path whitelist)
  deny_commands → command.blocklist
  only_domains  → allowed_domains (domain whitelist)
  value_range   → param.max / param.min
  field_deny    → param.blocklist
  postcondition → postcondition (return value assertion)
  invariant     → invariant (param assertion)
"""
from __future__ import annotations

import ast
import json
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Security pattern library (Source 4) ──────────────────────────────────────
# Deterministic, zero LLM, built from OWASP/CWE/CVE public knowledge

SECURITY_PATTERNS = {
    # Parameter name patterns → suggested constraints
    "path_params": {
        "keywords": ["path", "file", "dir", "folder", "filepath", "filename", "dest", "src"],
        "deny": ["/etc/", "/sys/", "/proc/", "../", "~root"],
        "dimension": "deny",
    },
    "url_params": {
        "keywords": ["url", "endpoint", "uri", "href", "host", "domain", "address"],
        "deny": ["192.168.", "10.", "127.0.0.1", "localhost", "169.254.", "0.0.0.0"],
        "dimension": "deny",
    },
    "command_params": {
        "keywords": ["command", "cmd", "shell", "exec", "run", "script"],
        "deny_commands": ["rm -rf", "sudo", "chmod 777", "dd if=", "| bash", "| sh",
                          "mkfs", "fdisk", "> /dev/"],
        "dimension": "deny_commands",
    },
    "secret_params": {
        "keywords": ["secret", "password", "passwd", "token", "key", "credential",
                     "auth", "api_key", "private"],
        "deny": [".env", ".secret", "credentials", "id_rsa", ".pem"],
        "dimension": "deny",
    },
    "amount_params": {
        "keywords": ["amount", "price", "cost", "fee", "balance", "quantity", "count", "total", "sum", "payment", "charge", "budget", "funds", "transfer", "money"],
        "invariant": ["value > 0", "value < 1000000"],
        "dimension": "invariant",
    },
    "env_params": {
        "keywords": ["environment", "env", "target_env", "deploy_env", "stage"],
        "field_deny": ["production", "prod", "live"],
        "dimension": "field_deny",
    },
}

# Built-in deny patterns always worth suggesting for certain function name patterns
FUNCTION_NAME_PATTERNS = {
    "deploy": {
        "deny": [".env", "credentials", "production", "prod"],
        "deny_commands": ["rm -rf", "sudo"],
    },
    "write": {
        "deny": ["/etc/", "/sys/", ".env", "../", "../../"],
    },
    "execute": {
        "deny_commands": ["rm -rf", "sudo", "| bash"],
    },
    "fetch": {
        "deny": ["192.168.", "localhost", "127.0.0.1"],
    },
    "delete": {
        "deny_commands": ["rm -rf"],
        "postcondition": [],
    },
    "transfer": {"deny": ["production", "prod"]},
    "payment":  {"deny": ["production", "prod"]},
    "fund":     {},
    "charge":   {"deny": ["production", "prod"]},
}


# ── Source 2: AST analysis ────────────────────────────────────────────────────

def _analyze_function_ast(func) -> Dict[str, List]:
    """
    Analyze function source via AST to suggest constraints.
    Deterministic, zero LLM.
    """
    suggestions: Dict[str, List] = {
        "deny": [], "only_paths": [], "deny_commands": [],
        "only_domains": [], "invariant": [], "postcondition": [],
        "field_deny": [], "value_range": {},
    }

    try:
        import inspect, textwrap
        source = textwrap.dedent(inspect.getsource(func))
        tree = ast.parse(source)
    except Exception:
        return suggestions

    # Analyze parameter names
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for arg in node.args.args:
                name = arg.arg.lower()
                for pattern_name, pattern in SECURITY_PATTERNS.items():
                    if any(kw in name for kw in pattern["keywords"]):
                        dim = pattern["dimension"]
                        if dim == "deny":
                            for v in pattern.get("deny", []):
                                if v not in suggestions["deny"]:
                                    suggestions["deny"].append(v)
                        elif dim == "deny_commands":
                            for v in pattern.get("deny_commands", []):
                                if v not in suggestions["deny_commands"]:
                                    suggestions["deny_commands"].append(v)
                        elif dim == "invariant":
                            for v in pattern.get("invariant", []):
                                inv = v.replace("value", arg.arg)
                                if inv not in suggestions["invariant"]:
                                    suggestions["invariant"].append(inv)
                        elif dim == "field_deny":
                            for v in pattern.get("field_deny", []):
                                if v not in suggestions["field_deny"]:
                                    suggestions["field_deny"].append(v)

    # Analyze function name
    func_name = getattr(func, "__name__", "").lower()
    for fn_pattern, fn_constraints in FUNCTION_NAME_PATTERNS.items():
        if fn_pattern in func_name:
            for dim, values in fn_constraints.items():
                if isinstance(values, list):
                    for v in values:
                        if v not in suggestions.get(dim, []):
                            suggestions.setdefault(dim, []).append(v)

    # Detect open() calls → suggest allowed_paths
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                if not suggestions["only_paths"]:
                    suggestions["only_paths"].append("./")

    # Detect requests/httpx calls → suggest only_domains
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (node.attr in ("get", "post", "put", "delete", "request") and
                    isinstance(node.value, ast.Name) and
                    node.value.id in ("requests", "httpx", "urllib", "aiohttp")):
                if not suggestions["deny"]:
                    suggestions["deny"].extend(["192.168.", "localhost", "127.0.0.1"])

    return suggestions


# ── Source 3: CIEU history statistics ────────────────────────────────────────

def _analyze_cieu_history(func_name: str,
                           ledger_path: Optional[Path] = None) -> Dict[str, List]:
    """
    Extract constraint suggestions from local CIEU history.
    Purely statistical, zero LLM.
    """
    suggestions: Dict[str, Any] = {
        "deny": [], "only_paths": [], "deny_commands": [],
        "only_domains": [], "violations": [],
    }

    if ledger_path is None:
        ledger_path = Path.home() / ".k9log" / "logs" / "k9log.cieu.jsonl"

    if not ledger_path.exists():
        return suggestions

    # Read CIEU records for this function
    path_counts: Dict[str, int] = {}
    domain_counts: Dict[str, int] = {}
    violation_patterns: Dict[str, int] = {}

    try:
        lines = ledger_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-5000:]:  # Last 5000 records only
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                skill = record.get("U_t", {}).get("skill", "")
                if func_name and func_name not in skill:
                    continue

                params = record.get("U_t", {}).get("params", {})
                violations = record.get("R_t+1", {}).get("violations", [])

                # Count actual param values
                for k, v in params.items():
                    if not isinstance(v, str):
                        continue
                    # Path-like values
                    if "/" in v or "\\" in v:
                        clean = v.split("?")[0].split("#")[0]
                        path_counts[clean] = path_counts.get(clean, 0) + 1
                    # Domain-like values
                    if "://" in v:
                        try:
                            from urllib.parse import urlparse
                            domain = urlparse(v).hostname or ""
                            if domain:
                                domain_counts[domain] = domain_counts.get(domain, 0) + 1
                        except Exception:
                            pass

                # Count violation patterns
                for viol in violations:
                    vtype = viol.get("type", "")
                    violation_patterns[vtype] = violation_patterns.get(vtype, 0) + 1

            except Exception:
                continue

    except Exception:
        return suggestions

    # Most common safe paths (never violated)
    total_calls = max(sum(path_counts.values()), 1)
    for path, count in sorted(path_counts.items(), key=lambda x: -x[1])[:5]:
        if count / total_calls > 0.1:  # Seen in >10% of calls
            suggestions["only_paths"].append(path)

    # Most common safe domains
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1])[:3]:
        suggestions["only_domains"].append(domain)

    # Violation patterns → suggest constraints
    suggestions["violations"] = [
        {"type": vtype, "count": count}
        for vtype, count in sorted(violation_patterns.items(), key=lambda x: -x[1])
    ]

    return suggestions


# ── Source 1: AGENTS.md ───────────────────────────────────────────────────────

def _load_agents_md_suggestions() -> Dict[str, List]:
    """Load constraint suggestions from AGENTS.md (pattern matcher, zero LLM)."""
    from k9log.agents_md_parser import parse_agents_md_to_constraints
    from k9log.constraints import _find_agents_md

    paths = _find_agents_md()
    if not paths:
        return {}

    try:
        constraints = parse_agents_md_to_constraints(paths[0])
        # Map from internal format to simplified format
        return {
            "deny":          constraints.get("deny_content", []),
            "only_paths":    constraints.get("allowed_paths", []),
            "deny_commands": constraints.get("command", {}).get("blocklist", []),
            "only_domains":  constraints.get("allowed_domains", []),
        }
    except Exception:
        return {}


# ── Prefill: merge all 4 sources ─────────────────────────────────────────────

def prefill_contract(func=None, func_name: str = "") -> Dict[str, Any]:
    """
    Auto-prefill contract from all 4 deterministic sources.
    Returns merged suggestions, deduplicated.
    """
    merged: Dict[str, List] = {
        "deny": [], "only_paths": [], "deny_commands": [],
        "only_domains": [], "invariant": [], "postcondition": [],
        "field_deny": [], "value_range": {},
    }

    def _extend(key, values):
        if not isinstance(values, list):
            return
        for v in values:
            if v and v not in merged.get(key, []):
                merged.setdefault(key, []).append(v)

    # Source 4: built-in patterns (always first)
    if func_name:
        for fn_pat, fn_constraints in FUNCTION_NAME_PATTERNS.items():
            if fn_pat in func_name.lower():
                for dim, values in fn_constraints.items():
                    _extend(dim, values)


    # Source 4b: infer param names from func_name, trigger SECURITY_PATTERNS
    _inferred_param = "value"
    for kw in ["amount","price","cost","fee","balance","quantity","total","sum","payment","charge","budget","funds","money"]:
        if kw in func_name.lower():
            _inferred_param = kw
            break
    _inv_added = False
    for _pname, _pat in SECURITY_PATTERNS.items():
        if any(kw in func_name.lower() for kw in _pat.get("keywords",[])):
            _dim = _pat["dimension"]
            if _dim == "invariant" and not _inv_added:
                for v in _pat.get("invariant",[]):
                    inv = v.replace("value", _inferred_param)
                    if inv not in merged.get("invariant",[]):
                        merged.setdefault("invariant",[]).append(inv)
                _inv_added = True
            elif _dim == "field_deny":
                for v in _pat.get("field_deny",[]):
                    if v not in merged.get("field_deny",[]): merged.setdefault("field_deny",[]).append(v)
                    if v not in merged.get("deny",[]): merged.setdefault("deny",[]).append(v)

    # Source 1: AGENTS.md
    agents_suggestions = _load_agents_md_suggestions()
    for key, values in agents_suggestions.items():
        _extend(key, values)

    # Source 2: AST analysis
    if func is not None:
        ast_suggestions = _analyze_function_ast(func)
        for key, values in ast_suggestions.items():
            if isinstance(values, list):
                _extend(key, values)

    # Source 3: CIEU history
    name = func_name or (getattr(func, "__name__", "") if func else "")
    if name:
        history_suggestions = _analyze_cieu_history(name)
        for key, values in history_suggestions.items():
            if isinstance(values, list):
                _extend(key, values)

    return merged


# ── Alias → internal format conversion ───────────────────────────────────────

def normalize_k9_aliases(**kwargs) -> Dict[str, Any]:
    """
    Convert simplified alias params to internal constraint format.

    Alias params:
        deny          → deny_content
        only_paths    → allowed_paths
        deny_commands → command.blocklist
        only_domains  → allowed_domains
        invariant     → invariant (unchanged)
        postcondition → postcondition (unchanged)
        field_deny    → per-param blocklist
        value_range   → per-param max/min

    Legacy params (deny_content, allowed_paths, etc.) pass through unchanged.
    """
    result = {}

    # Handle aliases
    if "deny" in kwargs:
        existing = kwargs.get("deny_content", [])
        combined = list(dict.fromkeys(existing + kwargs.pop("deny")))
        result["deny_content"] = combined
    if "only_paths" in kwargs:
        result["allowed_paths"] = kwargs.pop("only_paths")
    if "deny_commands" in kwargs:
        cmds = kwargs.pop("deny_commands")
        existing_cmd = kwargs.get("command", {})
        existing_bl = existing_cmd.get("blocklist", []) if isinstance(existing_cmd, dict) else []
        result["command"] = {"blocklist": list(dict.fromkeys(existing_bl + cmds))}
    if "only_domains" in kwargs:
        result["allowed_domains"] = kwargs.pop("only_domains")

    # Pass through legacy and remaining params unchanged
    for k, v in kwargs.items():
        if k not in result:
            result[k] = v

    return result


# ── Bidirectional projection ──────────────────────────────────────────────────

def constraints_to_template(constraints: Dict[str, Any]) -> Dict[str, Any]:
    """
    Project @k9 constraints → natural language fill-in-the-blank template.
    Returns a dict where each key has a human-readable label and the values.
    """
    template = {}

    deny = constraints.get("deny_content", constraints.get("deny", []))
    if deny:
        template["禁止出现的内容"] = {"values": deny, "hint": "文件名、路径前缀、IP段等"}

    paths = constraints.get("allowed_paths", constraints.get("only_paths", []))
    if paths:
        template["只允许写入的路径"] = {"values": paths, "hint": "如 ./projects/"}

    cmds = constraints.get("command", {}).get("blocklist", [])
    if cmds:
        template["禁止运行的命令"] = {"values": cmds, "hint": "如 rm -rf, sudo"}

    domains = constraints.get("allowed_domains", constraints.get("only_domains", []))
    if domains:
        template["只允许访问的域名"] = {"values": domains, "hint": "如 api.github.com"}

    invariant = constraints.get("invariant", [])
    if invariant:
        template["参数必须满足"] = {"values": invariant, "hint": "Python 表达式，如 amount > 0"}

    postcondition = constraints.get("postcondition", [])
    if postcondition:
        template["返回值必须满足"] = {"values": postcondition,
                                     "hint": "Python 表达式，如 result['status'] == 'ok'"}

    return template


def template_to_constraints(template: Dict[str, Any]) -> Dict[str, Any]:
    """
    Project natural language template → @k9 constraints dict.
    Inverse of constraints_to_template.
    """
    constraints = {}

    label_map = {
        "禁止出现的内容":   "deny_content",
        "只允许写入的路径": "allowed_paths",
        "只允许访问的域名": "allowed_domains",
        "参数必须满足":     "invariant",
        "返回值必须满足":   "postcondition",
    }

    for label, data in template.items():
        values = data["values"] if isinstance(data, dict) else data
        if not values:
            continue
        if label == "禁止运行的命令":
            constraints["command"] = {"blocklist": values}
        elif label in label_map:
            constraints[label_map[label]] = values

    return constraints


def hash_constraints(constraints: Dict[str, Any]) -> str:
    """SHA256 hash of constraints for Y*_t integrity."""
    canonical = json.dumps(constraints, sort_keys=True, ensure_ascii=True)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


# ── Save to config ────────────────────────────────────────────────────────────

def save_contract(func_name: str, constraints: Dict[str, Any],
                  source: str = "contract_builder") -> Path:
    """Save verified contract to ~/.k9log/config/{func_name}.json"""
    config_dir = Path.home() / ".k9log" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    p = config_dir / f"{func_name}.json"
    p.write_text(json.dumps({
        "skill":       func_name,
        "constraints": constraints,
        "version":     "1.0.0",
        "_source":     source,
        "_hash":       hash_constraints(constraints),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


# ── Generate @k9 decorator code ───────────────────────────────────────────────

def constraints_to_k9_code(func_name: str,
                             constraints: Dict[str, Any]) -> str:
    """Generate @k9 decorator source code from constraints."""
    lines = ["@k9("]

    deny = constraints.get("deny_content", [])
    if deny:
        lines.append(f"    deny={json.dumps(deny, ensure_ascii=False)},")

    paths = constraints.get("allowed_paths", [])
    if paths:
        lines.append(f"    only_paths={json.dumps(paths, ensure_ascii=False)},")

    cmds = constraints.get("command", {}).get("blocklist", [])
    if cmds:
        lines.append(f"    deny_commands={json.dumps(cmds, ensure_ascii=False)},")

    domains = constraints.get("allowed_domains", [])
    if domains:
        lines.append(f"    only_domains={json.dumps(domains, ensure_ascii=False)},")

    inv = constraints.get("invariant", [])
    if inv:
        lines.append(f"    invariant={json.dumps(inv, ensure_ascii=False)},")

    post = constraints.get("postcondition", [])
    if post:
        lines.append(f"    postcondition={json.dumps(post, ensure_ascii=False)},")

    lines.append(f")")
    lines.append(f"def {func_name}(...):")
    lines.append(f"    ...")

    return "\n".join(lines)
