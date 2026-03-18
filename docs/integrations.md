# K9 Audit — Integration Guide

K9 Audit works with any agent framework. Pick your setup below.

---

## Deployment Modes

K9 Audit is local-first, not local-only. Choose the deployment model that fits your needs:

| Mode | Who it's for | Data location |
|------|--------------|---------------|
| **Local** (default) | Individual devs, sensitive projects | Your disk only — no network calls |
| **Encrypted sync** (Phase 2) | Teams wanting shared dashboards | Encrypted before leaving your machine, key is yours |
| **Self-hosted** (Phase 2) | Compliance-driven orgs | Your own Docker / Kubernetes cluster |

The audit ledger is always yours. K9 will never train on your data.

For Phase 2 deployment options, watch the [roadmap](roadmap_phase2.md) or contact liuhaotian2024@gmail.com.

---

## Contents

- [Claude Code](#claude-code)
- [Cursor](#cursor)
- [LangChain](#langchain)
- [AutoGen](#autogen)
- [CrewAI](#crewai)
- [OpenClaw](#openclaw)
- [Any Python Agent](#any-python-agent)

---

## Claude Code

Claude Code exposes `PreToolUse` and `PostToolUse` hooks that fire before and after every tool call. K9 Audit intercepts at this layer — no changes to your prompts or workflow.

**Step 1 — Install:**

```bash
pip install k9audit-hook
```

**Step 2 — Register both hooks** in `.claude/settings.json` at your project root:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [{"type": "command", "command": "python -m k9log.hook"}]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [{"type": "command", "command": "python -m k9log.hook_post"}]
      }
    ]
  }
}
```

Both hooks are required. `PreToolUse` records the intent and checks constraints. `PostToolUse` records the outcome and — if Claude Code wrote a `.py` file containing a `K9Contract` docstring — automatically extracts and saves the contract for future enforcement.

**Note on hook file locations:** The repo contains a `hook.py` at the project root — this is an older standalone copy kept for the `Install-K9Solo.ps1` script. The canonical hooks used by `python -m k9log.hook` and `python -m k9log.hook_post` are inside the `k9log/` package. When using `pip install k9audit-hook`, always use the `-m` form above.

**Step 3 — Verify:**

```bash
k9log health
k9log stats
```

From this point, every Claude Code tool call is recorded in the CIEU Ledger. Violations are flagged automatically and alerts fire in real time.

**Windows one-step setup** (installs dependencies, registers both hooks globally, initializes `~/.k9log`):

```powershell
.\Install-K9Solo.ps1
```

---

## Cursor

Cursor does not expose a native hook layer, but you can audit any tool or
function it calls by wrapping it with `@k9`.

**Step 1 — Install:**

```bash
pip install k9audit-hook
```

**Step 2 — Wrap your tools:**

```python
from k9log import k9, set_agent_identity

set_agent_identity(agent_name='Cursor')

@k9(
    allowed_paths=["./src/**", "./tests/**"],
    deny_content=["staging.internal", "prod-db"]
)
def write_file(path: str, content: str) -> bool:
    with open(path, 'w') as f:
        f.write(content)
    return True
```

**Step 3 — Verify:**

```bash
k9log stats
k9log trace --last
```

---

## LangChain

Wrap any LangChain `Tool` with `@k9`. The decorator is transparent —
LangChain sees the same function signature and return type.

**Step 1 — Install:**

```bash
pip install k9audit-hook
```

**Step 2 — Wrap your tools:**

```python
from langchain.tools import Tool
from k9log import k9, set_agent_identity

set_agent_identity(agent_name='LangChainAgent')

@k9(
    query={'max_length': 500},
    deny_content=["DROP TABLE", "rm -rf"]
)
def search_tool(query: str) -> str:
    # your existing search logic
    return results

# Register with LangChain as usual
tool = Tool(
    name="search",
    func=search_tool,
    description="Search for information"
)
```

Every call to `search_tool` now writes a CIEU record. Your LangChain
agent requires zero other changes.

---

## AutoGen

Same pattern — wrap the function before registering it as a tool.

```python
import autogen
from k9log import k9, set_agent_identity

set_agent_identity(agent_name='AutoGenAgent')

@k9(
    code={"deny_content": ["os.system", "subprocess", "eval("]},
)
def execute_code(code: str) -> str:
    # your existing execution logic
    return output

# Register with AutoGen
autogen.register_function(
    execute_code,
    caller=assistant,
    executor=user_proxy,
    description="Execute Python code"
)
```

---

## CrewAI

Wrap the tool function inside your CrewAI `Tool` definition.

```python
from crewai_tools import BaseTool
from k9log import k9, set_agent_identity

set_agent_identity(agent_name='CrewAIAgent')

@k9(
    file_path={"allowed_paths": ["./output/**"]},
    deny_content=["staging.internal"]
)
def _write_report(file_path: str, content: str) -> str:
    with open(file_path, 'w') as f:
        f.write(content)
    return f"Written to {file_path}"

class ReportWriterTool(BaseTool):
    name: str = "Report Writer"
    description: str = "Write a report to a file"

    def _run(self, file_path: str, content: str) -> str:
        return _write_report(file_path, content)
```

---

## OpenClaw

K9 Audit integrates with OpenClaw at three levels, from zero-code setup to
full Y*_t intent contract definition.

### Level 1 — One-command setup (zero code changes)

Run once after `pip install k9audit-hook`:

```bash
k9log openclaw-setup
```

This command does four things automatically:

1. Finds or creates your AGENTS.md
2. Parses your AGENTS.md rules into verified Y*_t constraints (SHA256 hash-anchored)
3. Scans your existing OpenClaw session history and writes CIEU records retroactively
4. Starts a background watcher that monitors all future session JSONL files in real time

Every tool call your agent makes is now recorded as a CIEU five-tuple and
checked against your AGENTS.md rules. No decorator. No code change.

---

### Level 2 — Simplified intent contract with @k9 aliases

If you want to define constraints per-function, the simplified alias interface
removes the need to learn the internal constraint format:

```python
from k9log import k9, set_agent_identity

set_agent_identity(agent_name='OpenClaw')

@k9(
    deny=[".env", "/etc/", "production"],
    only_paths=["./projects/"],
    deny_commands=["rm -rf", "sudo"],
    only_domains=["api.github.com"],
    invariant=["amount > 0", "amount < 1000000"],
    postcondition=["result.get('status') == 'ok'"],
)
def transfer_funds(amount: float, recipient: str) -> dict:
    return {'status': 'ok', 'amount': amount}
```

Eight constraint dimensions are supported:

| Alias | Meaning |
|---|---|
| `deny` | Strings that must never appear in any parameter |
| `only_paths` | Allowed filesystem paths |
| `deny_commands` | Blocked shell commands |
| `only_domains` | Allowed network domains |
| `invariant` | Python expressions that must hold on inputs |
| `postcondition` | Python expressions that must hold on outputs |
| `field_deny` | Per-field value blocklist |
| `value_range` | Numeric bounds |

---

### Level 3 — Auto-prefilled contract builder

For any function, K9 Audit can suggest constraints automatically from four
deterministic sources (no LLM):

- **AST analysis** of the function code
- **AGENTS.md** rules (pattern matcher)
- **CIEU history** — what the function actually touched in the past
- **Security pattern library** — keyed on function and parameter names

```bash
k9log contract add transfer_funds
```

Example output for `transfer_funds`:

```
Auto-prefilling from AGENTS.md, AST, history, patterns...

[Deny content]    (comma-separated: .env, /etc/, 192.168.)
  Prefilled: production, prod
  Values [production, prod]:

[Deny commands]   (comma-separated: rm -rf, sudo, chmod 777)
  Values []:

[Param invariant] (e.g. amount > 0)
  Prefilled: funds > 0, funds < 1000000
  Values [funds > 0, funds < 1000000]:
```

The system infers the parameter name `funds` from the function name
`transfer_funds` and generates the invariant expressions automatically.
Press Enter to accept each suggestion. The result is saved to
`~/.k9log/config/transfer_funds.json` and loaded automatically by `@k9`.

---

### Wrap an entire skill module (legacy, still supported)

```python
from k9log.openclaw import k9_wrap_module
import my_skills

k9_wrap_module(my_skills)  # every function in my_skills is now audited
```

---

## Any Python Agent

If your agent calls Python functions, `@k9` works with no other requirements.

```python
from k9log import k9, set_agent_identity

# Name your agent — appears in every CIEU record
set_agent_identity(agent_name='MyAgent')

@k9(
    amount={'max': 500, 'min': 0},
    target_env={'blocklist': ['production', 'prod']}
)
def deploy(amount: float, target_env: str) -> dict:
    # your existing logic, completely unchanged
    return {'deployed': True}
```

That's it. Every call now produces a CIEU record. Run `k9log stats` to
see what has been captured.

---


## After any integration

Once your agent is wired up, the full investigation toolkit is available:

```bash
k9log stats                    # what happened across all sessions?
k9log trace --last             # root cause of the most recent deviation
k9log trace --step 451         # root cause of a specific event
k9log verify-log               # cryptographic proof nothing was tampered
k9log report --output out.html # shareable HTML evidence report
```

