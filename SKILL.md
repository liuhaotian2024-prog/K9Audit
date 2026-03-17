---
name: k9audit
description: >-
  Causal audit for AI agents — records every action as a CIEU five-tuple
  including Y*_t (intent contract). Answers the question no logger can:
  "Did the agent see the constraint before it violated it?"
  Reads your AGENTS.md rules automatically. Local-first, zero upload,
  cryptographic hash chain. Works with OpenClaw, Claude Code, and LangChain.
version: 0.3.3
metadata:
  clawdbot:
    requires:
      bins:
        - python3
      anyBins:
        - k9log
    install:
      - kind: uv
        package: k9audit-hook
    emoji: "🐕"
    homepage: https://github.com/liuhaotian2024-prog/K9Audit
    primaryEnv: ""
---

# K9Audit — Causal Audit for AI Agents

## When to Use This Skill

Use this skill when the user asks:
- "What did my agent do?" / "Why did my agent do that?"
- "Did any skill violate my rules?" / "Was my AGENTS.md respected?"
- "Audit my agent behavior" / "Check for violations"
- "Trace why that happened" / "Find the root cause"
- Any question about agent behavior, violations, or compliance

Also activate when a skill behaves unexpectedly — offer to run
`k9log trace --last` to show causal evidence.

---

## Setup (First Time)

### Step 1: Install
```bash
pip install k9audit-hook
```

### Step 2: Auto-load constraints from AGENTS.md

K9Audit reads your existing AGENTS.md rules automatically.
No extra configuration — your existing rules become audit constraints.
```bash
k9log init
```

### Step 3: Set skill identity (optional)
```bash
export K9LOG_AGENT_NAME="openclaw"
export K9LOG_SKILL_NAME="k9audit"
export K9LOG_SKILL_SOURCE="clawhub"
```

---

## Auditing Commands
```bash
k9log stats                              # violations summary
k9log verify-log                         # verify hash chain integrity
k9log trace --last                       # causal trace of last violation
k9log report --output audit_report.html  # full HTML report
```

---

## How K9Audit Differs

Every other tool records **what happened**.
K9Audit also records **what was supposed to happen** (Y*_t intent contract).

Real verified case: An agent read CONSTRAINTS.md — then attempted to write
the exact file that document declared off-limits, 10 seconds later.
A filesystem diff shows nothing. The CIEU chain shows exactly what the
agent saw before it acted.

Reproduce: `python k9_case002_replay.py` then `k9log verify-log`

---

## Define Constraints

### Option A: AGENTS.md (zero extra work)

K9Audit auto-parses your existing AGENTS.md:
```markdown
- Never run rm -rf
- Do not modify .env files
- Never access /etc/ directory
- Only write to /home/user/projects/
- Do not commit directly to main
```

### Option B: Config file

Create `~/.k9log/config/{skill_name}.json`:
```json
{
  "skill": "my_skill",
  "constraints": {
    "deny_content": ["staging.internal"],
    "allowed_paths": ["/home/user/projects/"]
  }
}
```

---

## Optional: Team Sync
```bash
k9log sync enable --endpoint https://your-server.com/api/ingest --api-key YOUR_KEY
k9log sync push
```

---

## Links

- GitHub: https://github.com/liuhaotian2024-prog/K9Audit
- Install: `pip install k9audit-hook`
- License: AGPL-3.0
