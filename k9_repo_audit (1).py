"""
K9 Audit — Case #004: Repository Residue Audit
===============================================
Uses K9 Audit to audit the K9Audit repository itself for AI agent
iteration residue — files that should have been cleaned up but were not.

Five rules derived from software engineering best practices:

  RULE 1 — SUPERSEDED:   *_fixed.py / *_v2.py / *_old.py exist alongside original
  RULE 2 — ORPHANED_TXT: .txt files not referenced in any .md file
  RULE 3 — ARTIFACT:     Office temp files (~$*), .bak, .tmp
  RULE 4 — ORPHANED_JSONL: .jsonl without a corresponding .md case document
  RULE 5 — UNREFERENCED_SCRIPT: root-level .py scripts not mentioned in README

This is not a linter. It does not check code quality.
It checks whether the repository matches the intent contract:
"After iteration, the repository should contain only files that are
actively referenced, not superseded, and not accidental artifacts."

Run:
    python k9_repo_audit.py [path_to_repo]

Then:
    k9log verify-log
    k9log stats
    k9log report --output case_004_evidence.html
"""

import sys
import os
import re
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
print("  K9 Audit — Case #004: Repository Residue Audit")
print(f"  Target: {REPO_ROOT}")
print("=" * 60)

set_agent_identity(agent_name='RepoAuditor', agent_type='auditor')
print("\n[Setup] Agent identity set: RepoAuditor\n")

# ── Helper: collect all repo files (excluding .git, __pycache__) ──────────────

def collect_files(root: Path) -> list[Path]:
    result = []
    exclude = {'.git', '__pycache__', '.pytest_cache', 'node_modules', '.venv'}
    for path in root.rglob('*'):
        if path.is_file():
            if not any(ex in path.parts for ex in exclude):
                result.append(path)
    return result

ALL_FILES = collect_files(REPO_ROOT)
README = (REPO_ROOT / 'README.md').read_text(encoding='utf-8', errors='ignore') if (REPO_ROOT / 'README.md').exists() else ''
ALL_MD = [f for f in ALL_FILES if f.suffix == '.md']
ALL_MD_TEXT = {}
for md in ALL_MD:
    try:
        ALL_MD_TEXT[md] = md.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        ALL_MD_TEXT[md] = ''

print(f"[Scan] {len(ALL_FILES)} files found in repository\n")

# ── Audited skills ────────────────────────────────────────────────────────────

@k9(
    deny_content=["VIOLATION"],
    rule_id={"enum": ["SUPERSEDED", "ORPHANED_TXT", "ARTIFACT", "ORPHANED_JSONL", "UNREFERENCED_SCRIPT", "ENCODING_ISSUE", "DUPLICATE_CONFIG"]},
)
def audit_file(file_path: str, rule_id: str, verdict: str, reason: str) -> dict:
    """Record one file audit result as a CIEU record.
    K9Contract:
      invariant: len(file_path) > 0
      invariant: len(rule_id) > 0
    """
    return {
        "file": file_path,
        "rule": rule_id,
        "verdict": verdict,
        "reason": reason
    }

# ── Rule 1: SUPERSEDED ────────────────────────────────────────────────────────

print("[Rule 1] SUPERSEDED — *_fixed.py, *_v2.py, *_old.py, *_backup.py\n")

superseded_patterns = re.compile(r'(.+)(_fixed|_v\d+|_old|_backup|_copy|_bak)(\.py)$')
py_files = [f for f in ALL_FILES if f.suffix == '.py']
py_stems = {f.stem: f for f in py_files}

rule1_count = 0
for f in py_files:
    m = superseded_patterns.match(f.name)
    if m:
        original_stem = m.group(1)
        # Check if original also exists
        original_exists = original_stem in py_stems
        reason = f"Superseded variant of '{original_stem}.py'" if original_exists else f"Looks like a superseded file (no original '{original_stem}.py' found)"
        print(f"  ❌ SUPERSEDED: {f.relative_to(REPO_ROOT)}")
        print(f"     {reason}")
        audit_file(str(f.relative_to(REPO_ROOT)), "SUPERSEDED", "VIOLATION", reason)
        rule1_count += 1

if rule1_count == 0:
    print("  ✅ No superseded files found")
    audit_file(".", "SUPERSEDED", "CLEAN", "No *_fixed / *_v2 / *_old files found")

# ── Rule 2: ORPHANED TXT ─────────────────────────────────────────────────────

print("\n[Rule 2] ORPHANED_TXT — .txt files not referenced in any .md\n")

txt_files = [f for f in ALL_FILES if f.suffix == '.txt' and 'requirements' not in f.name.lower()]
rule2_count = 0
for f in txt_files:
    fname = f.name
    referenced = any(fname in text or str(f.relative_to(REPO_ROOT)) in text
                     for text in ALL_MD_TEXT.values())
    referenced = referenced or (fname in README)
    if not referenced:
        reason = f"'{fname}' is not referenced in any .md file or README"
        print(f"  ❌ ORPHANED_TXT: {f.relative_to(REPO_ROOT)}")
        print(f"     {reason}")
        audit_file(str(f.relative_to(REPO_ROOT)), "ORPHANED_TXT", "VIOLATION", reason)
        rule2_count += 1

if rule2_count == 0:
    print("  ✅ No orphaned .txt files found")
    audit_file(".", "ORPHANED_TXT", "CLEAN", "All .txt files are referenced or are requirements files")

# ── Rule 3: ARTIFACT ─────────────────────────────────────────────────────────

print("\n[Rule 3] ARTIFACT — Office temp files, .bak, .tmp\n")

artifact_patterns = [
    lambda f: f.name.startswith('~$'),
    lambda f: f.suffix in {'.bak', '.tmp', '.swp'},
    lambda f: f.name.endswith('.py.bak'),
]
rule3_count = 0
for f in ALL_FILES:
    if any(p(f) for p in artifact_patterns):
        reason = f"'{f.name}' is an artifact file (temp/backup) — should not be in repository"
        print(f"  ❌ ARTIFACT: {f.relative_to(REPO_ROOT)}")
        print(f"     {reason}")
        audit_file(str(f.relative_to(REPO_ROOT)), "ARTIFACT", "VIOLATION", reason)
        rule3_count += 1

if rule3_count == 0:
    print("  ✅ No artifact files found")
    audit_file(".", "ARTIFACT", "CLEAN", "No temp/backup artifact files found")

# ── Rule 4: ORPHANED JSONL ────────────────────────────────────────────────────

print("\n[Rule 4] ORPHANED_JSONL — .jsonl without corresponding .md\n")

jsonl_files = [f for f in ALL_FILES if f.suffix == '.jsonl']
rule4_count = 0

# Known legitimate standalone jsonl files
KNOWN_STANDALONE = {'challenge_logs.jsonl', 'cieu_session.jsonl'}

for f in jsonl_files:
    if f.name in KNOWN_STANDALONE:
        # These are challenge data files — check if they're referenced in challenge/README.md
        challenge_readme = REPO_ROOT / 'challenge' / 'README.md'
        referenced = False
        if challenge_readme.exists():
            referenced = f.name in challenge_readme.read_text(encoding='utf-8', errors='ignore')
        referenced = referenced or (f.name in README)
        if not referenced:
            reason = f"'{f.name}' is a challenge data file not referenced in challenge/README.md"
            print(f"  ❌ ORPHANED_JSONL: {f.relative_to(REPO_ROOT)}")
            print(f"     {reason}")
            audit_file(str(f.relative_to(REPO_ROOT)), "ORPHANED_JSONL", "VIOLATION", reason)
            rule4_count += 1
        else:
            audit_file(str(f.relative_to(REPO_ROOT)), "ORPHANED_JSONL", "CLEAN", "Referenced in challenge docs")
        continue

    # For case_NNN_live_verified.jsonl — check if case_NNN*.md exists nearby
    stem = f.stem  # e.g. case_000_live_verified
    case_prefix = re.match(r'(case_\d+)', stem)
    if case_prefix:
        prefix = case_prefix.group(1)
        matching_md = [m for m in ALL_MD if prefix in m.stem]
        if not matching_md:
            reason = f"'{f.name}' has no corresponding case .md document (expected case matching '{prefix}')"
            print(f"  ❌ ORPHANED_JSONL: {f.relative_to(REPO_ROOT)}")
            print(f"     {reason}")
            audit_file(str(f.relative_to(REPO_ROOT)), "ORPHANED_JSONL", "VIOLATION", reason)
            rule4_count += 1
        else:
            audit_file(str(f.relative_to(REPO_ROOT)), "ORPHANED_JSONL", "CLEAN",
                      f"Matched to {matching_md[0].name}")
    else:
        reason = f"'{f.name}' does not follow case naming convention and has no corresponding .md"
        print(f"  ⚠️  ORPHANED_JSONL: {f.relative_to(REPO_ROOT)}")
        print(f"     {reason}")
        audit_file(str(f.relative_to(REPO_ROOT)), "ORPHANED_JSONL", "VIOLATION", reason)
        rule4_count += 1

if rule4_count == 0:
    print("  ✅ All .jsonl files have corresponding documentation")

# ── Rule 5: UNREFERENCED SCRIPT ──────────────────────────────────────────────

print("\n[Rule 5] UNREFERENCED_SCRIPT — root-level .py not in README or imports\n")

root_py = [f for f in ALL_FILES if f.suffix == '.py' and f.parent == REPO_ROOT]
rule5_count = 0

# Known legitimate standalone scripts
KNOWN_SCRIPTS = {
    'hook.py',          # legacy standalone copy documented in integrations.md
    'setup_k9audit.ps1' # not .py
}

for f in root_py:
    if f.name in KNOWN_SCRIPTS:
        continue
    stem = f.stem
    in_readme = stem in README or f.name in README
    imported = False
    for src in ALL_FILES:
        if src.suffix == '.py' and src != f:
            try:
                content = src.read_text(encoding='utf-8', errors='ignore')
                if f'import {stem}' in content or f'from {stem}' in content:
                    imported = True
                    break
            except Exception:
                pass

    if not in_readme and not imported:
        reason = f"'{f.name}' is a root-level script not mentioned in README and not imported anywhere"
        print(f"  ❌ UNREFERENCED_SCRIPT: {f.relative_to(REPO_ROOT)}")
        print(f"     {reason}")
        audit_file(str(f.relative_to(REPO_ROOT)), "UNREFERENCED_SCRIPT", "VIOLATION", reason)
        rule5_count += 1
    else:
        ref = "README" if in_readme else "imported"
        audit_file(str(f.relative_to(REPO_ROOT)), "UNREFERENCED_SCRIPT", "CLEAN",
                  f"Referenced in {ref}")

if rule5_count == 0:
    print("  ✅ All root-level scripts are referenced")

# ── Bonus: ENCODING ISSUE ────────────────────────────────────────────────────

print("\n[Bonus] ENCODING_ISSUE — filenames with URL-encoded characters\n")

rule6_count = 0
for f in ALL_FILES:
    if '#U' in f.name or '%' in f.name:
        reason = f"'{f.name}' has URL-encoded characters in filename — encoding issue from Windows/git"
        print(f"  ❌ ENCODING_ISSUE: {f.relative_to(REPO_ROOT)}")
        print(f"     {reason}")
        audit_file(str(f.relative_to(REPO_ROOT)), "ENCODING_ISSUE", "VIOLATION", reason)
        rule6_count += 1

if rule6_count == 0:
    print("  ✅ No encoding issues found")

# ── Bonus: DUPLICATE CONFIG ──────────────────────────────────────────────────

print("\n[Bonus] DUPLICATE_CONFIG — multiple settings/config files at root\n")

config_files = [f for f in ALL_FILES if f.parent == REPO_ROOT and
                f.name in {'claude_settings.json', 'settings.json', '.claude/settings.json'}]
root_json = [f for f in ALL_FILES if f.parent == REPO_ROOT and f.suffix == '.json'
             and 'settings' in f.name.lower()]

rule7_count = 0
if len(root_json) > 1:
    for f in root_json:
        reason = f"Multiple settings JSON files at root — '{f.name}' may be a duplicate or stale copy"
        print(f"  ❌ DUPLICATE_CONFIG: {f.relative_to(REPO_ROOT)}")
        print(f"     {reason}")
        audit_file(str(f.relative_to(REPO_ROOT)), "DUPLICATE_CONFIG", "VIOLATION", reason)
        rule7_count += 1
else:
    print("  ✅ No duplicate config files found")
    audit_file(".", "DUPLICATE_CONFIG", "CLEAN", "No duplicate settings files at root")

# ── Summary ───────────────────────────────────────────────────────────────────

total_violations = rule1_count + rule2_count + rule3_count + rule4_count + rule5_count + rule6_count + rule7_count

print("\n" + "=" * 60)
print("  Repository Residue Audit Complete")
print(f"  Total violations found: {total_violations}")
print(f"    Rule 1 SUPERSEDED:          {rule1_count}")
print(f"    Rule 2 ORPHANED_TXT:        {rule2_count}")
print(f"    Rule 3 ARTIFACT:            {rule3_count}")
print(f"    Rule 4 ORPHANED_JSONL:      {rule4_count}")
print(f"    Rule 5 UNREFERENCED_SCRIPT: {rule5_count}")
print(f"    Bonus ENCODING_ISSUE:       {rule6_count}")
print(f"    Bonus DUPLICATE_CONFIG:     {rule7_count}")
print("=" * 60)

print("""
Now run:
  k9log verify-log
  k9log stats
  k9log report --output case_004_evidence.html
""")
