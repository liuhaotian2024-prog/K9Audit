# K9Audit Skill

## When to use this skill

Use this skill when the user:
- Asks to audit agent behavior or actions
- Wants to know if Claude Code violated any constraints during a session
- Asks "what did the agent do?" or "did the agent follow the rules?"
- Wants to verify the integrity of a CIEU audit ledger
- Asks about causal tracing of agent actions
- Wants to instrument their Claude Code session with audit hooks
- Mentions K9Audit, CIEU, or causal audit

## What K9Audit does

K9Audit is causal audit infrastructure for AI agents. It hooks into Claude Code via `PreToolUse` and `PostToolUse` to record every action as a **CIEU five-tuple**:

```
(timestamp, action U_t, intent_contract Y*_t, observed_effect R_t+1, sha256_hash)
```

The critical field is **Y\*_t** — the intent contract at the time of the action. This is what the agent was *supposed* to do. The gap between Y\*_t and U_t is the violation.

No other tool records Y\*_t. This is what makes K9Audit different from LangSmith, Langfuse, or any logger.

## Installation

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

## Key commands

```bash
k9log verify-log          # verify hash chain integrity
k9log stats               # violation summary
k9log trace --last        # causal trace of last violation
k9log report --output report.html  # full HTML report
```

## Verified cases

**Case #002 — Read-Then-Write**: An agent read `CONSTRAINTS.md`. Ten seconds later it attempted to write the exact file that document declared off-limits — three times. A filesystem diff shows nothing happened. The CIEU chain shows exactly what the agent saw before it acted.

Reproduce: `python k9_case002_replay.py` → `k9log verify-log`

**Case #004 — Repository Residue Audit**: K9Audit audits its own repository for AI agent iteration residue — files that should have been cleaned up but were not. Records both detection and cleanup as a single verifiable causal chain.

Reproduce: `python k9_repo_audit.py .` → `python k9_repo_cleanup.py .` → `k9log verify-log`

## Repository

https://github.com/liuhaotian2024-prog/K9Audit

## License

AGPL-3.0 | US Provisional Patent 63/981,777
