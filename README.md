# K9Audit — Causal Audit Plugin for Claude Code

> Answers a question no logger can: **"Did the agent see the constraint before it violated it?"**

K9Audit hooks into Claude Code via `PreToolUse`/`PostToolUse` and records every action as a CIEU (Causal Intervention-Effect Unit) five-tuple — including **Y\*_t**, the agent's intent contract at the time of action. Fully local, zero upload, cryptographic hash chain.

## Install

```bash
pip install k9audit-hook
```

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [{"type": "command", "command": "k9log hook-pre"}]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [{"type": "command", "command": "k9log hook-post"}]
      }
    ]
  }
}
```

## Use

```bash
/k9-audit              # audit current repo for residue violations
k9log verify-log       # verify hash chain integrity  
k9log stats            # violation summary
k9log trace --last     # causal trace of last violation
```

## What makes K9Audit different

Every other observability tool records **what the agent did**. K9Audit also records **what the agent was supposed to do** (Y\*_t intent contract). The gap is the violation — causally traceable, cryptographically verifiable, fully local.

| Tool | Records actions | Records intent contract | Causal chain |
|---|---|---|---|
| LangSmith / Langfuse | ✅ | ❌ | ❌ |
| Arize / Weave | ✅ | ❌ | ❌ |
| **K9Audit** | ✅ | ✅ | ✅ |

## Real verified case

An agent read `CONSTRAINTS.md`. Ten seconds later it attempted to write the exact file that document declared off-limits — three times, across two projects. A filesystem diff shows nothing happened. The CIEU chain shows exactly what the agent saw before it acted.

Reproduce from scratch:
```bash
python k9_case002_replay.py
k9log verify-log
```

## Repository

**https://github.com/liuhaotian2024-prog/K9Audit**

License: AGPL-3.0 | US Provisional Patent 63/981,777
