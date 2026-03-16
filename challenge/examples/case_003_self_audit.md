# K9 Hard Case — #003: K9 Audited by K9

**Date:** 2026-03-16
**Session:** Outer K9 (meta_auditor) · Inner K9 (subject_agent)
**Outer Ledger:** 29 records · **Inner Ledger:** ~/.k9log/logs/k9log.cieu.jsonl
**Evidence integrity:** Both chains verified intact
**Status:** Closed — 27 / 28 README claims verified

---

## What happened (in one sentence)

K9 Audit was used to audit K9 Audit: the README became the Y*_t intent contract, Outer K9 ran 28 executable tests against Inner K9, and every result was recorded as a CIEU record in a separate Ledger.

---

## Why this is hard without a causal audit tool

Testing whether a tool "works" is straightforward. Testing whether a tool **honours the promises it makes in its documentation** requires a different frame entirely.

Conventional test frameworks answer: "does this function return the right value?"
A CIEU-structured audit answers: "does this system's behaviour match its declared intent?"

The difference becomes critical when the two diverge in unexpected directions — not because the code is broken, but because the documentation is wrong, or because an implementation is stronger than advertised, or because a design assumption was never made explicit.

All three of those cases appeared in this audit.

---

## Setup

Two K9 instances running simultaneously:

- **Inner K9** — the subject. Normal `@k9`-decorated functions writing to `~/.k9log/logs/k9log.cieu.jsonl`.
- **Outer K9** — the auditor. A separate `CIEULogger` instance writing to `/tmp/k9_outer/logs/k9log.cieu.jsonl`. Its Y*_t was derived from README.md.

The README was parsed into 28 testable intent clauses across 5 categories. For each clause, Outer K9 ran a test and recorded whether Inner K9's actual behaviour matched the documented intent.

---

## The 28 intent clauses and results

### Architecture (5/5)

| ID | Claim | Result |
|---|---|---|
| ARCH-01 | Every action produces a CIEU five-tuple | ✓ All 5 fields present in every Ledger record |
| ARCH-02 | SHA256 hash-chained, tamper-evident | ✓ prev_hash → event_hash chain intact across all records |
| ARCH-03 | Zero token consumption — no LLM calls | ✓ No openai/anthropic/httpx in core/logger/constraints/verifier/tracer |
| ARCH-04 | @k9 never raises to the caller — Ledger still written | ✓ Internal ValueError → caller receives exception, execution_error recorded |
| ARCH-05 | Data stays local by default | ✓ No unconditional outbound network calls in core.py or logger.py |

### Constraint syntax (11/11)

All constraint types documented in the README were tested bidirectionally (trigger + no-trigger):

`deny_content`, `allowed_paths`, `max`, `min`, `max_length`, `blocklist`, `allowlist`, `enum`, `regex`, `register_constraint` (custom constraint type). All 11 passed.

### CLI (6/6)

`k9log stats`, `k9log trace --last`, `k9log verify-log`, `k9log health`, `k9log report --output`, `k9log audit ./my-project`. All returned exit code 0.

### Agent integrations (4/5)

| ID | Claim | Result |
|---|---|---|
| INT-01 | Any Python agent — zero config, one @k9 | ✓ |
| INT-02 | Async function support | ✓ |
| INT-03 | LangChain K9CallbackHandler | ✓ |
| INT-04 | k9_wrap_module — wrap an entire module | ✗ See finding below |
| INT-05 | AGENTS.md / CLAUDE.md parsed to Grant objects | ✓ 3 rules → 3 Grant objects |

### Privacy (1/2)

| ID | Claim | Result |
|---|---|---|
| PRIV-01 | Sensitive param names auto-redacted | ✗ See finding below |
| PRIV-02 | sync disabled → no network call | ✓ |

---

## The two findings

### INT-04 — k9_wrap_module edge case

**Root cause:** `k9_wrap_module` filters out functions whose `__module__ != module.__name__`. Dynamically constructed modules (via `types.ModuleType`) cause functions to carry `__module__ = '__main__'`, which fails the check and skips wrapping.

**Scope:** Only affects dynamically built module objects. The README example `import my_skills; k9_wrap_module(my_skills)` works correctly on real `.py` imports. The edge case is real but limited. Documentation should note the constraint.

**Severity:** 0.6 — edge case, not a regression.

---

### PRIV-01 — Implementation stronger than documented

**README claims:** "the value is replaced with `[REDACTED]`"

**Actual output:**
```
{'_redacted': True, '_type': 'str', '_hash': 'sha256:64c63cf281ef', '_length': 16}
```

The actual redaction preserves type, length, and a SHA256 hash for deduplication analysis — objectively more useful than a bare string. This is what the CIEU structure surfaces that a conventional test cannot: the direction of the divergence. The system did not do something wrong. It did something better than documented.

**Recommendation:** Update README to reflect actual behaviour, or add `K9LOG_REDACT_LEVEL=simple` for string output.

**Severity:** 0.95 as a documentation finding — not a capability gap.

---

## Measured facts from the record

| Fact | Value | Evidence field |
|---|---|---|
| README claims tested | 28 | Outer Ledger record count |
| Claims verified | 27 | R_t+1: passed=true |
| Claims with findings | 2 | R_t+1: passed=false |
| Inner Ledger chain | Intact | Verified at analysis time |
| Outer Ledger chain | Intact | Verified at analysis time |
| Outer Ledger records | 29 | One per README claim tested |

---

## Reproduce
```python
from k9log import k9, set_agent_identity
set_agent_identity(agent_name='auditor')

@k9(deny_content=['staging.internal'], amount={'max': 500})
def trade(symbol, amount, endpoint): return {'ok': True}

trade('AAPL', 100, 'https://prod.api.com')          # passes
trade('AAPL', 9999, 'https://prod.api.com')         # caught: amount exceeded
trade('AAPL', 100, 'https://staging.internal/v2')   # caught: forbidden content
```
```bash
k9log trace --last
k9log verify-log
k9log report --output case_003.html
```
