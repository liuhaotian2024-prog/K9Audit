# K9Audit Sync Server — lightweight CIEU ingest endpoint
# Copyright (C) 2026 Haotian Liu
# AGPL-3.0
"""
Minimal FastAPI server that receives CIEU record batches from k9log sync push.

Design principles:
  - Append-only: never modifies records, preserves original hash chain
  - Per-workspace isolation: each api_key writes to its own JSONL file
  - No database required: plain .jsonl files, verifiable with k9log verify-log
  - Auth: Bearer token (api_key) — simple, stateless

Quick start:
  pip install fastapi uvicorn
  API_KEY=mysecret uvicorn server.main:app --host 0.0.0.0 --port 8000

Client:
  k9log sync enable --endpoint http://your-server:8000/api/ingest --api-key mysecret
  k9log sync push
"""
import json
import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────────────────────

DATA_DIR   = Path(os.environ.get("K9_DATA_DIR",  "./data"))
LOG_LEVEL  = os.environ.get("K9_LOG_LEVEL",  "INFO")
# Comma-separated list of valid API keys, OR a single key via API_KEY env var.
# Example: API_KEYS=key1,key2,key3
_raw_keys  = os.environ.get("API_KEYS", os.environ.get("API_KEY", ""))
VALID_KEYS = {k.strip() for k in _raw_keys.split(",") if k.strip()}

logging.basicConfig(level=LOG_LEVEL)
_log = logging.getLogger("k9server")

DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="K9Audit Sync Server",
    description="Receives CIEU ledger batches from k9log sync push",
    version="0.1.0",
    docs_url="/docs",
)

security = HTTPBearer(auto_error=False)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _workspace_id(api_key: str) -> str:
    """Derive a stable workspace directory name from the api_key."""
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Return workspace_id if auth passes, raise 401 otherwise."""
    if not VALID_KEYS:
        # No keys configured — open mode (dev/testing only, log a warning)
        _log.warning("K9_SERVER: no API keys configured — accepting all requests")
        token = credentials.credentials if credentials else "anonymous"
        return _workspace_id(token)

    if not credentials or credentials.credentials not in VALID_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return _workspace_id(credentials.credentials)


# ── Request / Response models ─────────────────────────────────────────────────

class IngestPayload(BaseModel):
    source:     str
    version:    str
    batch_size: int
    sent_at:    str
    records:    list


class IngestResponse(BaseModel):
    accepted:   int
    rejected:   int
    workspace:  str
    ledger_seq: int  # highest seq number now stored


# ── Storage ───────────────────────────────────────────────────────────────────

def _workspace_ledger(workspace_id: str) -> Path:
    p = DATA_DIR / workspace_id
    p.mkdir(parents=True, exist_ok=True)
    return p / "k9log.cieu.jsonl"


def _append_records(ledger_path: Path, records: list) -> tuple[int, int]:
    """
    Append records to workspace ledger.
    Returns (accepted_count, rejected_count).
    Records without _integrity are accepted but flagged with a warning.
    """
    accepted = 0
    rejected = 0

    with open(ledger_path, "a", encoding="utf-8") as f:
        for rec in records:
            if not isinstance(rec, dict):
                rejected += 1
                continue
            # Stamp server receipt time (does not alter original _integrity)
            rec["_server_received_at"] = datetime.now(timezone.utc).isoformat()
            if "_integrity" not in rec:
                _log.warning("K9_SERVER: record missing _integrity — accepted with warning")
                rec["_server_warning"] = "missing_integrity"
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            accepted += 1

    return accepted, rejected


def _highest_seq(ledger_path: Path) -> int:
    """Return the highest _integrity.seq stored, or -1."""
    if not ledger_path.exists():
        return -1
    highest = -1
    try:
        with open(ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    seq = (rec.get("_integrity") or {}).get("seq")
                    if seq is not None and seq > highest:
                        highest = seq
                except Exception:
                    continue
    except Exception:
        pass
    return highest


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Health check — no auth required."""
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/ingest", response_model=IngestResponse)
def ingest(
    payload: IngestPayload,
    workspace_id: str = Depends(verify_token),
):
    """
    Receive a batch of CIEU records from k9log sync push.
    Records are appended to a per-workspace append-only JSONL ledger.
    """
    if not payload.records:
        raise HTTPException(status_code=400, detail="Empty records list")

    if len(payload.records) > 1000:
        raise HTTPException(status_code=413, detail="Batch too large (max 1000)")

    ledger_path = _workspace_ledger(workspace_id)
    accepted, rejected = _append_records(ledger_path, payload.records)
    highest = _highest_seq(ledger_path)

    _log.info(
        "K9_SERVER: workspace=%s accepted=%d rejected=%d highest_seq=%d",
        workspace_id, accepted, rejected, highest,
    )

    return IngestResponse(
        accepted=accepted,
        rejected=rejected,
        workspace=workspace_id,
        ledger_seq=highest,
    )


@app.get("/api/status")
def workspace_status(workspace_id: str = Depends(verify_token)):
    """Return record count and latest seq for the authenticated workspace."""
    ledger_path = _workspace_ledger(workspace_id)

    if not ledger_path.exists():
        return {"workspace": workspace_id, "total_records": 0, "highest_seq": -1}

    total = 0
    violations = 0
    highest = -1

    with open(ledger_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                total += 1
                seq = (rec.get("_integrity") or {}).get("seq")
                if seq is not None and seq > highest:
                    highest = seq
                if not (rec.get("R_t+1") or {}).get("passed", True):
                    violations += 1
            except Exception:
                continue

    return {
        "workspace":      workspace_id,
        "total_records":  total,
        "violations":     violations,
        "highest_seq":    highest,
        "ledger_path":    str(ledger_path),
    }
