"""
Action class registry for the Constitutional governance layer.
Maps action class names to risk/irreversible metadata.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Dict


class ActionClass(str, Enum):
    READ     = "READ"
    WRITE    = "WRITE"
    DELETE   = "DELETE"
    EXECUTE  = "EXECUTE"
    NETWORK  = "NETWORK"
    TRANSFER = "TRANSFER"
    ADMIN    = "ADMIN"


class RiskLevel(str, Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class ActionMeta:
    risk:           RiskLevel
    irreversible:   bool
    grant_required: bool
    description:    str


# Registry — mirrors policy_packs/v0.5/action_code.md
ACTION_REGISTRY: Dict[ActionClass, ActionMeta] = {
    ActionClass.READ:     ActionMeta(RiskLevel.LOW,      False, False, "Read-only data access"),
    ActionClass.WRITE:    ActionMeta(RiskLevel.MEDIUM,   False, True,  "Write/create data"),
    ActionClass.DELETE:   ActionMeta(RiskLevel.HIGH,     True,  True,  "Permanent deletion"),
    ActionClass.EXECUTE:  ActionMeta(RiskLevel.HIGH,     False, True,  "Shell commands / code execution"),
    ActionClass.NETWORK:  ActionMeta(RiskLevel.MEDIUM,   False, True,  "External network calls"),
    ActionClass.TRANSFER: ActionMeta(RiskLevel.HIGH,     True,  True,  "Move money/tokens/ownership"),
    ActionClass.ADMIN:    ActionMeta(RiskLevel.CRITICAL, True,  True,  "Privilege escalation / policy changes"),
}


def get_meta(action_class: str) -> ActionMeta:
    """Return metadata for a given action class string. Raises KeyError if unknown."""
    return ACTION_REGISTRY[ActionClass(action_class)]


def is_grant_required(action_class: str) -> bool:
    try:
        return get_meta(action_class).grant_required
    except (KeyError, ValueError):
        return True  # Unknown class => require grant (safe default)


def is_irreversible(action_class: str) -> bool:
    try:
        return get_meta(action_class).irreversible
    except (KeyError, ValueError):
        return True  # Unknown class => treat as irreversible (safe default)

