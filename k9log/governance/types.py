"""
Shared types for the Constitutional governance layer.
No dependency on k9log core modules — intentionally isolated.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

class VerdictOutcome(str, Enum):
    AUTHORIZED          = "AUTHORIZED"
    BLOCKED             = "BLOCKED"
    HARD_BLOCK          = "HARD_BLOCK"

class ViolationType(str, Enum):
    # Audit-layer violations (detected by check_compliance / CIEU assessment)
    DENY_CONTENT         = "DENY_CONTENT"
    LEARNED_RULE_HIT     = "LEARNED_RULE_HIT"
    TAINT_VIOLATION      = "taint_violation"
    # Governance-layer violations (detected by constitutional gate)
    NO_GRANT             = "NO_GRANT"
    GRANT_EXPIRED        = "GRANT_EXPIRED"
    GRANT_CLASS_MISMATCH = "GRANT_CLASS_MISMATCH"
    GRANT_SCOPE_MISMATCH = "GRANT_SCOPE_MISMATCH"
    IRREVERSIBLE_NO_AUTH = "IRREVERSIBLE_NO_AUTH"

@dataclass
class EventFacts:
    """Normalised facts extracted from an agent action (input-agnostic)."""
    domains:  List[str] = field(default_factory=list)
    paths:    List[str] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.domains or self.paths or self.commands)

@dataclass
class NormalizedEvent:
    """
    Input-agnostic representation of an agent action.
    Adapters (e.g. openclaw_adapter) are responsible for producing this.
    """
    action_class:  str
    facts:         EventFacts
    irreversible:  bool         = False
    agent_id:      Optional[str] = None
    session_id:    Optional[str] = None
    purpose_tag:   Optional[str] = None

@dataclass
class Verdict:
    """
    Output of the constitutional evaluate() function.
    Designed to be merged into R_t+1.violations by the integration layer.
    """
    outcome:              VerdictOutcome
    violation_types:      List[ViolationType] = field(default_factory=list)
    hard_block:           bool                = False
    ask_user:             bool                = False
    grant_id:             Optional[str]       = None
    action_class:         str                 = ""
    severity:             float               = 0.0
    reason:               str                 = ""
    correction_hint:      Optional[str]       = None
    allowed_alternatives: List[str]           = field(default_factory=list)

    def to_cieu_field(self, policy_id: str = "", policy_version: str = "") -> dict:
        """Serialize to the _constitutional CIEU record field."""
        return {
            "enabled":            True,
            "verdict":            self.outcome.value,
            "violation_types":    [v.value for v in self.violation_types],
            "hard_block":         self.hard_block,
            "ask_user":           self.ask_user,
            "grant_id":           self.grant_id,
            "action_class":       self.action_class,
            "severity":           self.severity,
            "reason":             self.reason,
            "correction_hint":    self.correction_hint,
            "allowed_alternatives": self.allowed_alternatives,
            "policy_version":     f"{policy_id}:{policy_version}" if policy_id else "",
        }

