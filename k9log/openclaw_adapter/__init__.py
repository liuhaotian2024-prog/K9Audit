"""
k9log.openclaw_adapter — OpenClaw tool call → NormalizedEvent translator.

This adapter is a SWAPPABLE TRANSLATOR. It does not contain governance rules.
Laws live in k9log.governance (core). Evidence stays stable regardless of adapter version.

Public API:
    from k9log.openclaw_adapter import normalize_openclaw, ADAPTER_ID
"""
from k9log.openclaw_adapter.normalize import normalize_openclaw
from k9log.openclaw_adapter.mapping import ADAPTER_ID

__all__ = ["normalize_openclaw", "ADAPTER_ID"]

