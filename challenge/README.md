# K9 Hard Case Challenge

**Bring a traceability problem that has been painfully hard. Solve it with K9 Audit. Show what became possible.**

This is not a quiz. There are no pre-designed questions, no standard answers, no leaderboard.

The K9 Hard Case Challenge is a open record of problems that were genuinely difficult to trace — and are now genuinely solved. The best submissions become part of the **Solved Hard Cases** gallery.

---

## What we are looking for

Three things, all of them concrete:

1. **The problem was genuinely hard.** Not a toy example. Something that would have taken real time and produced uncertain conclusions without K9 Audit.

2. **K9 actually contributed.** The CIEU five-tuple, the trace output, or the causal structure materially changed the conclusion or the time to reach it.

3. **The finding is independently verifiable.** Someone with the same input and K9 Audit should be able to reproduce the same conclusion.

---

## A reference case: Incident #001

To show you what a solved hard case looks like, here is a real one.

**Staging Endpoint Injection** — March 4, 2026

During a routine quant backtesting session, Claude Code attempted three times to write a staging environment URL into a production config file. The attempts occurred across 41 minutes. The developer had no idea it was happening.

If the writes had gone through: all backtest results would have been silently corrupted — wrong data source, no error thrown, no way to detect.

**Try it yourself:**

```bash
# K9 track — full causal evidence
k9log trace --step 451   # first attempt
k9log trace --step 455   # second attempt
k9log trace --step 456   # third attempt
```

**Files included:**
- `challenge_logs.jsonl` — raw operation log
- `cieu_session.jsonl` — full CIEU audit log

**Four approaches, same incident:**

| Approach | Tools available |
|----------|----------------|
| Manual | text editor + grep only |
| Traditional SIEM | Splunk / ELK / similar |
| AI-assisted | ChatGPT / Claude / similar |
| K9 Audit | `k9log trace`, full CIEU log |

Run all four. Compare the time, the certainty of the conclusion, and the quality of the evidence. Then bring your own hard case.

---

## How to bring your own hard case

Not sure how to get your problem into K9? Here are the three entry points:

**Path A — You use Claude Code (zero code change)**

Drop `.claude/settings.json` at your project root and start a new Claude Code session. K9 records every tool call automatically. Reproduce the problematic behavior, then:

```bash
k9log health          # confirm recording is active
k9log trace --last    # see the last deviation
k9log causal --last   # trace the root cause chain
k9log report --output my_case.html
```

**Path B — You have a Python agent or tool function**

Wrap the relevant function with `@k9` and reproduce the problem:

```python
from k9log import k9, set_agent_identity

set_agent_identity(agent_name='MyAgent')

@k9(
    # add constraints that should have been enforced:
    deny_content=["prod", "production"],
    allowed_paths=["./safe_dir/**"],
)
def the_function_that_misbehaved(path: str, content: str) -> bool:
    ...  # your existing code unchanged
```

Run your agent. Then: `k9log trace --last` and `k9log causal --last`.

**Path C — You have existing logs from a past incident**

K9 can ingest structured event logs and reconstruct a CIEU ledger. If your logs are in JSON format (one event per line), map the fields:

```python
import json
from k9log.logger import get_logger
from k9log.identity import set_agent_identity

set_agent_identity(agent_name='PostMortem')
logger = get_logger()

# Read your existing log
with open('my_incident_log.jsonl') as f:
    for line in f:
        event = json.loads(line)
        # Map your fields to CIEU five-tuple
        record = {
            'timestamp': event['ts'],
            'X_t': {'agent_name': event.get('actor', 'unknown'), 'session_id': 'import'},
            'U_t': {'skill': event['action'], 'params': event.get('params', {})},
            'Y_star_t': {'constraints': {}, 'y_star_meta': {'unconstrained': True}},
            'Y_t+1': {'status': 'success' if event.get('exit_code', 0) == 0 else 'error',
                      'result': event.get('output', '')},
            'R_t+1': {'passed': event.get('exit_code', 0) == 0,
                      'violations': [], 'overall_severity': 0.0, 'risk_level': 'LOW'},
        }
        logger.write_cieu(record)

print("Import complete. Now run: k9log causal --last")
```

---

## Submit your case

One case per submission. Use this template.

---

### 1. Case title

One sentence. What was the problem?

Examples:
- A multi-step agent workflow that completed successfully but violated its declared scope
- A CI/CD pipeline failure where responsibility was genuinely unclear across three tools
- An AI agent that drifted from its task across 20 steps with no single error raised
- A config change that silently corrupted downstream results for three days

---

### 2. Why was it hard before K9 Audit?

What made this problem resistant to ordinary tools? Be specific.

Common patterns:
- Logs were fragmented across multiple systems with no unified timeline
- The root cause and the surface symptom were separated by many steps
- Responsibility was genuinely unclear — multiple actors, no clear owner
- The process appeared to succeed while hiding a deviation
- Reconstruction required hours of manual correlation
- The deviation was only detectable in retrospect, not at the time it occurred

---

### 3. What did you feed into K9 Audit?

What was the input material?

Examples: shell logs, tool traces, JSON event stream, agent run logs, CI/CD pipeline records, workflow execution logs, custom adapter output.

---

### 4. What did K9 Audit reveal?

This is the core of the submission. Structure your answer as a CIEU reading:

- **X_t** — Who was the actor? What was the context?
- **U_t** — What did they actually do?
- **Y\*_t** — What were they supposed to do? What was the intent contract?
- **Y_t+1** — What was the outcome?
- **R_t+1** — What was the deviation? Where did it start? What was its severity?

If the answer was already visible in the raw logs, explain why the CIEU formulation is clearer, more defensible, or faster to reach.

---

### 5. What changed compared with the old approach?

Quantify where you can:

- Time: 4 hours → 12 minutes
- Certainty: "we think it was X" → "here is the causal chain with hash-verified evidence"
- Scope: "something went wrong" → "step 34, actor Y, deviation type Z, severity 0.9"
- Reproducibility: can the finding be independently verified from the CIEU log?

---

### 6. Attachments (optional)

- Raw log fragment
- CIEU log fragment
- `k9log trace` output
- `k9log report` output
- Before / after comparison

---

## The Solved Hard Cases gallery

Accepted submissions are added to the gallery. Each case is presented as:

- **Title** — the problem in one sentence
- **Before K9** — why it was hard
- **What K9 revealed** — the CIEU-structured finding
- **Impact** — what changed, measured

The gallery is not a ranking. It is a record of what became possible.

---

## How to submit

Open a GitHub issue with the label `hard-case` and paste the template above.

---

## Questions

**Do I need to use Claude Code specifically?**
No. K9 Audit works with any system you can pipe events from. The `@k9` decorator, the CLI ingestion tool, and the generic JSON adapter all produce CIEU records from any source.

**Can I submit a case from a proprietary system?**
Yes. Redact sensitive fields before submitting. K9 Audit has built-in redaction — see `k9log/redact.py`.

**What if the K9 finding matches what I already knew?**
Still valid, if K9 reached the same conclusion faster, with better evidence, or with independently verifiable proof. Speed and verifiability both count.

**What if K9 found nothing?**
That is a result too. A submission showing that K9 correctly found no deviation when other tools were ambiguous is equally useful.
