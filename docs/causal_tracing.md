# AI Coding Agent Bug Tracing

> "I was afraid there would be bugs everywhere. Turns out there were only 3,
> and the causal chain found them all." — K9Audit developer, March 2026

## The problem every developer hits

You ask an AI coding agent to help build a feature. It writes dozens of files,
runs tests, iterates. Then something breaks. You spend 20 minutes reading
terminal output, grepping files, guessing which step introduced the bug.

This is not a rare edge case. It happens every session.

## What K9 Audit does instead

Every tool call Claude Code makes — every `Write`, `Edit`, `Bash` — is
recorded as a CIEU record with full intent and outcome. When a test fails,
one command traces the root cause:
```
k9log causal --last
```

## Real case: missing `import logging` in report.py

During K9Audit development on March 8, 2026, Claude Code wrote `report.py`
with `logging.info()` calls but forgot `import logging`. The file was written
successfully (exit code 0). The bug only surfaced three steps later when the
test runner crashed with:
```
NameError: name 'logging' is not defined
```

Traditional debugging: grep files, check git diff, read terminal output — ~20 minutes.

K9 Audit:
```
$ k9log causal --last

Auto-detected failure at Step #2

Causal Chain Analysis — Incident: Step #2
├── Root Causes
│   └── Step #1 - Write (report.py)  (confidence: 85%)
│       ├── Written content uses "logging" but missing import/definition.
│       │   Error propagated to Step #2.
│       └── Missing: import logging
└── Full Causal Chain
    ├── Depth 0 — EXEC_FAIL  Step #2 - Bash (python test_report.py)
    ├── Depth 1 — OK         Step #1 - Write (report.py)
    └── Depth 2 — OK         Step #0 - Write (utils.py)

Chain length: 3 steps | Depth: 2
```

Time to root cause: **under 10 seconds**.

## How it works
```
Claude Code writes report.py     → PreToolUse  hook → CIEU record (U_t)
File written successfully        → PostToolUse hook → CIEU record (Y_t+1, exit_code=0)
Claude Code runs test_report.py  → PreToolUse  hook → CIEU record (U_t)
Test crashes: NameError logging  → PostToolUse hook → CIEU record (Y_t+1, exit_code=1)

k9log causal --last
  → Scans ledger for most recent failure
  → Builds causal DAG (temporal + data flow edges)
  → Strategy 3: extracts "logging" from NameError
  → Finds Write step using "logging" without "import logging"
  → Outputs root cause with 85% confidence
```

## Setup for Claude Code

Add to `.claude/settings.json`:
```json
{
  "hooks": {
    "PreToolUse":  [{"matcher": "*", "hooks": [{"type": "command", "command": "python -m k9log.hook"}]}],
    "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "python -m k9log.hook_post"}]}]
  }
}
```

That is the entire setup. Every subsequent Claude Code session is
automatically recorded and traceable.
