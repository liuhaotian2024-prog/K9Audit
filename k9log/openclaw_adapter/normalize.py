"""
OpenClaw adapter — single normalize entry point.

normalize_openclaw(tool_name, args, result, x_t) -> NormalizedEvent

This module ONLY translates facts. It does NOT:
  - evaluate risk
  - check grants
  - make hard_block decisions
  - import anything from k9log.governance.verdict

All rule evaluation lives in k9log.governance (core), not here.
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from k9log.governance.types import NormalizedEvent, EventFacts
from k9log.openclaw_adapter.mapping import ADAPTER_ID, lookup


# ── Facts extractors ──────────────────────────────────────────────────────────

def _extract_domain(url: str) -> Optional[str]:
    """Extract hostname from a URL string. Returns None if unparseable."""
    if not url:
        return None
    try:
        if "://" not in url:
            url = "https://" + url
        host = urlparse(url).hostname
        return host.lower() if host else None
    except Exception:
        return None


def _normalize_path(raw: str) -> str:
    """Normalize a file path: forward slashes, strip trailing slash."""
    if not raw:
        return ""
    # Replace both double and single backslashes with forward slash
    import re as _re
    p = _re.sub(r'[\\/]+', '/', raw).rstrip('/')
    return p


def _extract_url_domain(args: dict) -> EventFacts:
    domains = []
    for key in ("url", "endpoint", "uri", "href", "target", "host", "domain"):
        val = args.get(key)
        if val and isinstance(val, str):
            d = _extract_domain(val)
            if d:
                domains.append(d)
                break
    return EventFacts(domains=domains)


def _extract_recipient_domain(args: dict) -> EventFacts:
    domains = []
    for key in ("recipient", "to", "email", "address", "target"):
        val = args.get(key)
        if val and isinstance(val, str):
            if "@" in val:
                domains.append(val.split("@")[-1].lower())
            else:
                d = _extract_domain(val)
                if d:
                    domains.append(d)
            break
    return EventFacts(domains=domains)


def _extract_path(args: dict) -> EventFacts:
    paths = []
    for key in ("path", "file", "filename", "filepath", "dest", "destination",
                "src", "source", "output", "input"):
        val = args.get(key)
        if val and isinstance(val, str):
            p = _normalize_path(val)
            if p:
                paths.append(p)
                break
    return EventFacts(paths=paths)


def _extract_command(args: dict) -> EventFacts:
    commands = []
    for key in ("command", "cmd", "script", "code", "tool", "program", "executable"):
        val = args.get(key)
        if val and isinstance(val, str):
            # Take first token of command string
            first_token = val.strip().split()[0] if val.strip() else val
            commands.append(first_token)
            break
    return EventFacts(commands=commands)


def _extract_transfer(args: dict) -> EventFacts:
    """For transfers: extract recipient domain + any amount context as command."""
    domains = []
    commands = []
    for key in ("recipient", "to", "destination", "address"):
        val = args.get(key)
        if val and isinstance(val, str):
            if "@" in val:
                domains.append(val.split("@")[-1].lower())
            else:
                d = _extract_domain(val)
                if d:
                    domains.append(d)
            break
    # Encode amount as command token for scope matching
    amt = args.get("amount") or args.get("value")
    if amt is not None:
        commands.append(f"amount:{amt}")
    return EventFacts(domains=domains, commands=commands)


def _extract_query_command(args: dict) -> EventFacts:
    commands = []
    for key in ("query", "q", "search", "keyword", "term"):
        val = args.get(key)
        if val and isinstance(val, str):
            commands.append(val[:64])  # cap length
            break
    return EventFacts(commands=commands)


def _extract_channel_command(args: dict) -> EventFacts:
    commands = []
    for key in ("channel", "workspace", "team", "room"):
        val = args.get(key)
        if val and isinstance(val, str):
            commands.append(val)
            break
    return EventFacts(commands=commands)


EXTRACTOR_MAP = {
    "url_to_domain":       _extract_url_domain,
    "recipient_to_domain": _extract_recipient_domain,
    "path_from_args":      _extract_path,
    "command_from_args":   _extract_command,
    "transfer_facts":      _extract_transfer,
    "query_to_command":    _extract_query_command,
    "channel_to_command":  _extract_channel_command,
}


# ── Public API ────────────────────────────────────────────────────────────────

def normalize_openclaw(
    tool_name: str,
    args: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    x_t: Optional[Dict[str, Any]] = None,
) -> NormalizedEvent:
    """
    Translate an OpenClaw tool call into a NormalizedEvent.

    Args:
        tool_name: OpenClaw tool name (e.g. "http_request", "bash")
        args:      Tool arguments dict
        result:    Tool result dict (used for enrichment, not yet)
        x_t:       CIEU X_t context dict (for agent_id / session_id)

    Returns:
        NormalizedEvent ready for k9log.governance.evaluate()
    """
    if args is None:
        args = {}
    if x_t is None:
        x_t = {}

    action_class, extractor_key = lookup(tool_name)
    extractor = EXTRACTOR_MAP.get(extractor_key, _extract_command)

    facts: EventFacts = extractor(args)

    # Irreversibility: check args explicitly or infer from action class
    irreversible = bool(
        args.get("irreversible")
        or args.get("permanent")
        or args.get("force")
        or action_class in ("DELETE", "TRANSFER", "ADMIN")
    )

    return NormalizedEvent(
        action_class=action_class,
        facts=facts,
        irreversible=irreversible,
        agent_id=x_t.get("agent_id"),
        session_id=x_t.get("session_id"),
        purpose_tag=args.get("purpose") or args.get("reason"),
    )

