# K9 Audit

**Turn hard-to-trace problems into explainable, accountable evidence.**

K9 Audit is a causal audit core built on CIEU Log — turning raw behavior streams into five-tuple causal audit records: who acted, what they did, what should have happened, what actually happened, and how far they diverged.

> K9 Audit is not about solving our puzzle. It is about finally solving yours.

---

## The problem

Most logs tell you *what happened*. They don't tell you *why it was wrong*, *where the deviation started*, or *who is responsible*.

When something goes wrong in a complex system — an agent misbehaves, a workflow drifts silently, a config gets quietly corrupted — you're left piecing together fragments, guessing at root causes, unable to definitively assign responsibility.

K9 Audit changes that. Not by logging more. By logging *causally*.

---

## A real incident

On March 4, 2026, during a routine quant backtesting session, Claude Code attempted three times to write a staging environment URL into a production config file:

```json
{"endpoint": "https://api.market-data.staging.internal/v2/ohlcv"}
```

The developer had no idea it was happening. Only found out afterward when querying the audit log.

If it had gone through: all backtest results would have been silently corrupted — wrong data source, no error thrown, no way to detect.

```bash
k9log trace --step 451
```

```
seq=451  2026-03-04 16:59:22 UTC

─── X_t  Context ──────────────────────────────────
  agent:    Claude Code  (session: abc123)
  action:   WRITE

─── U_t  What happened ────────────────────────────
  skill:    _write_file
  target:   quant_backtest/config.json
  content:  {"endpoint": "https://api.market-data.staging.internal/..."}

─── Y*_t  What should have happened ───────────────
  constraint: deny_content → ["staging.internal"]
  source:     intents/write_config.json

─── Y_t+1  Outcome ────────────────────────────────
  status:   recorded  (deviation noted)

─── R_t+1  Assessment ─────────────────────────────
  passed:   false
  severity: 0.9
  finding:  content contains forbidden pattern "staging.internal"
  causal_proof: root cause at step #451, chain intact

→  Three attempts. 41 minutes apart. All recorded.
```

---

## What K9 Audit is

Every action recorded by K9 Audit produces a **CIEU record** — a five-tuple causal evidence unit:

| Field | Symbol | Meaning |
|-------|--------|---------|
| Context | `X_t` | Who acted, when, from where |
| Action | `U_t` | What they actually did |
| Intent Contract | `Y*_t` | What they were supposed to do |
| Outcome | `Y_t+1` | What actually resulted |
| Assessment | `R_t+1` | How far the outcome diverged, and why |

Records are hash-chained. Nothing can be silently modified after the fact.

This is not a better log format. It is a different category of thing: **tamper-evident causal evidence**.

---

## What K9 Audit is not

- Not an AI agent governance platform
- Not a blocking or enforcement system
- Not a full-stack safety layer

In this first phase, K9 Audit does precisely one thing:

**Make hard-to-trace problems traceable.**

Record, trace, verify, report. The evidence layer that everything else can be built on top of.

---

## Installation

```bash
pip install k9-audit
```

---

## Quick start

### Option 1: Python decorator

```python
from k9log.core import k9

@k9(
    deny_content=["staging.internal"],
    allowed_paths=["./project/**"]
)
def write_config(path: str, content: dict) -> bool:
    # Your existing code, unchanged
    with open(path, 'w') as f:
        json.dump(content, f)
    return True
```

Every call now produces a CIEU record. Your code runs exactly as before.

### Option 2: Intent contract file

```json
// ~/.k9log/intents/write_config.json
{
  "skill": "write_config",
  "constraints": {
    "deny_content": ["staging.internal", "*.internal"],
    "allowed_paths": ["./project/**"],
    "action_class": "WRITE"
  }
}
```

### Option 3: CLI ingestion

```bash
k9log ingest --input events.jsonl
```

---

## CLI reference

```bash
k9log stats                    # audit summary
k9log trace --step 451         # trace a specific event
k9log trace --last             # trace the most recent deviation
k9log verify                   # verify hash chain integrity
k9log report --output out.html # generate audit report
k9log health                   # system health check
```

---

## Real-time audit alerts

K9 Audit can push a structured CIEU alert the moment a deviation is recorded — before you ever open the log.

Every alert is a CIEU five-tuple, not a raw event notification. The goal is not just to tell you something happened. It is to make you fluent in reading causal evidence.

Configure in `~/.k9log/config/alerting.json`:

```json
{
  "enabled": true,
  "channel": "telegram",
  "token": "...",
  "chat_id": "..."
}
```

Supports Telegram, Slack, Discord.

---

## Architecture

```
k9log/
  core.py              ← @k9 decorator, CIEU recording engine
  logger.py            ← hash-chained JSONL writer
  tracer.py            ← causal trace and root cause analysis
  verifier.py          ← chain integrity verification
  causal_analyzer.py   ← causal graph analysis
  constraints.py       ← Y*_t intent contract loader
  report.py            ← HTML audit report generator
  cli.py               ← k9log command-line interface
  alerting.py          ← real-time CIEU deviation alerts
  identity.py          ← agent identity capture
  redact.py            ← sensitive value redaction
  governance/
    types.py           ← action class and intent type definitions
    action_class.py    ← action classification
```

---

## The K9 Hard Case Challenge

**Bring a traceability problem that has been painfully hard. Solve it with K9 Audit. Show what became possible.**

We are not looking for quiz answers. We are looking for proof that K9 makes previously impractical problems solvable.

The best submissions become part of the **Solved Hard Cases** gallery — a record of problems that were genuinely difficult and are now genuinely solved.

→ [See the challenge](./challenge/README.md)

---

## Log format

Records are written to `~/.k9log/logs/k9log.cieu.jsonl` — one JSON object per line, hash-chained, UTF-8 encoded.

Full specification: [docs/CIEU_spec.md](./docs/CIEU_spec.md)

---

## License

AGPL-3.0. See [LICENSE](./LICENSE).

Copyright (C) 2026 Haotian Liu
