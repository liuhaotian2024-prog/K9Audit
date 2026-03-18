---
name: k9audit
description: >-
  Causal audit for AI agents — records every OpenClaw tool call as a CIEU
  five-tuple including Y*_t (intent contract). Answers the question no logger
  can: "Did the agent see the constraint before it violated it?"
  Reads your AGENTS.md rules automatically. Local-first, zero upload,
  cryptographic hash chain. Zero code changes needed — installs as a
  background watcher.
version: 0.3.3
metadata:
  clawdbot:
    requires:
      bins:
        - python3
    install:
      - kind: uv
        package: k9audit-hook
    emoji: "🐕"
    homepage: https://github.com/liuhaotian2024-prog/K9Audit
    primaryEnv: ""
---

# K9Audit — Causal Audit for OpenClaw Agents

## When to Use This Skill

Use this skill when the user asks:
- "What did my agent do?" / "Why did my agent do that?"
- "Did any skill violate my rules?" / "Was my AGENTS.md respected?"
- "Show me violations" / "Audit my agent"
- "Trace why that happened" / "Find the root cause"
- "Set up K9Audit" / "Install the auditor"

Also activate when a skill behaves unexpectedly — offer to run
`k9log trace --last` to show the causal evidence chain.

---

## First-Time Setup (One Command)

Run this once to install K9Audit and start automatic monitoring:

```bash
bash {baseDir}/skills/k9audit/setup.sh
```

This script:
1. Installs `k9audit-hook` via pip
2. Registers a `gateway:startup` hook so monitoring restarts automatically
3. Starts the background watcher immediately — no gateway restart needed

After setup, **every OpenClaw tool call is automatically recorded**.
No code changes needed in any skill.

---

## How It Works

K9Audit runs a background watcher that monitors OpenClaw's session files:

```
~/.openclaw/agents/*/sessions/*.jsonl
```

Every time OpenClaw writes a `toolCall` entry, K9Audit:
1. Reads your `AGENTS.md` as the intent contract (Y\*_t)
2. Checks the tool call against your constraints
3. Writes a CIEU five-tuple to the tamper-proof ledger

**No PreToolUse hook needed. No code changes in skills. Zero friction.**

---

## Auditing Commands

After setup, use these commands to query the audit ledger:

```bash
k9log stats                              # violation summary
k9log verify-log                         # verify hash chain integrity
k9log trace --last                       # causal trace of last violation
k9log report --output audit_report.html  # full HTML report
```

---

## How Constraints Work

K9Audit automatically reads your existing `AGENTS.md` — no extra config needed.

**Example AGENTS.md (already works with K9Audit):**

```markdown
# My Agent Rules
- Never run rm -rf
- Do not modify .env files
- Never access /etc/ directory
- Only write to ./projects/
- Do not commit directly to main
- Only access api.github.com domain
```

K9Audit parses these rules and enforces them on every tool call.
Any violation is immediately recorded with the full causal chain.

---

## What Makes K9Audit Different

Every other tool records **what happened**.
K9Audit also records **what was supposed to happen** (Y\*_t intent contract).

The gap is the violation — causally traceable, cryptographically verifiable.

**Real verified case**: An agent read `CONSTRAINTS.md` — then attempted to
write the file that document declared off-limits, 10 seconds later.
A filesystem diff shows nothing. The CIEU chain shows exactly what the
agent saw before it acted.

Reproduce: `python k9_case002_replay.py` then `k9log verify-log`

---

## Watcher Management

```bash
# Check watcher status
k9log openclaw-watch status

# Stop watcher
k9log openclaw-watch stop

# Restart watcher
k9log openclaw-watch start
```

---

## Optional: Team Sync

K9Audit is local-first. Ledger stays on your machine by default.
For shared team dashboards:

```bash
k9log sync enable --endpoint https://your-server.com/api/ingest --api-key KEY
k9log sync push
```

---

## Links

- GitHub: https://github.com/liuhaotian2024-prog/K9Audit
- Install: `pip install k9audit-hook`
- License: AGPL-3.0 | US Provisional Patent 63/981,777
