# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
# AGPL-3.0
"""
K9log Ledger Sync - Optional push of CIEU records to a remote endpoint

Architecture principle
----------------------
The local CIEU ledger is always the single source of truth.
Sync is a read-only operation on the ledger — it never modifies records.
The cursor (last_synced_seq) is stored separately so it can be reset
without touching the ledger itself.

Config (in ~/.k9log/alerting.json under "sync" key):
    enabled           : bool   — master switch, default False
    endpoint          : str    — POST URL, e.g. "https://your-server/api/ingest"
    api_key           : str    — sent as Authorization: Bearer <api_key>
    batch_size        : int    — records per HTTP request, default 100
    on_deviation_only : bool   — True = push only R_t+1.passed==False records
    retry_on_failure  : bool   — queue failed batches to sync_retry.jsonl
    cursor_path       : str    — override cursor file path

Usage
-----
    # Manual push (CLI):
    k9log sync push

    # Programmatic (e.g. end of session):
    from k9log.ledger_sync import push_pending
    push_pending()
"""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

_log = logging.getLogger("k9log.ledger_sync")

# ── Paths ─────────────────────────────────────────────────────────────────────

_K9_DIR      = Path.home() / ".k9log"
_LEDGER_PATH = _K9_DIR / "logs" / "k9log.cieu.jsonl"
_CURSOR_PATH = _K9_DIR / "sync_cursor.json"
_RETRY_PATH  = _K9_DIR / "sync_retry.jsonl"
_CONFIG_PATH = _K9_DIR / "alerting.json"


# ── Config helpers ────────────────────────────────────────────────────────────

def _load_sync_config() -> dict:
    """Load the [sync] section from alerting.json."""
    defaults = {
        "enabled":            False,
        "endpoint":           "",
        "api_key":            "",
        "batch_size":         100,
        "on_deviation_only":  False,
        "retry_on_failure":   True,
        "cursor_path":        "",
    }
    if not _CONFIG_PATH.exists():
        return defaults
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
        user_sync = cfg.get("sync", {})
        return {**defaults, **user_sync}
    except Exception as e:
        _log.warning("k9log sync: failed to load config: %s", e)
        return defaults


def _cursor_path(cfg: dict) -> Path:
    override = cfg.get("cursor_path", "")
    return Path(override).expanduser() if override else _CURSOR_PATH


# ── Cursor management ─────────────────────────────────────────────────────────

def _load_cursor(cfg: dict) -> int:
    """Return last successfully synced seq number, or -1 if never synced."""
    p = _cursor_path(cfg)
    if not p.exists():
        return -1
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return int(data.get("last_synced_seq", -1))
    except Exception:
        return -1


def _save_cursor(cfg: dict, seq: int) -> None:
    p = _cursor_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({
            "last_synced_seq": seq,
            "updated_at":      datetime.now(timezone.utc).isoformat(),
        }, indent=2),
        encoding="utf-8",
    )


def reset_cursor() -> None:
    """Reset sync cursor so next push re-sends all records."""
    cfg = _load_sync_config()
    p = _cursor_path(cfg)
    if p.exists():
        p.unlink()
    _log.info("k9log sync: cursor reset — next push will re-send all records")


# ── Record streaming ──────────────────────────────────────────────────────────

def _stream_pending(cfg: dict, last_seq: int):
    """
    Yield CIEU records whose _integrity.seq > last_seq.

    Streams line-by-line — O(1) memory regardless of ledger size.
    Skips SESSION_END and malformed lines silently.
    """
    if not _LEDGER_PATH.exists():
        return

    deviation_only = cfg.get("on_deviation_only", False)

    with open(_LEDGER_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if record.get("event_type") == "SESSION_END":
                continue

            seq = (record.get("_integrity") or {}).get("seq")
            if seq is None or seq <= last_seq:
                continue

            if deviation_only and record.get("R_t+1", {}).get("passed", True):
                continue

            yield record


# ── HTTP push ─────────────────────────────────────────────────────────────────

def _post_batch(endpoint: str, api_key: str, batch: list) -> bool:
    """
    POST a batch of CIEU records to endpoint.
    Returns True on HTTP 2xx, False otherwise.
    Never raises — caller handles retry logic.
    """
    headers = {
        "Content-Type":  "application/json",
        "User-Agent":    "k9log-sync/0.2.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "source":     "k9log",
        "version":    "0.2.0",
        "batch_size": len(batch),
        "sent_at":    datetime.now(timezone.utc).isoformat(),
        "records":    batch,
    }

    try:
        resp = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=30,
        )
        if 200 <= resp.status_code < 300:
            return True
        _log.warning(
            "k9log sync: server returned %s — %s",
            resp.status_code, resp.text[:200],
        )
        return False
    except requests.exceptions.ConnectionError:
        _log.warning("k9log sync: connection failed to %s", endpoint)
        return False
    except requests.exceptions.Timeout:
        _log.warning("k9log sync: request timed out to %s", endpoint)
        return False
    except Exception as e:
        _log.warning("k9log sync: unexpected error: %s", e)
        return False


def _append_retry(batch: list) -> None:
    """Queue a failed batch to sync_retry.jsonl for later."""
    _RETRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "queued_at":  datetime.now(timezone.utc).isoformat(),
        "batch_size": len(batch),
        "records":    batch,
    }
    with open(_RETRY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _log.info("k9log sync: %d records queued to retry file", len(batch))


# ── Public API ────────────────────────────────────────────────────────────────

class SyncResult:
    """Summary of a push_pending() call."""
    def __init__(self):
        self.pushed_records:  int = 0
        self.pushed_batches:  int = 0
        self.failed_batches:  int = 0
        self.queued_to_retry: int = 0
        self.last_synced_seq: int = -1
        self.skipped_reason:  str = ""

    def __repr__(self):
        return (
            f"SyncResult(pushed={self.pushed_records}, "
            f"batches={self.pushed_batches}, "
            f"failed={self.failed_batches}, "
            f"last_seq={self.last_synced_seq})"
        )


def push_pending(silent: bool = False) -> SyncResult:
    """
    Push all unsynced CIEU records to the configured endpoint.

    Safe to call at any time — if sync is disabled or endpoint is not
    configured, returns immediately with skipped_reason set.

    Args:
        silent: suppress INFO-level log output (used in automated contexts)

    Returns:
        SyncResult with push statistics
    """
    result = SyncResult()
    cfg = _load_sync_config()

    if not cfg.get("enabled", False):
        result.skipped_reason = "sync disabled in config"
        return result

    endpoint = cfg.get("endpoint", "").strip()
    if not endpoint:
        result.skipped_reason = "no endpoint configured"
        _log.warning("k9log sync: enabled=true but no endpoint set in alerting.json")
        return result

    api_key    = cfg.get("api_key", "")
    batch_size = max(1, int(cfg.get("batch_size", 100)))

    last_seq = _load_cursor(cfg)
    if not silent:
        _log.info(
            "k9log sync: starting push from seq=%d to %s (deviation_only=%s)",
            last_seq + 1, endpoint, cfg.get("on_deviation_only", False),
        )

    batch: list = []
    highest_seq = last_seq

    for record in _stream_pending(cfg, last_seq):
        batch.append(record)
        seq = (record.get("_integrity") or {}).get("seq", highest_seq)
        if seq > highest_seq:
            highest_seq = seq

        if len(batch) >= batch_size:
            ok = _post_batch(endpoint, api_key, batch)
            if ok:
                result.pushed_records += len(batch)
                result.pushed_batches += 1
                _save_cursor(cfg, highest_seq)
                result.last_synced_seq = highest_seq
            else:
                result.failed_batches += 1
                if cfg.get("retry_on_failure", True):
                    _append_retry(batch)
                    result.queued_to_retry += len(batch)
            batch = []

    # flush remaining
    if batch:
        ok = _post_batch(endpoint, api_key, batch)
        if ok:
            result.pushed_records += len(batch)
            result.pushed_batches += 1
            _save_cursor(cfg, highest_seq)
            result.last_synced_seq = highest_seq
        else:
            result.failed_batches += 1
            if cfg.get("retry_on_failure", True):
                _append_retry(batch)
                result.queued_to_retry += len(batch)

    if not silent:
        _log.info(
            "k9log sync: done — pushed %d records in %d batches, %d failed",
            result.pushed_records, result.pushed_batches, result.failed_batches,
        )

    return result


def sync_status() -> dict:
    """
    Return a summary dict for CLI display.
    Does not push anything — read-only.
    """
    cfg      = _load_sync_config()
    last_seq = _load_cursor(cfg)

    # Count pending records
    pending = 0
    for _ in _stream_pending(cfg, last_seq):
        pending += 1

    # Count retry queue
    retry_count = 0
    if _RETRY_PATH.exists():
        try:
            for line in _RETRY_PATH.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    retry_count += entry.get("batch_size", 0)
        except Exception:
            pass

    return {
        "enabled":           cfg.get("enabled", False),
        "endpoint":          cfg.get("endpoint", ""),
        "on_deviation_only": cfg.get("on_deviation_only", False),
        "batch_size":        cfg.get("batch_size", 100),
        "last_synced_seq":   last_seq,
        "pending_records":   pending,
        "retry_queue_size":  retry_count,
        "cursor_path":       str(_cursor_path(cfg)),
    }


def flush_retry() -> SyncResult:
    """
    Attempt to re-send all records in sync_retry.jsonl.
    Clears the retry file on full success.
    """
    result = SyncResult()
    cfg = _load_sync_config()
    endpoint = cfg.get("endpoint", "").strip()
    if not endpoint:
        result.skipped_reason = "no endpoint configured"
        return result

    if not _RETRY_PATH.exists():
        return result

    api_key = cfg.get("api_key", "")
    lines = _RETRY_PATH.read_text(encoding="utf-8").strip().splitlines()
    all_ok = True

    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            batch = entry.get("records", [])
        except Exception:
            continue
        ok = _post_batch(endpoint, api_key, batch)
        if ok:
            result.pushed_records += len(batch)
            result.pushed_batches += 1
        else:
            result.failed_batches += 1
            all_ok = False

    if all_ok and _RETRY_PATH.exists():
        _RETRY_PATH.unlink()
        _log.info("k9log sync: retry queue cleared")

    return result
