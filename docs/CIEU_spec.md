# CIEU Log — Specification v1.0

**Causal Intent-Execution Unit**

---

## A complete record at a glance

Before the field-by-field spec, here is what one real CIEU record looks like in the Ledger:

```json
{
  "seq": 451,
  "session_id": "abc123",
  "timestamp": "2026-03-04T16:59:22.341Z",
  "X_t": {
    "agent_name": "Claude Code",
    "hostname": "dev-machine",
    "pid": 18234
  },
  "U_t": {
    "skill": "write_file",
    "params": {
      "path": "quant_backtest/config.json",
      "content": "{\"endpoint\": \"https://api.market-data.staging.internal/v2/ohlcv\"}"
    }
  },
  "Y_star_t": {
    "constraints": {
      "deny_content": ["staging.internal"],
      "allowed_paths": ["./quant_backtest/**"]
    },
    "source": "intents/write_config.json",
    "hash": "sha256:9f3a..."
  },
  "Y_t1": {
    "result": true,
    "exit_code": 0,
    "duration_ms": 3.2
  },
  "R_t1": {
    "passed": false,
    "overall_severity": 0.9,
    "risk_level": "CRITICAL",
    "violations": [
      {
        "type": "DENY_CONTENT",
        "field": "content",
        "matched": "staging.internal",
        "severity": 0.9,
        "message": "Content contains forbidden pattern: 'staging.internal'"
      }
    ]
  },
  "prev_hash": "sha256:7c2b...",
  "record_hash": "sha256:4e1d..."
}
```

`prev_hash` chains this record to the previous one — any tampering breaks the chain and is detected by `k9log verify-log`.

---

## What CIEU is

A CIEU record is the fundamental unit of causal audit in K9 Audit. It is not a log entry. It is a structured causal witness.

Ordinary logs record *what happened*. A CIEU record records a causal moment: the context in which an action was taken, the intent contract that governed it, the outcome that resulted, and the measured deviation between the two.

This distinction matters because most hard traceability problems are not caused by missing events. They are caused by missing *causality*. You have the logs. You still cannot determine:

- Which step caused the downstream failure
- Whether the actor was doing what it was supposed to do
- How far the actual outcome diverged from the intended one
- Whether the deviation was detectable at the time it happened

CIEU records make all four answerable.

---

## The five-tuple

Every CIEU record contains exactly five fields:

```
X_t      Context        Who acted, when, from where
U_t      Action         What they actually did
Y*_t     Intent         What they were supposed to do
Y_t+1    Outcome        What actually happened
R_t+1    Assessment     How far it diverged, and why
```

The subscript `t` is the step index within the session. `t+1` is the post-execution state.

The critical field is `Y*_t`. Without an intent contract, you can observe the outcome. With it, you can determine whether the outcome was correct. This is the difference between a log and an audit record.

---

## Field specification

### `X_t` — Context

Who acted, when, and from where.

```json
{
  "ts": 1741100362.441,
  "datetime": "2026-03-04T16:59:22+00:00",
  "agent_id": "claude-code",
  "agent_name": "Claude Code",
  "agent_type": "coding",
  "session_id": "abc123",
  "action_class": "WRITE",
  "caller": {
    "file": "hook.py",
    "line": 0,
    "function": "hook"
  }
}
```

`action_class` must be one of: `READ`, `WRITE`, `EXECUTE`, `NETWORK`, `DELETE`, `ADMIN`.

---

### `U_t` — Action

What the actor actually did.

```json
{
  "skill": "_write_file",
  "params": {
    "path": "quant_backtest/config.json",
    "content": "{\"endpoint\": \"https://api.market-data.staging.internal/v2/ohlcv\"}"
  }
}
```

`skill` is the normalized internal name of the operation. `params` contains the full parameters at call time. Sensitive values (credentials, tokens) are redacted before writing — see `k9log/redact.py`.

---

### `Y*_t` — Intent Contract

What the actor was supposed to do. This is the audit baseline.

```json
{
  "constraints": {
    "deny_content": ["staging.internal", "*.internal"],
    "allowed_paths": ["./project/**"],
    "action_class": "WRITE"
  },
  "y_star_meta": {
    "source": "intents/write_config.json",
    "hash": "sha256:a3f...",
    "version": "1.0"
  }
}
```

The intent contract is loaded from the user-defined intent files at call time. It declares what the actor should do: what content is forbidden, what paths are allowed, what action classes are expected.

If no contract is defined for a given skill, `constraints` is empty and the record is logged without deviation assessment. The audit still runs — it simply has no baseline to compare against.

---

### `Y_t+1` — Outcome

What actually happened after the action.

```json
{
  "result": {},
  "status": "success"
}
```

`status` is one of: `pending`, `success`, `error`, `blocked`.

For completed operations, `result` contains the return value after redaction. For blocked operations (in systems with enforcement layers), `result` is empty.

---

### `R_t+1` — Assessment

The measured deviation between `U_t` and `Y*_t`.

```json
{
  "passed": false,
  "overall_severity": 0.9,
  "violations": [
    {
      "type": "DENY_CONTENT",
      "matched": "staging.internal",
      "field": "content"
    }
  ],
  "duration_sec": 0.003
}
```

`passed` is `true` if no deviations were detected. `overall_severity` is a float from `0.0` to `1.0`.

`violations` is the list of specific deviations found. Each violation records the type, the field where the deviation occurred, and what was matched.

---

## Violation types

| Type | Meaning |
|------|---------|
| `DENY_CONTENT` | Action content matched a forbidden pattern in the intent contract |
| `GRANT_SCOPE_MISMATCH` | Action class does not match the declared intent |
| `LEARNED_RULE_HIT` | Action matched a pattern learned from prior incident history | _(Phase 2)_ |
| `taint_violation` | Data from an untrusted source reached a sensitive operation | _(Phase 2)_ |

---

## Intent contracts

Intent contracts define `Y*_t` — the baseline against which every action is assessed.

### Inline (Python decorator)

```python
from k9log.core import k9

@k9(
    deny_content=["staging.internal"],
    allowed_paths=["./project/**"],
    action_class="WRITE"
)
def write_config(path: str, content: dict) -> bool:
    ...
```

### File-based (JSON)

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

### File-based (YAML)

```yaml
# ~/.k9log/intents/write_config.yaml
skill: write_config
constraints:
  deny_content:
    - "staging.internal"
    - "*.internal"
  allowed_paths:
    - "./project/**"
  action_class: WRITE
```

K9 Audit loads contracts at call time, writes them into `Y*_t`, computes the deviation in `R_t+1`, and records the result. It does not enforce or block — that is the responsibility of layers built on top of the audit core.

---

## Hash chain

Each record contains three chain fields:

```json
{
  "_seq": 451,
  "_hash": "sha256:9f3a...",
  "_prev_hash": "sha256:7c1b...",
  ...
}
```

`_hash` is computed over the full serialized record content, excluding `_hash` itself. `_prev_hash` is the `_hash` of record `_seq - 1`.

This forms a tamper-evident chain. Any modification to any record, or any deletion from the middle of the sequence, breaks the chain at that point and is detectable.

```bash
k9log verify
```

```
Chain intact. 704 records verified. No tampering detected.
```

---

## Full record example

```json
{
  "_seq": 451,
  "_hash": "sha256:9f3a...",
  "_prev_hash": "sha256:7c1b...",
  "X_t": {
    "ts": 1741100362.441,
    "datetime": "2026-03-04T16:59:22+00:00",
    "agent_id": "claude-code",
    "agent_name": "Claude Code",
    "agent_type": "coding",
    "session_id": "abc123",
    "action_class": "WRITE",
    "caller": {
      "file": "hook.py",
      "line": 0,
      "function": "hook"
    }
  },
  "U_t": {
    "skill": "_write_file",
    "params": {
      "path": "quant_backtest/config.json",
      "content": "{\"endpoint\": \"https://api.market-data.staging.internal/v2/ohlcv\"}"
    }
  },
  "Y_star_t": {
    "constraints": {
      "deny_content": ["staging.internal"],
      "allowed_paths": ["./quant_backtest/**"]
    },
    "y_star_meta": {
      "source": "intents/write_config.json",
      "hash": "sha256:a3f...",
      "version": "1.0"
    }
  },
  "Y_t+1": {
    "result": {},
    "status": "success"
  },
  "R_t+1": {
    "passed": false,
    "overall_severity": 0.9,
    "violations": [
      {
        "type": "DENY_CONTENT",
        "matched": "staging.internal",
        "field": "content"
      }
    ],
    "duration_sec": 0.003
  }
}
```

---

## Why CIEU is not structured logging

Structured logs (JSON logs, OpenTelemetry spans) record *what happened*.

CIEU records record *what should have happened, what actually happened, and how far they diverged*.

The key difference is `Y*_t`. Without it, you can observe the outcome. With it, you can determine whether the outcome was correct. This is the difference between a witness and an auditor.

A second difference is the hash chain. Structured logs are append-only by convention. CIEU records are tamper-evident by construction — verifiable cryptographically, not just by reviewing timestamps.

A third difference is the assessment. `R_t+1` is computed at the time of the action, not reconstructed afterward. The deviation record reflects the state of the system at the moment the action occurred, not a post-hoc interpretation.

---

## Storage

Records are written to `~/.k9log/logs/k9log.cieu.jsonl`: one JSON object per line, UTF-8 encoded, append-only.

Do not modify the file directly. Use `k9log verify` to check integrity and `k9log trace` to query records.

---

## Extending to your own system

**Python decorator**

```python
from k9log.core import k9

@k9
def your_function(param1, param2):
    ...
```

**Direct record construction**

```python
from k9log.logger import get_logger

logger = get_logger()
logger.write_cieu({
    "X_t": { ... },
    "U_t": {"skill": "your_skill", "params": { ... }},
    "Y_star_t": {"constraints": {}},
    "Y_t+1": {"result": ..., "status": "success"},
    "R_t+1": {"passed": True, "violations": [], "overall_severity": 0.0}
})
```

---

## Version history

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-03-07 | Initial public specification |

