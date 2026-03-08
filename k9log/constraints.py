# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
"""
K9log Constraints - Enhanced constraint types and checking
"""
import json
import hashlib
import logging
import re
from pathlib import Path
from datetime import datetime, timezone

def load_constraints(skill_name, inline_constraints=None):
    """
    Load Y*_t with versioning metadata
    
    Priority:
    1. Inline constraints (runtime override)
    2. Config file (~/.k9log/config/skill_name.json)
    3. Empty constraints
    """
    constraints = {}
    source = 'none'
    source_path = None
    version = None
    
    # Priority 1: Inline constraints
    if inline_constraints:
        constraints = inline_constraints
        source = 'decorator'
        source_path = 'inline'
    
    # Priority 2: Config file
    if not constraints:
        config_file = Path.home() / '.k9log' / 'config' / f'{skill_name}.json'
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    constraints = config.get('constraints', {})
                    version = config.get('version', '1.0.0')
                    source = 'config_file'
                    source_path = str(config_file)
            except Exception as e:
                logging.getLogger('k9log').warning('k9log: failed to load constraints from %s: %s', config_file, e)
    
    # Calculate hash
    y_star_hash = hash_ystar(constraints)

    # Warn if no constraints found -- unconstrained calls are recorded
    # but violations cannot be detected, which is a security gap.
    if not constraints:
        logging.getLogger('k9log').warning(
            'k9log: skill "%s" has no constraints (no inline rules, no config file) '
            '-- call will be recorded as UNCONSTRAINED', skill_name
        )

    return {
        'constraints': constraints,
        'y_star_meta': {
            'source': source if constraints else 'none',
            'source_path': source_path,
            'version': version or '1.0.0',
            'hash': y_star_hash,
            'loaded_at': datetime.now(timezone.utc).isoformat(),
            'unconstrained': not bool(constraints),
        }
    }


def hash_ystar(constraints):
    """Calculate SHA256 hash of canonicalized constraints"""
    canonical = canonicalize_ystar(constraints)
    return 'sha256:' + hashlib.sha256(canonical.encode()).hexdigest()

def canonicalize_ystar(constraints):
    """Canonicalize constraints for consistent hashing"""
    return json.dumps(
        constraints,
        sort_keys=True,
        ensure_ascii=True,
        separators=(',', ':')
    )


# ---------------------------------------------------------------------------
# Custom constraint registry
# ---------------------------------------------------------------------------
# Allows users and third-party packages to register new constraint types
# without modifying K9log core code.
#
# Usage (in your own code):
#
#   from k9log.constraints import register_constraint
#


_CUSTOM_CONSTRAINT_REGISTRY: dict = {}


def register_constraint(constraint_name: str):
    """
    Decorator to register a custom constraint checker.

    @register_constraint("my_constraint")
    def check_my_constraint(param_name, value, rule_value):
        ...
    """
    def decorator(fn):
        _CUSTOM_CONSTRAINT_REGISTRY[constraint_name] = fn
        return fn
    return decorator


def list_custom_constraints() -> list:
    """Return the names of all registered custom constraints."""
    return list(_CUSTOM_CONSTRAINT_REGISTRY.keys())


def unregister_constraint(constraint_name: str) -> bool:
    """Remove a custom constraint. Returns True if it existed."""
    if constraint_name in _CUSTOM_CONSTRAINT_REGISTRY:
        del _CUSTOM_CONSTRAINT_REGISTRY[constraint_name]
        return True
    return False

def check_compliance(params, result, y_star_t):
    """
    Enhanced compliance checking with multiple constraint types
    
    Supported constraints:
    - max, min: Numeric bounds
    - regex: Pattern matching
    - blocklist, allowlist: Value restrictions
    - enum: Allowed values
    - min_length, max_length: String length
    - type: Type validation
    """
    constraints = y_star_t.get('constraints', {})
    
    if not constraints:
        return {
            'passed': True,
            'violations': [],
            'overall_severity': 0.0,
            'risk_level': 'LOW'
        }
    
    violations = []

    # ── deny_content: substring blocklist across all param values ──────────
    deny_terms = constraints.get('deny_content', [])
    if deny_terms:
        all_values = ' '.join(str(v) for v in params.values())
        for term in deny_terms:
            term_lower = term.lower()
            if term_lower in all_values.lower():
                violations.append({
                    'type': 'DENY_CONTENT',
                    'field': 'content',
                    'matched': term,
                    'severity': 0.9,
                    'message': f'Content contains forbidden pattern: {term!r}',
                })
                break  # one violation per deny_content check is enough

    # -- Top-level allowed_paths: check path-like params ---------------------
    allowed_paths_top = constraints.get('allowed_paths', [])
    if allowed_paths_top:
        PATH_PARAM_NAMES = {"path", "file_path", "filepath", "dest",
                            "destination", "output", "target", "filename"}
        for p_name, p_value in params.items():
            if p_name.lower() in PATH_PARAM_NAMES or p_name.lower().endswith("path"):
                violation = None
                import fnmatch as _fnmatch
                _path = str(p_value).replace("\\", "/")
                _allowed = False
                for _pat in allowed_paths_top:
                    _pat = _pat.replace("\\", "/")
                    if "**" in _pat:
                        _base = _pat.split("**")[0].rstrip("/").lstrip("./")
                        if _path.lstrip("./").startswith(_base):
                            _allowed = True; break
                    elif _fnmatch.fnmatch(_path, _pat) or _fnmatch.fnmatch(_path.lstrip("./"), _pat.lstrip("./")):
                        _allowed = True; break
                if not _allowed:
                    violation = {"type": "PATH_VIOLATION", "field": p_name,
                        "actual": str(p_value), "constraint": f"allowed_paths={allowed_paths_top}",
                        "severity": 0.8, "message": f"Path '{p_value}' is outside allowed directories"}
                if violation:
                    violations.append(violation)

    # Flatten Y_t+1.result for output field checking
    result_flat = {}
    if isinstance(result, dict):
        result_obj = result.get("result", result)
        if isinstance(result_obj, dict):
            result_flat = result_obj

    _TOP_LEVEL_KEYS = {"deny_content", "allowed_paths"}
    for param_name, rules in constraints.items():
        if param_name in _TOP_LEVEL_KEYS:
            continue
        if param_name in params:
            value = params[param_name]
        elif param_name in result_flat:
            # Y*_t constraint targets output field (Y_t+1.result)
            value = result_flat[param_name]
        else:
            continue
        
        # Type checking
        if 'type' in rules:
            expected_type = rules['type']
            if not _check_type(value, expected_type):
                violations.append({
                    'type': 'type_mismatch',
                    'field': param_name,
                    'actual': type(value).__name__,
                    'constraint': f"type={expected_type}",
                    'severity': 0.7,
                    'message': f"{param_name} type mismatch: expected {expected_type}, got {type(value).__name__}"
                })
        
        # Numeric constraints
        if 'max' in rules:
            violation = _check_max(param_name, value, rules['max'])
            if violation:
                violations.append(violation)
        
        if 'min' in rules:
            violation = _check_min(param_name, value, rules['min'])
            if violation:
                violations.append(violation)
        
        # String constraints
        if 'regex' in rules:
            violation = _check_regex(param_name, value, rules['regex'])
            if violation:
                violations.append(violation)
        
        if 'min_length' in rules:
            violation = _check_min_length(param_name, value, rules['min_length'])
            if violation:
                violations.append(violation)
        
        if 'max_length' in rules:
            violation = _check_max_length(param_name, value, rules['max_length'])
            if violation:
                violations.append(violation)
        
        # List constraints
        if 'blocklist' in rules:
            violation = _check_blocklist(
                param_name, value, rules['blocklist'],
                case_sensitive=rules.get('case_sensitive', False)
            )
            if violation:
                violations.append(violation)
        
        if 'allowlist' in rules:
            violation = _check_allowlist(param_name, value, rules['allowlist'])
            if violation:
                violations.append(violation)
        
        if 'enum' in rules:
            violation = _check_enum(param_name, value, rules['enum'])
            if violation:
                violations.append(violation)

        # Custom constraints: any key not recognised above
        _BUILTIN_KEYS = {
            'type', 'max', 'min', 'regex',
            'min_length', 'max_length',
            'blocklist', 'allowlist', 'enum',
            'description',  # metadata-only, not a constraint
        }
        for rule_key, rule_value in rules.items():
            if rule_key in _BUILTIN_KEYS:
                continue
            checker = _CUSTOM_CONSTRAINT_REGISTRY.get(rule_key)
            if checker is None:
                import logging as _logging
                _logging.getLogger('k9log').warning(
                    "k9log: unknown constraint type '%s' on param '%s'. "
                    "Register it with @register_constraint.",
                    rule_key, param_name
                )
                continue
            try:
                violation = checker(param_name, value, rule_value)
                if violation:
                    violations.append(violation)
            except Exception as e:
                import logging as _logging
                _logging.getLogger('k9log').warning(
                    "k9log: custom constraint '%s' raised an error for param '%s': %s",
                    rule_key, param_name, e
                )
    
    # Calculate overall assessment
    passed = len(violations) == 0
    overall_severity = max([v['severity'] for v in violations]) if violations else 0.0
    
    if overall_severity >= 0.8:
        risk_level = 'CRITICAL'
    elif overall_severity >= 0.5:
        risk_level = 'HIGH'
    elif overall_severity >= 0.3:
        risk_level = 'MEDIUM'
    else:
        risk_level = 'LOW'
    
    return {
        'passed': passed,
        'violations': violations,
        'overall_severity': overall_severity,
        'risk_level': risk_level
    }

# Helper functions for constraint checking

def _check_type(value, expected_type):
    """Check type constraint"""
    type_map = {
        'string': str,
        'number': (int, float),
        'integer': int,
        'float': float,
        'boolean': bool,
        'list': list,
        'dict': dict
    }
    expected = type_map.get(expected_type, str)
    return isinstance(value, expected)

def _check_max(param_name, value, max_val):
    """Check max constraint"""
    try:
        if float(value) > float(max_val):
            excess = float(value) - float(max_val)
            severity = min(1.0, excess / float(max_val))
            return {
                'type': 'numeric_exceeded',
                'field': param_name,
                'actual': value,
                'constraint': f"max={max_val}",
                'excess': excess,
                'severity': severity,
                'message': f"{param_name}={value} exceeds max={max_val}"
            }
    except (ValueError, TypeError):
        pass
    return None

def _check_min(param_name, value, min_val):
    """Check min constraint"""
    try:
        if float(value) < float(min_val):
            deficit = float(min_val) - float(value)
            severity = min(1.0, deficit / float(min_val)) if float(min_val) != 0 else 0.5
            return {
                'type': 'numeric_below',
                'field': param_name,
                'actual': value,
                'constraint': f"min={min_val}",
                'deficit': deficit,
                'severity': severity,
                'message': f"{param_name}={value} below min={min_val}"
            }
    except (ValueError, TypeError):
        pass
    return None

def _check_regex(param_name, value, pattern):
    """Check regex constraint"""
    try:
        if not re.match(pattern, str(value)):
            return {
                'type': 'regex_mismatch',
                'field': param_name,
                'actual': value,
                'constraint': f"regex={pattern}",
                'severity': 0.6,
                'message': f"{param_name}={value} does not match pattern {pattern}"
            }
    except re.error:
        pass
    return None

def _check_min_length(param_name, value, min_len):
    """Check min_length constraint"""
    try:
        if len(str(value)) < min_len:
            return {
                'type': 'length_too_short',
                'field': param_name,
                'actual': len(str(value)),
                'constraint': f"min_length={min_len}",
                'severity': 0.4,
                'message': f"{param_name} length {len(str(value))} < min {min_len}"
            }
    except TypeError:
        pass
    return None

def _check_max_length(param_name, value, max_len):
    """Check max_length constraint"""
    try:
        if len(str(value)) > max_len:
            return {
                'type': 'length_too_long',
                'field': param_name,
                'actual': len(str(value)),
                'constraint': f"max_length={max_len}",
                'severity': 0.4,
                'message': f"{param_name} length {len(str(value))} > max {max_len}"
            }
    except TypeError:
        pass
    return None

def _check_blocklist(param_name, value, blocklist, case_sensitive=False):
    """Check blocklist constraint with three-tier matching.

    For each entry in *blocklist*, the following checks run in order:

    1. **Regex** – entries starting with ``re:`` are compiled as patterns
       and tested via ``re.search`` against ``str(value)``.
    2. **Exact** – ``value == entry`` (preserves backward compatibility).
    3. **Substring** – ``str(entry) in str(value)`` so that
       ``"sudo rm -rf /home"`` is caught by the entry ``"rm -rf /"``.

    The violation dict includes *match_mode* and *matched_entry* so that
    downstream consumers (L1 causal DAG, HTML report) can distinguish
    the three tiers.
    """
    str_value = str(value)
    for entry in blocklist:
        entry_str = str(entry)

        # ── Tier 1: regex (prefix 're:') ──
        if entry_str.startswith('re:'):
            pattern = entry_str[3:]
            try:
                if re.search(pattern, str_value):
                    return {
                        'type': 'blocklist_hit',
                        'field': param_name,
                        'actual': value,
                        'constraint': f'blocklist_regex({pattern})',
                        'matched_entry': entry_str,
                        'match_mode': 'regex',
                        'severity': 0.9,
                        'message': f"{param_name} matches blocklist regex: {pattern}"
                    }
            except re.error:
                pass  # malformed pattern – skip silently
            continue

        # ── Tier 2: exact ──
        cmp_value = str_value if case_sensitive else str_value.lower()
        cmp_entry = entry_str if case_sensitive else entry_str.lower()
        if cmp_value == cmp_entry:
            return {
                'type': 'blocklist_hit',
                'field': param_name,
                'actual': value,
                'constraint': 'blocklist',
                'matched_entry': entry_str,
                'match_mode': 'exact',
                'severity': 0.9,
                'message': f"{param_name}={value} in blocklist (exact)"
            }

        # ── Tier 3: substring ──
        if cmp_entry in cmp_value:
            return {
                'type': 'blocklist_hit',
                'field': param_name,
                'actual': value,
                'constraint': 'blocklist_substring',
                'matched_entry': entry_str,
                'match_mode': 'substring',
                'severity': 0.9,
                'message': (f"{param_name} contains blocklist entry "
                            f"'{entry_str}'")
            }

    return None

def _check_allowlist(param_name, value, allowlist):
    """Check allowlist constraint"""
    if value not in allowlist:
        return {
            'type': 'allowlist_miss',
            'field': param_name,
            'actual': value,
            'constraint': 'allowlist',
            'severity': 0.8,
            'message': f"{param_name}={value} not in allowlist"
        }
    return None

def _check_enum(param_name, value, enum_values):
    """Check enum constraint"""
    if value not in enum_values:
        return {
            'type': 'enum_violation',
            'field': param_name,
            'actual': value,
            'constraint': f"enum={enum_values}",
            'severity': 0.7,
            'message': f"{param_name}={value} not in allowed values {enum_values}"
        }
    return None

