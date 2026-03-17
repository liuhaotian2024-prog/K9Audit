"""
K9 Audit — Case #004 Phase 2: Repository Residue Cleanup
=========================================================
Executes cleanup of violations found in Phase 1 (k9_repo_audit.py).
Every cleanup action is recorded as a CIEU five-tuple — forming a
complete causal chain: detect → clean → verify.

This is the closure that static analyzers cannot provide:
not just "what was wrong" but "what was done about it, and when,
and by which agent, under which contract."

Run AFTER k9_repo_audit.py:
    python k9_repo_cleanup.py [path_to_repo]

Then verify the complete chain:
    k9log verify-log
    k9log stats
"""

import sys
import os
import shutil
from pathlib import Path

try:
    from k9log import k9, set_agent_identity
except ImportError:
    print("ERROR: k9log not found. Run from the K9Audit repo root.")
    sys.exit(1)

# ── Setup ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
REPO_ROOT = REPO_ROOT.resolve()

print("\n" + "=" * 60)
print("  K9 Audit — Case #004 Phase 2: Repository Residue Cleanup")
print(f"  Target: {REPO_ROOT}")
print("=" * 60)

set_agent_identity(agent_name='RepoCleanup', agent_type='auditor')
print("\n[Setup] Agent identity set: RepoCleanup\n")

# ── Cleanup contract ──────────────────────────────────────────────────────────
#
# Intent contract (Y*_t):
#   After Phase 1 detection, the agent MUST:
#   1. Delete all SUPERSEDED files
#   2. Delete all ORPHANED_TXT debug/trace files
#   3. Delete all ARTIFACT (temp/lock) files
#   4. Add build artifact directories to .gitignore
#   5. NOT delete runtime data or legitimate standalone scripts
#
# Any file deleted must be recorded as a CIEU action.
# Any file skipped must also be recorded with reason.

@k9(
    deny_content=["SKIPPED_WITHOUT_REASON"],
    action={"enum": ["DELETED", "GITIGNORED", "PRESERVED"]},
)
def cleanup_file(file_path: str, action: str, rule_id: str, reason: str) -> dict:
    """Record one cleanup action as a CIEU record.
    K9Contract:
      invariant: len(file_path) > 0
      invariant: len(reason) > 0
    """
    return {
        "file": file_path,
        "action": action,
        "rule": rule_id,
        "reason": reason,
    }

# ── Phase 2 cleanup manifest ──────────────────────────────────────────────────
#
# Derived directly from Phase 1 output.
# Each entry: (relative_path, action, rule_id, reason)

CLEANUP_MANIFEST = [
    # Rule 1: SUPERSEDED
    (
        "k9_case002_replay_fixed.py",
        "DELETED",
        "SUPERSEDED",
        "Superseded by k9_case002_replay.py — fixed version was merged, original variant not removed"
    ),
    # Rule 2: ORPHANED_TXT — debug trace outputs
    (
        "challenge/examples/case_000_trace_step3.txt",
        "DELETED",
        "ORPHANED_TXT",
        "Intermediate k9log trace output from Case 000 development — not referenced, fully reproducible"
    ),
    (
        "challenge/examples/case_000_trace_step6.txt",
        "DELETED",
        "ORPHANED_TXT",
        "Intermediate k9log trace output from Case 000 development — not referenced, fully reproducible"
    ),
    (
        "challenge/examples/case_000_trace_step8.txt",
        "DELETED",
        "ORPHANED_TXT",
        "Intermediate k9log trace output from Case 000 development — not referenced, fully reproducible"
    ),
    (
        "challenge/examples/case_000_verify.txt",
        "DELETED",
        "ORPHANED_TXT",
        "Intermediate k9log verify-log output from Case 000 development — not referenced, fully reproducible"
    ),
    (
        "output/test_output.txt",
        "DELETED",
        "ORPHANED_TXT",
        "Test session output — not referenced in any document"
    ),
    # Rule 3: ARTIFACT — editor lock files
    (
        "docs/~$9_demo.html",
        "DELETED",
        "ARTIFACT",
        "Microsoft Office editor lock file — accidentally committed, contains no useful content"
    ),
    (
        "server/~$shboard.html",
        "DELETED",
        "ARTIFACT",
        "Microsoft Office editor lock file — accidentally committed, contains no useful content"
    ),
    # Rule 2: ORPHANED_TXT — build artifacts → .gitignore instead of delete
    # (deleting egg-info is fine but it regenerates on next pip install -e .)
    (
        "k9audit_hook.egg-info",
        "GITIGNORED",
        "ORPHANED_TXT",
        "setuptools build artifact directory — auto-generated on pip install -e ., added to .gitignore"
    ),
]

# ── Execute cleanup ───────────────────────────────────────────────────────────

deleted = 0
gitignored = 0
failed = 0

print("[Phase 2] Executing cleanup under CIEU contract\n")

for rel_path, action, rule_id, reason in CLEANUP_MANIFEST:
    target = REPO_ROOT / rel_path.replace("/", os.sep)

    if action == "DELETED":
        if target.exists():
            try:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                print(f"  ✅ DELETED: {rel_path}")
                cleanup_file(rel_path, "DELETED", rule_id, reason)
                deleted += 1
            except Exception as e:
                print(f"  ❌ FAILED to delete: {rel_path} — {e}")
                cleanup_file(rel_path, "PRESERVED", rule_id, f"Deletion failed: {e}")
                failed += 1
        else:
            print(f"  ⚠️  ALREADY GONE: {rel_path}")
            cleanup_file(rel_path, "PRESERVED", rule_id, "File already removed before cleanup script ran")

    elif action == "GITIGNORED":
        gitignore_path = REPO_ROOT / ".gitignore"
        entry = rel_path.split("/")[0]  # top-level dir/file name

        # Read existing .gitignore
        existing = ""
        if gitignore_path.exists():
            existing = gitignore_path.read_text(encoding='utf-8')

        if entry not in existing:
            with open(gitignore_path, 'a', encoding='utf-8') as f:
                f.write(f"\n# Build artifacts (auto-generated by setuptools)\n{entry}/\n")
            print(f"  ✅ GITIGNORED: {entry}/ added to .gitignore")
            cleanup_file(rel_path, "GITIGNORED", rule_id, reason)
            gitignored += 1

            # Also remove the directory if it exists
            if target.exists():
                shutil.rmtree(target)
                print(f"  ✅ DELETED: {rel_path} (now in .gitignore)")
        else:
            print(f"  ⚠️  ALREADY IN .gitignore: {entry}")
            cleanup_file(rel_path, "PRESERVED", rule_id, "Already in .gitignore")

# ── Summary ───────────────────────────────────────────────────────────────────

total = deleted + gitignored + failed
print("\n" + "=" * 60)
print("  Phase 2 Cleanup Complete")
print(f"  Files deleted:    {deleted}")
print(f"  Added to .gitignore: {gitignored}")
print(f"  Failed:           {failed}")
print(f"  Total actions:    {total}")
print("=" * 60)

print("""
Complete causal chain now in ledger:
  Phase 1 — detection (k9_repo_audit.py)
  Phase 2 — cleanup   (k9_repo_cleanup.py)

Verify the full chain:
  k9log verify-log
  k9log stats

Then commit:
  git add -A
  git commit -m "Case 004 Phase 2: remove 13 residue files detected by k9_repo_audit"
  git push
""")
