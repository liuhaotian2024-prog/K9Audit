"""
AGENTS.md / CLAUDE.md parser — converts behavioral rules into Grant objects.
Deterministic rule matching only. Zero LLM dependency.
Supported rule patterns:
  - "do not modify <branch> branch"  -> EXECUTE grant, commands excludelist
  - "only edit <dir>/ directory"     -> WRITE grant, paths allowlist
  - "do not introduce new <pkg> dependencies" -> EXECUTE grant, commands blocklist
  - "never run <cmd>"                -> EXECUTE grant, commands blocklist
  - "only access <domain>"           -> NETWORK grant, domains allowlist
Input:  path to AGENTS.md or CLAUDE.md
Output: List[Grant], each with source field indicating origin line number
"""
from __future__ import annotations
import re
import uuid
from pathlib import Path
from typing import List, Optional, Tuple
from k9log.governance.grants import Grant

# ── Rule patterns (deterministic, no LLM) ──────────────────────────────────

PATTERNS: List[Tuple[str, str, str]] = [
    # (regex, action_class, scope_key)
    (r"do not modify\s+(\S+)\s+branch",          "EXECUTE",  "commands"),
    (r"never modify\s+(\S+)\s+branch",            "EXECUTE",  "commands"),
    (r"only edit\s+(\S+)\s+director(?:y|ies)",    "WRITE",    "paths"),
    (r"only write to\s+(\S+)",                    "WRITE",    "paths"),
    (r"do not introduce new\s+(\S+)\s+dependenc", "EXECUTE",  "commands"),
    (r"never install\s+(\S+)",                    "EXECUTE",  "commands"),
    (r"never run\s+(\S+)",                        "EXECUTE",  "commands"),
    (r"do not run\s+(\S+)",                       "EXECUTE",  "commands"),
    (r"only access\s+(\S+)\s+domain",             "NETWORK",  "domains"),
    (r"only call\s+(\S+)\s+api",                  "NETWORK",  "domains"),
]

def _parse_line(line: str, line_no: int) -> Optional[Grant]:
    """Try to match a single line against all known patterns."""
    stripped = line.strip().rstrip(".").lower()
    if not stripped or stripped.startswith("#"):
        return None

    for pattern, action_class, scope_key in PATTERNS:
        m = re.search(pattern, stripped)
        if m:
            value = m.group(1).strip("`\"'")
            return Grant(
                grant_id=f"agents-md-{uuid.uuid4().hex[:8]}",
                issuer="AGENTS.md",
                allowed_action_classes=[action_class],
                scope={scope_key: [value]},
                expires_at=None,
                reason=line.strip(),
                agent_id=None,
                session_id=None,
                correction={"inherited_from": f"AGENTS.md:line-{line_no}"},
            )
    return None

def parse_agents_md(filepath: str | Path) -> List[Grant]:
    """
    Parse AGENTS.md or CLAUDE.md into a list of Grant objects.
    Each grant carries a correction.inherited_from field with source line number.
    Non-matching lines are silently skipped.
    """
    path = Path(filepath)
    if not path.exists():
        return []

    grants: List[Grant] = []
    lines = path.read_text(encoding="utf-8").splitlines()

    for i, line in enumerate(lines, start=1):
        grant = _parse_line(line, i)
        if grant:
            grants.append(grant)

    return grants

