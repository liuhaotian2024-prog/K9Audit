# 🐕‍🦺 K9 Audit

![License](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)
![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Version](https://img.shields.io/badge/Version-0.2.0-blue.svg)
![Evidence](https://img.shields.io/badge/Evidence-SHA256_hash--chain-brightgreen.svg)
![Phase](https://img.shields.io/badge/Phase-Record_·_Trace_·_Verify_·_Report-orange.svg)

**Using an LLM-based audit tool to audit another LLM-based agent is like one suspect signing another suspect's alibi.**

LLMs are probabilistic by nature. Auditing them with another probabilistic tool doesn't solve the problem — it compounds it. A system that is itself uncertain cannot render certain judgments about other systems. No LLM-based audit tool can escape this paradox.

K9 Audit is causal AI applied to the audit problem. It does not generate or guess — it verifies. Every agent action is recorded into a **CIEU Ledger** — a five-tuple causal evidence unit that captures precisely: who acted, what they did, what they were supposed to do, what actually happened, and how far the outcome diverged.

The CIEU Ledger is not a log. It is a causal evidence ledger. Records are SHA256 hash-chained. Nothing can be silently modified or retroactively falsified. Forensic-grade auditing demands visibility, transparency, tamper-proofness, and reproducibility. Only the mathematical certainty of causal AI can satisfy all four.

> K9 Audit is not about solving our puzzle. It is about finally solving yours.

*Statistical AI moves fast. Causal AI makes sure it doesn't go off the rails — and when it does, the evidence is ironclad.*

*AI coding agent wrote broken code? K9 alerts at the moment of write, delivers root cause within 100ms, and supports one-command tracing even if you missed the alert. From minutes of investigation to seconds of pinpointing.*

---

## Contents

- [Why causal auditing](#why-causal-auditing)
- [A real incident](#a-real-incident)
- [What K9 Audit is](#what-k9-audit-is)
- [What K9 Audit is not](#what-k9-audit-is-not)
- [How K9 Audit differs](#how-k9-audit-differs)
- [Installation](#installation)
- [Works with](#works-with)
- [Quick start](#quick-start)
- [Constraint syntax reference](#constraint-syntax-reference)
- [AI coding agent bug tracing](#ai-coding-agent-bug-tracing)
- [Querying the Ledger directly](#querying-the-ledger-directly)
- [CLI reference](#cli-reference)
- [Real-time audit alerts](#real-time-audit-alerts)
- [Architecture](#architecture)
- [FAQ](#faq)
- [The K9 Hard Case Challenge](#the-k9-hard-case-challenge)
- [Ledger format](#ledger-format)
- [License](#license)

---

## Why causal auditing

K-9. The police dog. It doesn't clock out.

A K-9 unit doesn't file a report saying "there is a 73% probability this person committed a crime." It tracks, detects, alerts — and puts everything on record. That's K9 Audit. It lives on your machine, watches every agent action, and produces a tamper-proof causal record that can withstand forensic scrutiny.

Most observability tools give you a flat timeline. They tell you what happened — but not why an action was wrong, and not where the logical deviation actually started. When a multi-step agent goes wrong, engineers spend hours sifting through walls of text trying to find where tainted data entered the chain.

K9 Audit turns that forensic archaeology into a graph traversal. Because every record in the CIEU Ledger is linked through data flow and temporal dependencies, debugging an AI agent no longer requires manual reading. What used to take hours of log archaeology now takes a single terminal command.

Your agents work for you. K9 Audit makes sure that's actually true.

---

## A real incident

On March 4, 2026, during a routine quant backtesting session, Claude Code attempted three times to write a staging environment URL into a production config file:

```json
{"endpoint": "https://api.market-data.staging.internal/v2/ohlcv"}
```

Because the syntax was valid, no error was thrown. A conventional logger would have buried this silently in a text file — quietly corrupting every subsequent backtest result.

Here is how K9 Audit traced the root cause using the Ledger immediately:

```
k9log trace --last

seq=451  2026-03-04 16:59:22 UTC

─── X_t  Context ──────────────────────────────────
  agent:    Claude Code  (session: abc123)
  action:   WRITE

─── U_t  What happened ────────────────────────────
  skill:    _write_file
  target:   quant_backtest/config.json
  content:  {"endpoint": "https://api.market-data.staging.internal/..."}

─── Y*_t  Intent Contract ─────────────────────────
  constraint: deny_content → ["staging.internal"]
  source:     intents/write_config.json

─── Y_t+1  Outcome ────────────────────────────────
  status:   recorded  (executed with silent deviation)

─── R_t+1  Assessment ─────────────────────────────
  passed:   false
  severity: 0.9
  finding:  content contains forbidden pattern "staging.internal"
  causal_proof: root cause traced to step #451, chain intact

→  Three attempts. 41 minutes apart. All recorded.
```

---

## What K9 Audit is

Every action monitored by K9 Audit produces a **CIEU record** — a rigorously structured five-tuple written into the causal evidence ledger:

| Field | Symbol | Meaning |
|---|---|---|
| Context | `X_t` | Who acted, when, and under what conditions |
| Action | `U_t` | What the agent actually executed |
| Intent Contract | `Y*_t` | What the system expected the agent to do |
| Outcome | `Y_t+1` | What actually resulted |
| Assessment | `R_t+1` | How far the outcome diverged from intent, and why |

This is a fundamentally different category of infrastructure: **tamper-evident causal evidence**.

→ [Full CIEU record specification](./docs/CIEU_spec.md)

---

## What K9 Audit is not

- Not an interception or firewall system *(Phase 1: zero-disruption observability only)*
- Not an LLM-as-judge platform — it consumes zero tokens
- Not a source of agent crashes or execution interruptions

In this phase, K9 Audit does one thing perfectly: turn hard-to-trace AI deviations into traceable, verifiable mathematics. Record, trace, verify, report. The evidence layer that everything else can be built on top of.

---

## How K9 Audit differs

Other observability tools work like expensive cameras. K9 Audit works like an automated forensic investigator.

| | K9 Audit | Mainstream tools (LangSmith / Langfuse / Arize) |
|---|---|---|
| Core technology | Causal AI, deterministic tracking | Generative AI, probabilistic evaluation |
| Data structure | Hash-chained causal evidence ledger | Flat timeline / trace spans |
| Troubleshooting | Commands, not hours | Hours of manual log reading |
| Data location | Fully local, never uploaded | Cloud SaaS or partial upload |
| Tamper-proofness | SHA256 cryptographic chain | Depends entirely on server trust |
| Audit cost | Zero tokens, zero per-event billing | Per-event / per-seat API billing |

---

## Installation

```bash
pip install k9audit-hook
```

The PyPI package is `k9audit-hook`. Once installed, the import name is `k9log`:

```python
from k9log import k9, set_agent_identity  # correct
```

**Windows (one-step setup including Claude Code hook registration):**

```powershell
.\Install-K9Solo.ps1
```

---

## Works with

| Tool | Type | Setup |
|---|---|---|
| **Claude Code** | AI coding agent | [Zero-config hook →](./docs/integrations.md#claude-code) |
| **Cursor** | AI coding editor | [Decorator setup →](./docs/integrations.md#cursor) |
| **LangChain** | Agent framework | [Callback handler →](./docs/integrations.md#langchain) |
| **AutoGen** | Multi-agent framework | [Function wrapper →](./docs/integrations.md#autogen) |
| **CrewAI** | Agent framework | [Tool wrapper →](./docs/integrations.md#crewai) |
| **OpenClaw** | Skill framework | [Module-level wrap →](./docs/integrations.md#openclaw) |
| **Any Python agent** | — | [One decorator →](./docs/integrations.md#any-python-agent) |

---

## Quick start

### Option 1: Claude Code — zero-config hook (recommended)

Drop a `.claude/settings.json` at your project root. Every Claude Code tool call is automatically recorded — no changes to your code or prompts.

```json
{
  "hooks": {
    "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "python -m k9log.hook"}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "python -m k9log.hook_post"}]}]
  }
}
```

The `PostToolUse` hook also parses **K9Contract** blocks from any `.py` file Claude Code writes, and saves them automatically — so the next time that function is called, constraints are enforced with no decorator needed.

→ [K9Contract format and rules](./AGENTS.md)

### Option 2: Python decorator (non-invasive tracing)

```python
from k9log.core import k9
import json

@k9(
    deny_content=["staging.internal"],
    allowed_paths=["./project/**"]
)
def write_config(path: str, content: dict) -> bool:
    # Your existing code remains completely unchanged
    with open(path, 'w') as f:
        json.dump(content, f)
    return True
```

Every call now automatically writes a CIEU record to the Ledger. If the agent violates a constraint, execution continues — but a high-severity deviation is permanently flagged in the chain.

### Option 3: Intent contract file (decoupled rules)

File: `~/.k9log/intents/write_config.json`

```json
{
  "skill": "write_config",
  "constraints": {
    "deny_content": ["staging.internal", "*.internal"],
    "allowed_paths": ["./project/**"],
    "action_class": "WRITE"
  }
}
```

### Option 4: LangChain callback handler

For agents built with LangChain — zero changes to your chain or agent logic:

```python
from k9log.langchain_adapter import K9CallbackHandler

handler = K9CallbackHandler()

# Works with agents, chains, or individual tools
agent = initialize_agent(tools, llm, callbacks=[handler])
chain = LLMChain(llm=llm, prompt=prompt, callbacks=[handler])
```

Every tool call automatically writes a CIEU record. Constraint violations are detected at `on_tool_start` (pre-execution) and the outcome is recorded at `on_tool_end` / `on_tool_error`. No decorator or hook configuration needed.

→ [Integration guides: Cursor, AutoGen, CrewAI, OpenClaw, and more](./docs/integrations.md)

---

## Constraint syntax reference

`@k9` accepts two kinds of arguments:

**Global constraints** — apply across all parameters:

| Argument | Type | What it checks |
|---|---|---|
| `deny_content=["term"]` | list of strings | Fails if any parameter value contains any listed term (case-insensitive substring match) |
| `allowed_paths=["./src/**"]` | list of glob patterns | Fails if any path-like parameter points outside the listed directories |

**Per-parameter constraints** — keyed by the exact parameter name:

| Constraint key | Example | What it checks |
|---|---|---|
| `max` | `amount={'max': 1000}` | Value must not exceed this number |
| `min` | `amount={'min': 0}` | Value must not be below this number |
| `max_length` | `query={'max_length': 500}` | String length must not exceed this |
| `min_length` | `name={'min_length': 1}` | String length must be at least this |
| `blocklist` | `env={'blocklist': ['prod']}` | Value must not equal or contain any listed term |
| `allowlist` | `status={'allowlist': ['ok','fail']}` | Value must be one of the listed options |
| `enum` | `level={'enum': [1,2,3]}` | Value must be exactly one of the listed values |
| `regex` | `email={'regex': r'.+@.+'}` | Value must match this regular expression |
| `type` | `count={'type': 'integer'}` | Value must be this type (`string`, `integer`, `float`, `boolean`, `list`, `dict`) |

**Full example:**

```python
@k9(
    deny_content=["staging.internal", "DROP TABLE"],
    allowed_paths=["./project/**"],
    amount={'max': 10000, 'min': 0},
    recipient={'blocklist': ['re:.*@untrusted\\..*']},  # regex prefix re:
    env={'enum': ['dev', 'staging']},
    query={'max_length': 500, 'regex': r'^[a-zA-Z0-9 ]+$'}
)
def process(amount: float, recipient: str, env: str, query: str) -> dict:
    ...
```

Constraints can also be stored in `~/.k9log/config/<function_name>.json` to keep them out of your source code. The decorator takes priority over the config file if both exist.

**Custom constraint types**

If the built-in types above don't cover your use case, register your own:

```python
from k9log.constraints import register_constraint

@register_constraint("allowed_domains")
def check_allowed_domains(param_name, value, rule_value):
    domain = str(value).split("@")[-1]
    if domain not in rule_value:
        return {
            'type': 'domain_violation',
            'field': param_name,
            'severity': 0.9,
            'message': f'{param_name} domain {domain!r} not in allowed list'
        }
    return None  # no violation

@k9(recipient={'allowed_domains': ['company.com', 'partner.org']})
def transfer(amount, recipient):
    ...
```

**Important:** `register_constraint` is process-scoped — registrations live only for the current Python process. To make custom constraints available everywhere, create a `k9_plugins.py` file at your project root and import it at agent startup:

```python
# k9_plugins.py  — import this once at startup
from k9log.constraints import register_constraint

@register_constraint("allowed_domains")
def check_allowed_domains(param_name, value, rule_value):
    ...
```

```python
# agent_main.py or your entry point
import k9_plugins  # registers all custom constraints
from myagent import run
run()
```

20 minutes of log archaeology → 10 seconds with `k9log causal --last`.

→ [Real case: how K9 traced a missing import through 3 steps](./docs/causal_tracing.md)

---

## Querying the Ledger directly

The Ledger is a plain JSONL file — one record per line. You can query it directly from Python without any special API:

```python
import json
from pathlib import Path

ledger = Path.home() / ".k9log" / "logs" / "k9log.cieu.jsonl"
records = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]

# All violations
violations = [r for r in records if not r.get("R_t+1", {}).get("passed", True)]

# Filter by severity threshold
critical = [r for r in violations if r.get("R_t+1", {}).get("overall_severity", 0) >= 0.8]

# Filter by skill name
write_violations = [r for r in violations if r.get("U_t", {}).get("skill") == "write_file"]

# Export for team review or CI artifact
with open("violations_report.json", "w") as f:
    json.dump(violations, f, indent=2, default=str)

print(f"{len(violations)} violations total, {len(critical)} critical")
```

On Windows the path is `C:\Users\<username>\.k9log\logs\k9log.cieu.jsonl`.

---

## CLI reference

```bash
k9log stats                    # display Ledger summary
k9log trace --step 451         # instantly trace the root cause of a specific event
k9log trace --last             # analyze the most recent deviation
k9log causal --last            # causal chain analysis: auto-detect and find root cause
k9log causal --step 7          # causal chain analysis for a specific step
k9log verify-log               # verify full SHA256 hash chain integrity
k9log verify-ystar             # verify intent contract coverage across all skills
k9log report --output out.html # generate an interactive causal graph report
k9log health                   # system health check: ledger + integrity + coverage
k9log alerts status            # show alerting channel status
```

**`k9log health`** shows a skill coverage table. Skills marked `UNCOVERED` are being recorded but have no constraints — violations in those skills will be logged but not flagged. To fix, add a `@k9(...)` decorator to the function, or create `~/.k9log/config/<skill_name>.json` with your constraints. Skills marked `PARTIAL` have constraints on some calls but not all — check for code paths that bypass the decorator.

**`k9log verify-log`** outputs a `Chain integrity: OK` confirmation plus the total record count and the final hash. A clean result means no record has been silently modified since it was written. Run it before sending a report to a client, auditor, or compliance reviewer — it is cryptographic proof the evidence has not been tampered with.

**`k9log report --output out.html`** generates a self-contained HTML file with an interactive causal graph, full CIEU record table, and violation summary. Share it with a team lead for post-incident review, attach it to a compliance audit, or send it to a client as evidence that agent actions were monitored and recorded.

**CI/CD gate: failing a pipeline on violations**

`k9log` commands currently always return exit code 0. To fail a CI pipeline when critical violations exist, use the Python query pattern:

```python
# ci_check.py — run after your agent job
import json, sys
from pathlib import Path

ledger = Path.home() / ".k9log" / "logs" / "k9log.cieu.jsonl"
if not ledger.exists():
    print("No ledger found — was K9 running?")
    sys.exit(1)

records = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
critical = [
    r for r in records
    if not r.get("R_t+1", {}).get("passed", True)
    and r.get("R_t+1", {}).get("overall_severity", 0) >= 0.8
]

if critical:
    print(f"K9 AUDIT FAILED: {len(critical)} critical violation(s)")
    for r in critical:
        print(f"  seq={r.get('_integrity',{}).get('seq','?')} "
              f"skill={r.get('U_t',{}).get('skill','?')} "
              f"severity={r.get('R_t+1',{}).get('overall_severity','?')}")
    sys.exit(1)

print(f"K9 AUDIT PASSED: {len(records)} records, no critical violations")
sys.exit(0)
```

Call `python ci_check.py` as the last step in your pipeline. Exit code 1 = violations found, 0 = clean.

---

## Real-time audit alerts

K9 Audit can push a structured CIEU alert the moment a deviation is written to the Ledger — milliseconds before you would ever think to investigate manually.

Every alert is a CIEU five-tuple, not a raw event ping. The goal is not just to tell you something happened. It is to make you fluent in reading causal evidence. A second message follows automatically 100ms later with the causal chain trace and root cause.

Configure your alert channel with a single command — no config file editing needed:

```bash
# Telegram
k9log alerts set-telegram --token YOUR_BOT_TOKEN --chat-id YOUR_CHAT_ID

# Slack
k9log alerts set-slack --webhook-url https://hooks.slack.com/services/...

# Discord
k9log alerts set-discord --webhook-url https://discord.com/api/webhooks/...

# Custom webhook
k9log alerts set-webhook --url https://your-endpoint.example.com/k9alert

# Enable / disable the whole system
k9log alerts enable
k9log alerts disable

# Check current status
k9log alerts status

# Configure Do Not Disturb (e.g. 11pm–8am UTC+8)
k9log alerts set-dnd --start 23:00 --end 08:00 --offset 8
```

Each `set-*` command writes the credential directly to `~/.k9log/alerting.json` and enables that channel immediately.

---

## Architecture

```
k9log/
├── core.py              ← @k9 decorator, non-invasive Ledger writer
├── logger.py            ← hash-chained Ledger persistence
├── tracer.py            ← incident trace: full CIEU five-tuple display
├── causal_analyzer.py   ← causal DAG traversal and root cause analysis
├── verifier.py          ← cryptographic chain integrity verification
├── constraints.py       ← Y*_t intent contract loader and checker
├── redact.py            ← automatic sensitive data masking
├── report.py            ← HTML causal graph report generator
├── cli.py               ← command-line interface
├── alerting.py          ← real-time CIEU deviation alerts
├── identity.py          ← agent identity and session capture
├── hook.py              ← Claude Code PreToolUse adapter
├── hook_post.py         ← Claude Code PostToolUse + K9Contract extractor
├── autocontract.py      ← zero-decorator contract injection via sys.meta_path
├── langchain_adapter.py ← LangChain callback handler
├── openclaw.py          ← module-level batch wrapping (k9_wrap_module)
├── agents_md_parser.py  ← AGENTS.md / CLAUDE.md rule parser
└── governance/          ← action class registry (READ/WRITE/DELETE/EXECUTE/…)
```

**Sensitive data masking (`redact.py`)**

By default, K9 Audit runs in `standard` redaction mode. Parameter names matching common sensitive patterns (`password`, `token`, `api_key`, `secret`, `credit_card`, `ssn`, and others) are automatically masked before being written to the Ledger — the value is replaced with `[REDACTED]`.

Control the redaction level via environment variable:

```bash
K9LOG_REDACT_LEVEL=off      # no masking — full params stored
K9LOG_REDACT_LEVEL=standard # default — mask known sensitive param names
K9LOG_REDACT_LEVEL=strict   # mask all string values longer than 50 chars
```

Or set it permanently in `~/.k9log/redact.json`:

```json
{ "level": "standard" }
```

`strict` mode is recommended for agents handling PII, medical records, or financial data.

---

## FAQ

**Will this slow down my agent?**

No. `@k9` is a pure Python decorator that performs one synchronous write to the local Ledger before and after each function call. Measured latency per audit is in the microsecond range — imperceptible to normal agent execution.

**What happens to my agent when a deviation is detected?**

In this phase, K9 Audit is designed for zero-disruption observability. Deviations are flagged in the Ledger with a high severity score and trigger real-time alerts. Your agent's execution is never blocked or interrupted. You get complete visibility without sacrificing continuity.

**Where is the Ledger stored, and how large does it get?**

Records are written to `~/.k9log/logs/k9log.cieu.jsonl` — one JSON object per line, hash-chained, UTF-8 encoded. Each CIEU record is approximately 500 bytes. Ten thousand records occupy roughly 5MB. Run `k9log verify-log` at any time to verify chain integrity.

On Windows, `~` resolves to `C:\Users\<your-username>`, so the full path is `C:\Users\<your-username>\.k9log\logs\k9log.cieu.jsonl`.

---

## The K9 Hard Case Challenge

Bring a traceability problem that has been genuinely hard to debug. Solve it with K9 Audit. Show us what changes when troubleshooting shifts from reading text logs to querying a causal graph.

We are looking for proof that K9 can resolve deep-chain agent deviations that would otherwise take hours to untangle. The best submissions become part of the **Solved Hard Cases** gallery.

→ [See the challenge](./challenge/README.md)

---

## Ledger format

Records are written to `~/.k9log/logs/k9log.cieu.jsonl` — one JSON object per line, hash-chained, UTF-8 encoded.

Full cryptographic and DAG structure specification: [docs/CIEU_spec.md](./docs/CIEU_spec.md)

---

## Patent Notice

The CIEU architecture is covered by U.S. Provisional Patent Application No. 63/981,777:
*"Causal Intervention-Effect Unit (CIEU): A Universal Causal Record Architecture for Audit and Governance of Arbitrary Processes"*

Users of K9log under AGPL-3.0 receive patent rights per AGPL-3.0 Section 11.
For commercial licensing, contact: liuhaotian2024@gmail.com — see [PATENTS.md](./PATENTS.md).

## License

AGPL-3.0. See [LICENSE](./LICENSE).

Copyright (C) 2026 Haotian Liu

