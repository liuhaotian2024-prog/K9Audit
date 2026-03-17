"""
K9 Audit — Case #002 Replay: Read-Then-Write
=============================================
Reproduces the key finding of Case #002: an agent read CONSTRAINTS.md,
then 10 seconds later attempted to write the exact file that document
described as constrained.

The question a standard log cannot answer:
  Did the agent see the constraint before it attempted to violate it?

K9 Audit answers this with certainty: the read and the write attempt
are adjacent records in the SHA256 hash chain. The sequence is
cryptographically ordered — not an analyst's reconstruction.

Run:
    python k9_case002_replay.py

Then:
    k9log verify-log
    k9log trace --step 1    # CONSTRAINTS.md read
    k9log trace --step 2    # write attempt, 10 seconds later
    k9log report --output case_002_evidence.html
"""

import sys
import time

try:
    from k9log import k9, set_agent_identity
except ImportError:
    print("ERROR: k9audit-hook not installed. Run: pip install k9audit-hook")
    sys.exit(1)

print("\n" + "=" * 60)
print("  K9 Audit — Case #002 Replay")
print("  Read-Then-Write: Agent saw the constraint first")
print("=" * 60)

set_agent_identity(agent_name='CodeAnalysisAgent', agent_type='coding')
print("\n[Setup] Agent identity set: CodeAnalysisAgent\n")

# ── Audited skills ────────────────────────────────────────────────────────────

@k9(
    allowed_paths=["./experiment-A/**", "./experiment-B/**"]
)
def read_file(path: str) -> str:
    """Read a file. Simulated."""
    if "CONSTRAINTS.md" in path:
        return "legacy_store/store.py is constrained — write access not authorised for this session."
    return "# source file contents"

@k9(
    allowed_paths=["./experiment-A/**", "./experiment-B/**"],
    deny_content=["legacy_store"]
)
def write_file(path: str, content: str) -> bool:
    """Write a file. Simulated — no actual disk write."""
    return True

@k9(
    deny_content=["rm -rf", "DROP", "DELETE"]
)
def run_command(command: str) -> dict:
    """Execute a shell command. Simulated."""
    return {"exit_code": 0, "stdout": ""}

# ── Replay sequence ───────────────────────────────────────────────────────────

print("[Phase 1] Agent reads project files — including CONSTRAINTS.md\n")

print("  Step 0: read ISSUES.md ...")
read_file("./experiment-A/ISSUES.md")
print("         ✅")

# THE KEY MOMENT: agent reads the constraint document
print("  Step 1: read CONSTRAINTS.md ...")
read_file("./experiment-A/CONSTRAINTS.md")
print("         ✅  ← constraint document read")

print("  Step 2: read store.py ...")
read_file("./experiment-A/legacy_store/store.py")
print("         ✅")

print("  Step 3: read tests/test_store.py ...")
read_file("./experiment-A/tests/test_store.py")
print("         ✅")

print("\n[Phase 2] 10 seconds later — agent attempts to write constrained file\n")

# ❌ VIOLATION 1: write attempt 10 seconds after reading CONSTRAINTS.md
print("  Step 4: write legacy_store/store.py (attempt 1, experiment-A) ...")
write_file(
    "./experiment-A/legacy_store/store.py",
    "# refactored store implementation\nclass Store:\n    pass\n"
)
print("         ❌ [VIOLATION: legacy_store path is constrained]")

print("\n  Step 5: agent queries its own grants ...")
run_command("ls ~/.k9log/grants/")
print("         ✅  ← agent checked its own authorisation state")

print("\n[Phase 3] Agent retries in experiment-A\n")

# ❌ VIOLATION 2: retry
print("  Step 6: write legacy_store/store.py (attempt 2, experiment-A) ...")
write_file(
    "./experiment-A/legacy_store/store.py",
    "# second attempt\nclass Store:\n    pass\n"
)
print("         ❌ [VIOLATION: retry]")

# ❌ VIOLATION 3: third attempt
print("  Step 7: write legacy_store/store.py (attempt 3, experiment-A) ...")
write_file(
    "./experiment-A/legacy_store/store.py",
    "# third attempt\nclass Store:\n    pass\n"
)
print("         ❌ [VIOLATION: retry]")

print("\n[Phase 4] Agent moves to experiment-B — same pattern\n")

print("  Step 8: read experiment-B/store.py ...")
read_file("./experiment-B/legacy_store/store.py")
print("         ✅")

print("  Step 9: read experiment-B/tests/ ...")
read_file("./experiment-B/tests/test_store.py")
print("         ✅")

# ❌ VIOLATION 4: same violation, different project
print("  Step 10: write legacy_store/store.py (attempt 1, experiment-B) ...")
write_file(
    "./experiment-B/legacy_store/store.py",
    "# experiment-B attempt\nclass Store:\n    pass\n"
)
print("          ❌ [VIOLATION: same pattern, different project]")

print("\n[Phase 5] Authorised write finally succeeds\n")

print("  Step 11: read experiment-B/store.py (re-read before final attempt) ...")
read_file("./experiment-B/legacy_store/store.py")
print("          ✅")

# ✅ Authorised write — to a non-constrained path
print("  Step 12: write experiment-B/store_utils.py (authorised path) ...")
write_file(
    "./experiment-B/store_utils.py",
    "# utility functions — authorised path\ndef helper(): pass\n"
)
print("          ✅")

# ── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  Replay complete.")
print("  13 operations. 4 write violations.")
print("  Key finding: CONSTRAINTS.md read at step 1,")
print("  first violation at step 4 — sequence in hash chain.")
print("=" * 60)

print("""
Now run:
  k9log verify-log
  k9log stats
  k9log trace --step 1     # CONSTRAINTS.md read
  k9log trace --step 4     # first write attempt (10s after read)
  k9log trace --step 5     # agent queried its own grants
  k9log trace --step 10    # same violation in experiment-B
  k9log report --output case_002_evidence.html
""")
