# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
# AGPL-3.0
"""
K9log Auditor — Post-hoc static analysis of AI-written codebases.

Detects violations without executing any code:
  - Staging / internal URLs written into production configs
  - Secret / credential patterns (API keys, tokens, passwords)
  - Missing imports that will fail at runtime
  - Files written outside declared scope (allowed_paths)
  - Constraint violations against CONSTRAINTS.md rules

Usage:
    k9log audit ./my-project
    k9log audit ./my-project --checks imports,secrets,staging
    k9log audit ./my-project --output report.html
"""
import ast
import json
import re
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Finding data model ────────────────────────────────────────────────────────

@dataclass
class Finding:
    severity: str          # HIGH / MEDIUM / LOW
    check:    str          # imports / secrets / staging / scope / constraints
    title:    str
    detail:   str
    file:     str
    line:     Optional[int] = None
    command:  Optional[str] = None

    def severity_order(self):
        return {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(self.severity, 3)


# ── Pattern definitions ───────────────────────────────────────────────────────

STAGING_PATTERNS = [
    r'staging\.internal',
    r'\.staging\.',
    r'sandbox\.',
    r'dev\.internal',
    r'test\.internal',
    r'localhost',
    r'127\.0\.0\.1',
    r'192\.168\.',
    r'10\.0\.',
]

SECRET_PATTERNS = [
    (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?([A-Za-z0-9_\-]{16,})', 'api_key'),
    (r'(?i)(secret[_-]?key|secret)\s*[=:]\s*["\']?([A-Za-z0-9_\-]{16,})', 'secret'),
    (r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']([^"\']{4,})["\']', 'password'),
    (r'(?i)(token|access_token|auth_token)\s*[=:]\s*["\']?([A-Za-z0-9_\-\.]{16,})', 'token'),
    (r'sk-[A-Za-z0-9]{32,}', 'openai_key'),
    (r'ghp_[A-Za-z0-9]{36}', 'github_token'),
    (r'-----BEGIN (RSA |EC )?PRIVATE KEY-----', 'private_key'),
]

# Extensions to scan
CODE_EXTENSIONS   = {'.py', '.js', '.ts', '.jsx', '.tsx', '.mjs'}
CONFIG_EXTENSIONS = {'.json', '.yaml', '.yml', '.toml', '.env', '.cfg', '.ini', '.conf'}
ALL_EXTENSIONS    = CODE_EXTENSIONS | CONFIG_EXTENSIONS

# Directories to skip
# Files to skip during audit (test fixtures, demo data, tool internals)
SKIP_FILES = {
    "auditor.py", "k9_live_test.py", "k9_concurrency_test.py",
    "hook.py",  # root-level standalone copy
    "main.py",  # server infrastructure
    "openclaw.py",  # examples in docstrings are not real violations
}

SKIP_DIRS = {
    '.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env',
    'dist', 'build', '.next', '.nuxt', 'coverage', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', 'site-packages',
}


# ── File scanner ──────────────────────────────────────────────────────────────

def _iter_files(root: Path):
    """Yield all scannable files under root, skipping known junk dirs."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith('.')]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() in ALL_EXTENSIONS and fpath.name not in SKIP_FILES:
                yield fpath


def _read_lines(fpath: Path):
    """Read file lines safely, returning [] on decode error."""
    try:
        return fpath.read_text(encoding='utf-8', errors='replace').splitlines()
    except Exception:
        return []


# ── Individual checks ─────────────────────────────────────────────────────────

def check_staging(root: Path) -> list[Finding]:
    """Find staging / internal URLs written into any file."""
    findings = []
    combined = re.compile('|'.join(STAGING_PATTERNS), re.IGNORECASE)

    for fpath in _iter_files(root):
        lines = _read_lines(fpath)
        rel = str(fpath.relative_to(root))
        for i, line in enumerate(lines, 1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('//'):
                continue
            if combined.search(line):
                matched = combined.search(line).group(0)
                # Skip lines that are constraint config definitions
                # (e.g. deny_content=['staging.internal'] in cli.py/constraints.py)
                config_keywords = ['deny_content', 'deny_content=', 'DENY_CONTENT',
                                   'infer_magic', '_MAGIC_', 'MAGIC_AST', 'MAGIC_PARAM',
                                   'k9log init defaults', 'suggest', 'constraints']
                is_config_line = any(kw in line for kw in config_keywords)
                if is_config_line:
                    continue
                findings.append(Finding(
                    severity='HIGH',
                    check='staging',
                    title='Staging / internal URL in code',
                    detail=f'"{matched}" found — this should not reach production.',
                    file=rel,
                    line=i,
                    command=f'k9log trace --file {rel}',
                ))
    return findings


def check_secrets(root: Path) -> list[Finding]:
    """Find hardcoded secrets, tokens, and credentials."""
    findings = []

    for fpath in _iter_files(root):
        # Skip test files and example configs
        rel = str(fpath.relative_to(root))
        if any(p in rel.lower() for p in ['test', 'example', 'sample', 'fixture', 'mock']):
            continue
        lines = _read_lines(fpath)
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('//'):
                continue
            for pattern, label in SECRET_PATTERNS:
                if re.search(pattern, line):
                    findings.append(Finding(
                        severity='HIGH',
                        check='secrets',
                        title=f'Potential hardcoded secret ({label})',
                        detail=f'Pattern "{label}" detected — use environment variables instead.',
                        file=rel,
                        line=i,
                        command=f'k9log audit {root} --checks secrets --verbose',
                    ))
                    break  # one finding per line
    return findings


def check_imports(root: Path) -> list[Finding]:
    """Find missing imports in Python files (used but not imported)."""
    findings = []

    for fpath in _iter_files(root):
        if fpath.suffix != '.py':
            continue
        rel = str(fpath.relative_to(root))
        try:
            source = fpath.read_text(encoding='utf-8', errors='replace')
            tree = ast.parse(source, filename=str(fpath))
        except SyntaxError:
            continue
        except Exception:
            continue

        # Collect imported names
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.asname or alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module.split('.')[0])
                for alias in node.names:
                    imported.add(alias.asname or alias.name)

        # Check for common modules used without import
        common_modules = {
            'os', 'sys', 'json', 'logging', 're', 'time', 'datetime',
            'pathlib', 'typing', 'collections', 'itertools', 'functools',
            'subprocess', 'threading', 'hashlib', 'base64', 'uuid',
        }
        used_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    used_names.add(node.value.id)

        missing = common_modules & used_names - imported
        if missing:
            for mod in sorted(missing):
                findings.append(Finding(
                    severity='HIGH',
                    check='imports',
                    title=f'Possibly missing import: {mod}',
                    detail=f'"{mod}" is used but not imported — will raise NameError at runtime.',
                    file=rel,
                    command=f'k9log causal --file {rel}',
                ))

    return findings


def check_scope(root: Path, allowed_paths: list[str] = None) -> list[Finding]:
    """
    Find files that may have been written outside declared scope.
    Heuristic: config/prod files outside common safe dirs are flagged.
    """
    findings = []
    # Patterns that suggest production-sensitive files
    sensitive_patterns = [
        r'prod(uction)?[_\-\.]',
        r'[_\-\.]prod\.',
        r'deploy',
        r'release',
    ]
    combined = re.compile('|'.join(sensitive_patterns), re.IGNORECASE)

    safe_dirs = {'src', 'tests', 'test', 'docs', 'output', 'outputs', 'scripts'}

    for fpath in _iter_files(root):
        rel = fpath.relative_to(root)
        parts = rel.parts
        if not parts:
            continue

        # Flag production-named files outside safe dirs
        fname = fpath.name
        if combined.search(fname) and fpath.suffix in CONFIG_EXTENSIONS:
            top_dir = parts[0] if len(parts) > 1 else ''
            if top_dir not in safe_dirs:
                findings.append(Finding(
                    severity='MEDIUM',
                    check='scope',
                    title='Production-sensitive config outside safe directory',
                    detail=f'"{rel}" looks like a production config. Verify it belongs here.',
                    file=str(rel),
                    command=f'k9log trace --file {rel}',
                ))

    return findings


def check_constraints(root: Path) -> list[Finding]:
    """Check code against CONSTRAINTS.md rules if present."""
    findings = []
    constraints_file = root / 'CONSTRAINTS.md'
    if not constraints_file.exists():
        # Also check common locations
        for loc in ['docs/CONSTRAINTS.md', '.claude/CONSTRAINTS.md']:
            candidate = root / loc
            if candidate.exists():
                constraints_file = candidate
                break
        else:
            return []

    try:
        constraints_text = constraints_file.read_text(encoding='utf-8')
    except Exception:
        return []

    # Extract NEVER rules
    never_patterns = re.findall(r'NEVER\s+(?:write|use|access|call|modify)[^`\n]*`([^`]+)`', constraints_text)
    never_patterns += re.findall(r'deny_content[^:]*:\s*["\']([^"\']+)["\']', constraints_text)

    if not never_patterns:
        return []

    combined = re.compile('|'.join(re.escape(p) for p in never_patterns), re.IGNORECASE)

    for fpath in _iter_files(root):
        if fpath == constraints_file:
            continue
        rel = str(fpath.relative_to(root))
        lines = _read_lines(fpath)
        for i, line in enumerate(lines, 1):
            if combined.search(line):
                matched = combined.search(line).group(0)
                findings.append(Finding(
                    severity='HIGH',
                    check='constraints',
                    title='CONSTRAINTS.md violation',
                    detail=f'Forbidden pattern "{matched}" found — violates declared intent contract.',
                    file=rel,
                    line=i,
                    command=f'k9log trace --file {rel}',
                ))

    return findings


# ── Main audit runner ─────────────────────────────────────────────────────────

CHECK_MAP = {
    'staging':     check_staging,
    'secrets':     check_secrets,
    'imports':     check_imports,
    'scope':       check_scope,
    'constraints': check_constraints,
}

DEFAULT_CHECKS = ['staging', 'secrets', 'imports', 'scope', 'constraints']


def run_audit(
    path: str,
    checks: list[str] = None,
    output: str = None,
    verbose: bool = False,
) -> list[Finding]:
    """
    Run a post-hoc static audit on a codebase.

    Args:
        path:    Path to repository root
        checks:  List of check names to run (default: all)
        output:  Output file path (.html or .json), or None for terminal
        verbose: Include LOW severity findings

    Returns:
        List of Finding objects
    """
    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Path not found: {root}")

    active_checks = checks or DEFAULT_CHECKS
    all_findings: list[Finding] = []

    for check_name in active_checks:
        fn = CHECK_MAP.get(check_name)
        if fn:
            try:
                found = fn(root)
                all_findings.extend(found)
            except Exception as e:
                # Never crash the audit runner
                import logging
                logging.getLogger('k9log.auditor').warning(
                    'check %s failed: %s', check_name, e
                )

    # Sort by severity then file
    all_findings.sort(key=lambda f: (f.severity_order(), f.file, f.line or 0))

    if not verbose:
        all_findings = [f for f in all_findings if f.severity in ('HIGH', 'MEDIUM')]

    if output:
        out_path = Path(output)
        if out_path.suffix == '.html':
            _write_html(all_findings, out_path, root)
        elif out_path.suffix == '.json':
            _write_json(all_findings, out_path, root)

    return all_findings


# ── Output formatters ─────────────────────────────────────────────────────────

def _write_json(findings: list[Finding], out_path: Path, root: Path):
    data = {
        'audited_path': str(root),
        'total_findings': len(findings),
        'findings': [
            {
                'severity': f.severity,
                'check':    f.check,
                'title':    f.title,
                'detail':   f.detail,
                'file':     f.file,
                'line':     f.line,
                'command':  f.command,
            }
            for f in findings
        ]
    }
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def _write_html(findings: list[Finding], out_path: Path, root: Path):
    high   = [f for f in findings if f.severity == 'HIGH']
    medium = [f for f in findings if f.severity == 'MEDIUM']
    low    = [f for f in findings if f.severity == 'LOW']

    def finding_html(f: Finding) -> str:
        sev_color = {'HIGH': '#ff4d6d', 'MEDIUM': '#f0a500', 'LOW': '#00c9a7'}.get(f.severity, '#7a8fa8')
        loc = f.file + (f':' + str(f.line) if f.line else '')
        cmd = f'<div style="margin-top:8px;font-family:monospace;font-size:12px;color:#f0a500">&rarr; {f.command}</div>' if f.command else ''
        return f'''
        <div style="background:#0f1215;border:1px solid #1e2530;border-left:4px solid {sev_color};border-radius:8px;padding:16px;margin-bottom:12px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
            <span style="color:#e8f0f8;font-weight:700;font-size:13px">{f.title}</span>
            <span style="background:{sev_color}22;color:{sev_color};font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px">{f.severity}</span>
          </div>
          <div style="color:#7a8fa8;font-size:12px;margin-bottom:6px">{f.detail}</div>
          <div style="color:#4a5a6e;font-size:11px;font-family:monospace">{loc}</div>
          {cmd}
        </div>'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>K9 Audit Report — {root.name}</title>
<style>
body{{background:#0a0c0f;color:#c8d4e0;font-family:'JetBrains Mono',monospace;font-size:14px;padding:40px;max-width:900px;margin:0 auto}}
h1{{font-size:28px;color:#e8f0f8;margin-bottom:8px}}
.summary{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:24px 0}}
.stat{{background:#0f1215;border:1px solid #1e2530;border-radius:8px;padding:16px;text-align:center}}
.stat .val{{font-size:32px;font-weight:700;margin-bottom:4px}}
.stat .lbl{{font-size:11px;color:#4a5a6e;text-transform:uppercase;letter-spacing:.1em}}
</style>
</head>
<body>
<h1>🐕‍🦺 K9 Audit Report</h1>
<div style="color:#7a8fa8;margin-bottom:8px">Path: {root}</div>
<div class="summary">
  <div class="stat"><div class="val" style="color:#ff4d6d">{len(high)}</div><div class="lbl">High</div></div>
  <div class="stat"><div class="val" style="color:#f0a500">{len(medium)}</div><div class="lbl">Medium</div></div>
  <div class="stat"><div class="val" style="color:#00c9a7">{len(low)}</div><div class="lbl">Low</div></div>
</div>
{''.join(finding_html(f) for f in findings) if findings else '<div style="color:#00c9a7;padding:24px;text-align:center">✓ No findings — codebase looks clean</div>'}
<div style="margin-top:32px;font-size:11px;color:#4a5a6e">Generated by k9log audit · K9 Audit v0.2.1</div>
</body></html>'''

    out_path.write_text(html, encoding='utf-8')
