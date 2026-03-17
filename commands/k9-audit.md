---
description: Run K9Audit causal audit on the current repository or a specific path
argument-hint: [path]
allowed-tools: [Bash]
---

Run a K9Audit repository residue audit on $ARGUMENTS (defaults to current directory).

Steps:
1. Check if k9audit-hook is installed: `pip show k9audit-hook`
2. If not installed, run: `pip install k9audit-hook`
3. Check if k9_repo_audit.py exists in the repo root
4. If it exists, run: `python k9_repo_audit.py ${ARGUMENTS:-.}`
5. Then run: `k9log verify-log`
6. Then run: `k9log stats`
7. Report the findings to the user: how many violations were found, which rules fired, and what files are implicated

If k9_repo_audit.py does not exist, explain that the user should download it from https://github.com/liuhaotian2024-prog/K9Audit and place it in the repo root.
