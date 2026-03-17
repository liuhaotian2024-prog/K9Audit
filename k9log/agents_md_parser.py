"""
AGENTS.md / CLAUDE.md parser — converts behavioral rules into Grant objects.
Deterministic rule matching only. Zero LLM dependency.

Supported rule patterns:
  File/path constraints:
    - "only edit <dir>/ directory"       -> WRITE grant, paths allowlist
    - "only write to <path>"             -> WRITE grant, paths allowlist
    - "never modify <file>"              -> WRITE grant, paths blocklist
    - "do not modify <file>"             -> WRITE grant, paths blocklist
    - "only read files in <path>"        -> READ grant, paths allowlist
    - "never access <path>"              -> READ grant, paths blocklist
    - "do not access <path>"             -> READ grant, paths blocklist
    - "never delete <path>"              -> DELETE grant, paths blocklist
    - "do not delete <path>"             -> DELETE grant, paths blocklist

  Command constraints:
    - "never run <cmd>"                  -> EXECUTE grant, commands blocklist
    - "do not run <cmd>"                 -> EXECUTE grant, commands blocklist
    - "never install <pkg>"              -> EXECUTE grant, commands blocklist
    - "never commit [directly to] <ref>" -> EXECUTE grant, commands blocklist
    - "do not commit [directly to] <ref>"-> EXECUTE grant, commands blocklist
    - "do not modify <branch> branch"    -> EXECUTE grant, commands blocklist
    - "do not introduce new <pkg> dependencies" -> EXECUTE grant

  Network constraints:
    - "only access <domain> domain"      -> NETWORK grant, domains allowlist
    - "only call <svc> api"              -> NETWORK grant, domains allowlist
    - "never access <domain> domain"     -> NETWORK grant, domains blocklist
    - "do not make [external] network"   -> NETWORK grant, block all external
    - "never exfiltrate <data>"          -> NETWORK grant, block exfil
    - "never upload <data>"              -> NETWORK grant, block upload
    - "do not send <svc>"                -> EXECUTE grant, commands blocklist

Markdown-aware:
  Lines starting with "- ", "* ", "1. ", "## ", "**Label**: " are
  stripped of their prefix before matching — compatible with OpenClaw
  AGENTS.md and CLAUDE.md files that use markdown lists and headers.

Input:  path to AGENTS.md or CLAUDE.md
Output: List[Grant], each with source field indicating origin line number
"""
from __future__ import annotations
import re
import uuid
from pathlib import Path
from typing import List, Optional, Tuple
from k9log.governance.grants import Grant

# ── Rule patterns (deterministic, no LLM) ────────────────────────────────────
# Each entry: (regex, action_class, scope_key)
# Patterns are evaluated in order — first match wins.
# More specific patterns go first.

PATTERNS: List[Tuple[str, str, str]] = [
    # ── Branch/version control (specific "branch" keyword) ──────────────────
    (r"do not modify\s+(\S+)\s+branch",            "EXECUTE", "commands"),
    (r"never modify\s+(\S+)\s+branch",             "EXECUTE", "commands"),
    (r"never commit\s+(?:directly\s+to\s+)?(\S+)", "EXECUTE", "commands"),
    (r"do not commit\s+(?:directly\s+to\s+)?(\S+)","EXECUTE", "commands"),

    # ── Path allowlists ───────────────────────────────────────────────────────
    (r"only edit\s+(\S+)\s+director(?:y|ies)",     "WRITE",   "paths"),
    (r"only write to\s+(\S+)",                     "WRITE",   "paths"),
    (r"only read\s+files?\s+in\s+(\S+)",           "READ",    "paths"),

    # ── Path blocklists ───────────────────────────────────────────────────────
    (r"never modify\s+(\S+)",                      "WRITE",   "paths"),
    (r"do not modify\s+(\S+)",                     "WRITE",   "paths"),
    (r"never delete\s+(\S+)",                      "DELETE",  "paths"),
    (r"do not delete\s+(\S+)",                     "DELETE",  "paths"),
    (r"never access\s+(\S+)\s+director(?:y|ies)",  "READ",    "paths"),
    (r"do not access\s+(\S+)\s+director(?:y|ies)", "READ",    "paths"),
    (r"never access\s+(/\S+)",                     "READ",    "paths"),   # absolute path
    (r"do not access\s+(/\S+)",                    "READ",    "paths"),

    # ── Command blocklists ────────────────────────────────────────────────────
    (r"never run\s+(\S+)",                         "EXECUTE", "commands"),
    (r"do not run\s+(\S+)",                        "EXECUTE", "commands"),
    (r"never install\s+(\S+)",                     "EXECUTE", "commands"),
    (r"do not introduce new\s+(\S+)\s+dependenc",  "EXECUTE", "commands"),
    (r"do not send\s+(\S+)",                       "EXECUTE", "commands"),

    # ── Network allowlists ────────────────────────────────────────────────────
    (r"only access\s+(\S+)\s+domain",              "NETWORK", "domains"),
    (r"only call\s+(\S+)\s+api",                   "NETWORK", "domains"),

    # ── Network blocklists ────────────────────────────────────────────────────
    (r"never access\s+(\S+)\s+domain",             "NETWORK", "domains"),
    (r"do not make\s+(?:\S+\s+)*network",          "NETWORK", "domains"),  # no capture
    (r"never make\s+(?:\S+\s+)*network",           "NETWORK", "domains"),  # no capture
    (r"never exfiltrate\s+(\S+)",                  "NETWORK", "domains"),
    (r"never upload\s+(\S+)",                      "NETWORK", "domains"),
]


def _strip_markdown_prefix(line: str) -> str:
    """
    Strip markdown list and header prefixes so rules inside lists/headers
    are matched correctly.

    Examples stripped:
      "- rule"       -> "rule"
      "* rule"       -> "rule"
      "+ rule"       -> "rule"
      "1. rule"      -> "rule"
      "## rule"      -> "rule"
      "**Label**: rule" -> "rule"
    """
    s = line
    # Numbered list: "1. ", "10. "
    s = re.sub(r'^\s*\d+\.\s+', '', s)
    # Unordered list: "- ", "* ", "+ "
    s = re.sub(r'^\s*[-*+]\s+', '', s)
    # Markdown headers: "# ", "## ", etc.
    s = re.sub(r'^\s*#{1,6}\s+', '', s)
    # Bold label prefix: "**Security**: " or "**Rule**:"
    s = re.sub(r'^\s*\*\*[^*]+\*\*:\s*', '', s)
    return s


def _parse_line(line: str, line_no: int) -> Optional[Grant]:
    """
    Try to match a single line against all known patterns.
    Returns a Grant on match, None otherwise.
    """
    # Strip markdown formatting before matching
    cleaned = _strip_markdown_prefix(line)
    stripped = cleaned.strip().rstrip(".").lower()

    if not stripped or stripped.startswith("#"):
        return None

    for pattern, action_class, scope_key in PATTERNS:
        m = re.search(pattern, stripped)
        if m:
            # Some patterns have no capture group (e.g. "do not make network requests")
            try:
                value = m.group(1).strip("`\"'")
                # Skip English articles — re-capture next token
                if value.lower() in ("the", "a", "an", "any", "all", "my"):
                    # Try to get the next word from the match position
                    rest = stripped[m.end():].strip().split()
                    value = rest[0].rstrip(".,;:") if rest else value
            except IndexError:
                value = "external"

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
    Parse AGENTS.md, CLAUDE.md, or any compatible markdown rules file
    into a list of Grant objects.

    Supports:
      - Plain rule lines
      - Markdown list items ("- rule", "* rule", "1. rule")
      - Header sections ("## Security Rules")
      - Bold-label prefixes ("**Never**: do not run sudo")

    Non-matching lines are silently skipped.
    Each grant carries a correction.inherited_from field with source line number.

    Args:
        filepath: Path to AGENTS.md, CLAUDE.md, or equivalent file.

    Returns:
        List of Grant objects parsed from the file.
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


def parse_agents_md_to_constraints(filepath: str | Path) -> dict:
    """
    Parse AGENTS.md into a K9Audit constraints dict suitable for
    passing directly to @k9() or saving as ~/.k9log/config/{skill}.json.

    Returns a constraints dict with deny_content, allowed_paths, and
    blocklist entries derived from the AGENTS.md rules.

    Example output:
        {
            "deny_content": ["staging.internal"],
            "allowed_paths": ["/home/user/projects/"],
            "command": {"blocklist": ["rm", "sudo"]},
        }
    """
    grants = parse_agents_md(filepath)
    constraints: dict = {}

    for grant in grants:
        action_class = grant.allowed_action_classes[0] if grant.allowed_action_classes else ""
        scope = grant.scope

        if action_class == "WRITE" and "paths" in scope:
            paths = scope["paths"]
            if "only" in grant.reason.lower():
                constraints.setdefault("allowed_paths", []).extend(paths)
            else:
                constraints.setdefault("deny_content", []).extend(paths)

        elif action_class == "EXECUTE" and "commands" in scope:
            cmds = scope["commands"]
            constraints.setdefault("command", {}).setdefault("blocklist", []).extend(cmds)

        elif action_class == "NETWORK" and "domains" in scope:
            domains = scope["domains"]
            if "only" in grant.reason.lower():
                constraints.setdefault("allowed_domains", []).extend(domains)
            else:
                constraints.setdefault("deny_content", []).extend(domains)

        elif action_class == "DELETE" and "paths" in scope:
            paths = scope["paths"]
            constraints.setdefault("deny_content", []).extend(paths)

        elif action_class == "READ" and "paths" in scope:
            paths = scope["paths"]
            if "only" in grant.reason.lower():
                constraints.setdefault("allowed_paths", []).extend(paths)
            else:
                constraints.setdefault("deny_content", []).extend(paths)

    # Deduplicate
    for key in ("deny_content", "allowed_paths", "allowed_domains"):
        if key in constraints:
            constraints[key] = list(dict.fromkeys(constraints[key]))

    return constraints
