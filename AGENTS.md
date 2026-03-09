# K9 Audit — Claude Code Agent Instructions

## K9Contract Specification

Every Python function you write must declare a K9Contract in its docstring.
K9 Audit verifies these contracts at runtime — violations are immediately
flagged and written into the causal chain.

### Format

```python
def process_payment(account_id: str, amount: float) -> dict:
    """
    Process a payment request.

    K9Contract:
      postcondition: result["status"] in ("success", "failed")
      postcondition: result["balance"] >= 0
      invariant: amount > 0
    """
    ...
```

### Rules

**postcondition** — condition that must hold after the function returns.
Available variables: `result` (return value), `params` (dict of all arguments),
and all argument names directly.

- `postcondition: result is not None`
- `postcondition: len(result) > 0`
- `postcondition: result["status"] == "success" or result["error"] is not None`

**invariant** — condition that must always hold, typically on input arguments.

- `invariant: amount > 0`
- `invariant: len(user_id) > 0`
- `invariant: balance >= 0`

### When a K9Contract is required

- Any function with a return value
- Any function that modifies files, databases, or external state
- Any function involving finance, security, or configuration

### When a K9Contract may be omitted

- Pure utility functions (format conversion, string manipulation)
- Side-effect-free constant functions

### Example: file write

```python
def write_config(path: str, content: dict) -> bool:
    """
    Write configuration to file.

    K9Contract:
      postcondition: result == True
      invariant: len(path) > 0
      invariant: isinstance(content, dict)
    """
    ...
```

### Example: database query

```python
def query_database(table: str, limit: int) -> list:
    """
    Query database records.

    K9Contract:
      postcondition: isinstance(result, list)
      postcondition: len(result) <= limit
      invariant: limit > 0
      invariant: len(table) > 0
    """
    ...
```

---

## General coding rules

- Every new file must have explicit `import` statements at the top — do not rely on implicit imports.
- Use `pathlib.Path` for all path handling — do not hardcode `/` or `\`.
- Never hardcode URLs, IPs, or secrets — use config files or environment variables.
- All exceptions must be handled — no bare `except: pass`.

