"""
OpenClaw tool → ActionClass + facts extraction rules.

This is a DETERMINISTIC LOOKUP TABLE, not scattered if/else.
Changing a mapping = one-line diff here + update golden tests.

Rule format:
    key:   tool_name pattern (exact match first, then prefix, then keyword)
    value: (action_class, facts_extractor_key)

facts_extractor_key tells normalize.py which extractor to use for facts.
"""
from __future__ import annotations

ADAPTER_ID = "openclaw/v1"

# ── Tool → (action_class, facts_extractor) ───────────────────────────────────
# Exact match table (checked first, O(1))
EXACT: dict[str, tuple[str, str]] = {
    # Network
    "http_request":       ("NETWORK",  "url_to_domain"),
    "web_fetch":          ("NETWORK",  "url_to_domain"),
    "web_search":         ("NETWORK",  "query_to_command"),
    "send_message":       ("NETWORK",  "recipient_to_domain"),
    "webhook":            ("NETWORK",  "url_to_domain"),
    "api_call":           ("NETWORK",  "url_to_domain"),
    "send_email":         ("NETWORK",  "recipient_to_domain"),
    "slack_post":         ("NETWORK",  "channel_to_command"),
    # File write
    "file_write":         ("WRITE",    "path_from_args"),
    "write_file":         ("WRITE",    "path_from_args"),
    "file_create":        ("WRITE",    "path_from_args"),
    "upload_file":        ("WRITE",    "path_from_args"),
    "save_file":          ("WRITE",    "path_from_args"),
    "append_file":        ("WRITE",    "path_from_args"),
    # File read
    "file_read":          ("READ",     "path_from_args"),
    "read_file":          ("READ",     "path_from_args"),
    "view":               ("READ",     "path_from_args"),
    "list_dir":           ("READ",     "path_from_args"),
    # Exec
    "bash":               ("EXECUTE",  "command_from_args"),
    "exec":               ("EXECUTE",  "command_from_args"),
    "run_command":        ("EXECUTE",  "command_from_args"),
    "shell":              ("EXECUTE",  "command_from_args"),
    "python":             ("EXECUTE",  "command_from_args"),
    "run_script":         ("EXECUTE",  "command_from_args"),
    # Delete
    "file_delete":        ("DELETE",   "path_from_args"),
    "delete_file":        ("DELETE",   "path_from_args"),
    "remove_file":        ("DELETE",   "path_from_args"),
    # Transfer
    "transfer_money":     ("TRANSFER", "transfer_facts"),
    "send_payment":       ("TRANSFER", "transfer_facts"),
    "wire_transfer":      ("TRANSFER", "transfer_facts"),
    "crypto_transfer":    ("TRANSFER", "transfer_facts"),
    # Admin
    "escalate_privilege": ("ADMIN",    "command_from_args"),
    "sudo":               ("ADMIN",    "command_from_args"),
    "add_user":           ("ADMIN",    "command_from_args"),
    "change_policy":      ("ADMIN",    "command_from_args"),
}

# Keyword fallback table (checked if exact miss, first keyword match wins)
# Order matters: more specific keywords first
KEYWORD_FALLBACK: list[tuple[str, str, str]] = [
    # (keyword_in_tool_name, action_class, facts_extractor)
    ("transfer",  "TRANSFER", "transfer_facts"),
    ("payment",   "TRANSFER", "transfer_facts"),
    ("delete",    "DELETE",   "path_from_args"),
    ("remove",    "DELETE",   "path_from_args"),
    ("admin",     "ADMIN",    "command_from_args"),
    ("privilege", "ADMIN",    "command_from_args"),
    ("exec",      "EXECUTE",  "command_from_args"),
    ("bash",      "EXECUTE",  "command_from_args"),
    ("run",       "EXECUTE",  "command_from_args"),
    ("shell",     "EXECUTE",  "command_from_args"),
    ("write",     "WRITE",    "path_from_args"),
    ("upload",    "WRITE",    "path_from_args"),
    ("save",      "WRITE",    "path_from_args"),
    ("create",    "WRITE",    "path_from_args"),
    ("read",      "READ",     "path_from_args"),
    ("fetch",     "NETWORK",  "url_to_domain"),
    ("request",   "NETWORK",  "url_to_domain"),
    ("http",      "NETWORK",  "url_to_domain"),
    ("api",       "NETWORK",  "url_to_domain"),
    ("send",      "NETWORK",  "recipient_to_domain"),
    ("email",     "NETWORK",  "recipient_to_domain"),
    ("webhook",   "NETWORK",  "url_to_domain"),
    ("search",    "NETWORK",  "query_to_command"),
]

# Default when nothing matches
DEFAULT_ACTION_CLASS = "EXECUTE"
DEFAULT_EXTRACTOR    = "command_from_args"


def lookup(tool_name: str) -> tuple[str, str]:
    """Return (action_class, extractor_key) for a tool name."""
    tn = tool_name.lower().strip()
    if tn in EXACT:
        return EXACT[tn]
    for kw, ac, ext in KEYWORD_FALLBACK:
        if kw in tn:
            return ac, ext
    return DEFAULT_ACTION_CLASS, DEFAULT_EXTRACTOR

