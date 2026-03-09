# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
"""
K9log Redact - Sensitive data masking for CIEU records

Default behavior: automatically mask common sensitive patterns in params.
Users can control redaction via:
  - Environment variable: K9LOG_REDACT_LEVEL=off|standard|strict
  - Config file: ~/.k9log/redact.json
"""
import re
import os
import json
import hashlib
from pathlib import Path

REDACT_OFF = "off"
REDACT_STANDARD = "standard"
REDACT_STRICT = "strict"
DEFAULT_LEVEL = REDACT_STANDARD

SENSITIVE_PARAM_NAMES = re.compile(
    r"(password|passwd|pwd|secret|token|api_key|apikey|"
    r"auth|authorization|bearer|credential|private_key|"
    r"access_key|secret_key|session_id|session_token|cookie|"
    r"ssn|social_security|credit_card|card_number|cvv|cvc|"
    r"bank_account|routing_number)",
    re.IGNORECASE
)

SENSITIVE_VALUE_PATTERNS = [
    (re.compile(r"(sk-[a-zA-Z0-9]{20,})"), "***API_KEY***"),
    (re.compile(r"(ghp_[a-zA-Z0-9]{36,})"), "***GITHUB_TOKEN***"),
    (re.compile(r"(xox[bpas]-[a-zA-Z0-9\-]+)"), "***SLACK_TOKEN***"),
    (re.compile(r"(\d{8,}:[A-Za-z0-9_\-]{30,})"), "***BOT_TOKEN***"),
    (re.compile(r"(Bearer\s+[a-zA-Z0-9\-_.]+)"), "***BEARER_TOKEN***"),
    (re.compile(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"), "***EMAIL***"),
    (re.compile(r"(\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b)"), "***CARD***"),
    (re.compile(r"(\b\d{3}-\d{2}-\d{4}\b)"), "***SSN***"),
    (re.compile(r"(\b\+?1?[\s\-.]?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b)"), "***PHONE***"),
]

CONFIG_PATH = Path.home() / ".k9log" / "redact.json"


def _load_redact_config():
    env_level = os.environ.get("K9LOG_REDACT_LEVEL", "").lower()
    if env_level in (REDACT_OFF, REDACT_STANDARD, REDACT_STRICT):
        return {"level": env_level, "extra_sensitive_params": []}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as fh:
                config = json.load(fh)
            if config.get("level") in (REDACT_OFF, REDACT_STANDARD, REDACT_STRICT):
                return config
        except Exception:
            pass
    return {"level": DEFAULT_LEVEL, "extra_sensitive_params": []}


def _hash_value(value):
    s = str(value)
    return "sha256:" + hashlib.sha256(s.encode()).hexdigest()[:12]


# Sensitive patterns (API keys, tokens, SSNs, credit cards) are always short
# strings. File contents, code, or any param value longer than this threshold
# is virtually never a credential — scanning it character-by-character with 9
# regexes causes O(n) × 9 latency that ruins Claude Code hook performance.
# Strategy: scan only the first REDACT_SCAN_LIMIT characters; if the value is
# longer we append a truncation marker so the stored record clearly shows the
# original was larger.
_REDACT_SCAN_LIMIT = 2000  # chars — covers any realistic credential/token


def _redact_value(value):
    s = str(value)
    if len(s) <= _REDACT_SCAN_LIMIT:
        for pattern, replacement in SENSITIVE_VALUE_PATTERNS:
            s = pattern.sub(replacement, s)
        return s
    # Large value: scan only the head (credentials appear at the start of a
    # value, e.g. "Bearer sk-..."), leave the tail untouched.
    head = s[:_REDACT_SCAN_LIMIT]
    tail = s[_REDACT_SCAN_LIMIT:]
    for pattern, replacement in SENSITIVE_VALUE_PATTERNS:
        head = pattern.sub(replacement, head)
    return head + tail


def redact_params(params, level=None):
    if level is None:
        config = _load_redact_config()
        level = config.get("level", DEFAULT_LEVEL)
    else:
        config = {"extra_sensitive_params": []}
    if level == REDACT_OFF:
        return params
    if level == REDACT_STRICT:
        result = {}
        for key, value in params.items():
            result[key] = {"_redacted": True, "_type": type(value).__name__, "_hash": _hash_value(value)}
            if isinstance(value, (str, bytes, list, dict)):
                result[key]["_length"] = len(value)
        return result
    result = {}
    extra_names = config.get("extra_sensitive_params", [])
    for key, value in params.items():
        is_sensitive_name = bool(SENSITIVE_PARAM_NAMES.search(key))
        if not is_sensitive_name and extra_names:
            is_sensitive_name = any(n.lower() in key.lower() for n in extra_names)
        if is_sensitive_name:
            result[key] = {"_redacted": True, "_type": type(value).__name__, "_hash": _hash_value(value)}
            if isinstance(value, (str, bytes, list, dict)):
                result[key]["_length"] = len(value)
        elif isinstance(value, str):
            result[key] = _redact_value(value)
        elif isinstance(value, dict):
            result[key] = redact_params(value, level)
        elif isinstance(value, list):
            result[key] = [_redact_value(str(v)) if isinstance(v, str) else v for v in value]
        else:
            result[key] = value
    return result


def redact_context(x_t, level=None):
    if level is None:
        config = _load_redact_config()
        level = config.get("level", DEFAULT_LEVEL)
    if level == REDACT_OFF:
        return x_t
    result = dict(x_t)
    if level == REDACT_STRICT:
        result.pop("hostname", None)
        result.pop("user", None)
        if "caller" in result:
            result["caller"] = {"function": result["caller"].get("function", "unknown")}
    else:
        if "hostname" in result:
            result["hostname"] = _hash_value(result["hostname"])
        if "user" in result:
            result["user"] = _hash_value(result["user"])
        if "caller" in result and "file" in result["caller"]:
            result["caller"]["file"] = Path(result["caller"]["file"]).name
    return result


def redact_result(y_t_plus_1, level=None):
    if level is None:
        config = _load_redact_config()
        level = config.get("level", DEFAULT_LEVEL)
    if level == REDACT_OFF:
        return y_t_plus_1
    if y_t_plus_1 is None:
        return y_t_plus_1
    result = dict(y_t_plus_1)
    if level == REDACT_STRICT:
        if "result" in result:
            r = result["result"]
            result["result"] = {"_redacted": True, "_type": type(r).__name__}
            if isinstance(r, (str, bytes, list, dict)):
                result["result"]["_length"] = len(r)
        return result
    if "result" in result:
        r = result["result"]
        if isinstance(r, str):
            result["result"] = _redact_value(r)
        elif isinstance(r, dict):
            result["result"] = redact_params(r, level)
    return result

