"""
k9log.governance — type definitions and action classification for CIEU audit.

This package provides the foundational types used in CIEU records:
  - ActionClass: classifies what kind of action was taken (READ/WRITE/EXECUTE/...)
  - ViolationType: classifies what kind of deviation was detected
  - NormalizedEvent / Verdict: data structures for audit assessment

Note: enforcement and verdict evaluation (verdict.py, grants.py,
constitutional_gate.py) are part of the governance enforcement layer
and are not included in the K9 Audit open-source core.
"""
from k9log.governance.types import (
    VerdictOutcome,
    ViolationType,
    EventFacts,
    NormalizedEvent,
    Verdict,
)
from k9log.governance.action_class import ActionClass, RiskLevel, ActionMeta, get_meta

__all__ = [
    "VerdictOutcome",
    "ViolationType",
    "EventFacts",
    "NormalizedEvent",
    "Verdict",
    "ActionClass",
    "RiskLevel",
    "ActionMeta",
    "get_meta",
]
