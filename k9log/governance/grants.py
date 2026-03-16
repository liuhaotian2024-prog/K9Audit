# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
# AGPL-3.0
"""
K9log Governance — Grant data model

A Grant is a scoped authorisation issued to an agent for a specific
action class and set of resources. Grants are the mechanism by which
K9 Audit expresses the Y*_t intent contract at the governance layer —
what the agent is permitted to do, who issued the permission, and
when it expires.

Grants are produced by:
  - parse_agents_md()   — parsed from AGENTS.md / CLAUDE.md rules
  - k9log task start    — CLI issues a session-scoped grant
  - metalearning engine — suggests grants from incident history

Grants are consumed by:
  - constitutional gate  — evaluates whether an action is authorised
  - k9log grants list    — CLI display
  - k9log grants export  — serialise to JSON for sharing

Grant files are stored at:
  ~/.k9log/grants/<grant_id>.json         — active grants
  ~/.k9log/grants/suggested/<grant_id>.json — suggested, pending approval
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Grant:
    """
    A scoped authorisation record for an AI agent action.

    Fields
    ------
    grant_id              : Unique identifier (UUID-derived)
    issuer                : Who issued this grant (e.g. "AGENTS.md", "cli", "metalearning")
    allowed_action_classes: List of ActionClass strings this grant covers (READ/WRITE/EXECUTE/...)
    scope                 : Dict of resource constraints — paths, commands, domains, etc.
    expires_at            : ISO-8601 UTC string, or None for session-scoped (no expiry)
    reason                : Human-readable description of why this grant exists
    agent_id              : Optional — restricts grant to a specific agent identity
    session_id            : Optional — restricts grant to a specific session
    correction            : Optional — metadata from metalearning or source provenance
    """
    grant_id:               str
    issuer:                 str
    allowed_action_classes: List[str]
    scope:                  Dict[str, Any]
    expires_at:             Optional[str]
    reason:                 str
    agent_id:               Optional[str]             = None
    session_id:             Optional[str]             = None
    correction:             Optional[Dict[str, Any]]  = field(default=None)

    # -- Constructors ----------------------------------------------------------

    @classmethod
    def new(
        cls,
        issuer: str,
        allowed_action_classes: List[str],
        scope: Dict[str, Any],
        reason: str,
        expires_at: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        correction: Optional[Dict[str, Any]] = None,
    ) -> "Grant":
        """Create a new Grant with an auto-generated ID."""
        return cls(
            grant_id=f"grant-{uuid.uuid4().hex[:12]}",
            issuer=issuer,
            allowed_action_classes=allowed_action_classes,
            scope=scope,
            expires_at=expires_at,
            reason=reason,
            agent_id=agent_id,
            session_id=session_id,
            correction=correction,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Grant":
        """Deserialise a Grant from a plain dict (e.g. loaded from JSON)."""
        return cls(
            grant_id=data.get("grant_id", f"grant-{uuid.uuid4().hex[:12]}"),
            issuer=data.get("issuer", "unknown"),
            allowed_action_classes=data.get("allowed_action_classes", []),
            scope=data.get("scope", {}),
            expires_at=data.get("expires_at"),
            reason=data.get("reason", ""),
            agent_id=data.get("agent_id"),
            session_id=data.get("session_id"),
            correction=data.get("correction"),
        )

    @classmethod
    def from_json_file(cls, path: Path) -> "Grant":
        """Load a Grant from a JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    # -- Serialisation ---------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict (JSON-safe)."""
        return asdict(self)

    def save(self, directory: Path, suggested: bool = False) -> Path:
        """Write this grant to disk."""
        target_dir = directory / "suggested" if suggested else directory
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{self.grant_id}.json"
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    # -- Validity checks -------------------------------------------------------

    def is_expired(self) -> bool:
        """Return True if this grant has a non-None expires_at that is in the past."""
        if self.expires_at is None:
            return False
        try:
            expiry = datetime.fromisoformat(self.expires_at)
            now = datetime.now(timezone.utc)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            return now > expiry
        except (ValueError, TypeError):
            return False

    def covers_action_class(self, action_class: str) -> bool:
        """Return True if this grant covers the given ActionClass string."""
        return action_class in self.allowed_action_classes

    def covers_path(self, path: str) -> bool:
        """Return True if the given file path is within this grant's path scope."""
        import fnmatch
        allowed = self.scope.get("paths", [])
        if not allowed:
            return True
        for pattern in allowed:
            if fnmatch.fnmatch(path, pattern):
                return True
            if "*" not in pattern and path.startswith(pattern.rstrip("/")):
                return True
        return False

    def covers_domain(self, domain: str) -> bool:
        """Return True if the domain is within this grant's domain scope."""
        allowed = self.scope.get("domains", [])
        if not allowed:
            return True
        return any(domain == d or domain.endswith("." + d) for d in allowed)

    def __repr__(self) -> str:
        expiry = f" expires={self.expires_at}" if self.expires_at else " (no expiry)"
        return (
            f"Grant(id={self.grant_id!r}, "
            f"issuer={self.issuer!r}, "
            f"classes={self.allowed_action_classes}{expiry})"
        )


# -- Directory helpers ---------------------------------------------------------

_GRANTS_DIR = Path.home() / ".k9log" / "grants"


def load_active_grants(grants_dir: Optional[Path] = None) -> List[Grant]:
    """Load all active (non-suggested) grants from disk."""
    d = grants_dir or _GRANTS_DIR
    if not d.exists():
        return []
    grants: List[Grant] = []
    for p in d.glob("*.json"):
        try:
            g = Grant.from_json_file(p)
            if not g.is_expired():
                grants.append(g)
        except Exception:
            pass
    return grants


def load_suggested_grants(grants_dir: Optional[Path] = None) -> List[Grant]:
    """Load all suggested (pending approval) grants from disk."""
    d = (grants_dir or _GRANTS_DIR) / "suggested"
    if not d.exists():
        return []
    grants: List[Grant] = []
    for p in d.glob("*.json"):
        try:
            grants.append(Grant.from_json_file(p))
        except Exception:
            pass
    return grants
