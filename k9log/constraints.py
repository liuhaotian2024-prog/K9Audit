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

# Track which skills have already emitted the UNCONSTRAINED warning this process,
# so users aren't flooded with identical messages on repeated calls.
_unconstrained_warned: set = set()

def _find_agents_md() -> list:
    """
    Search for AGENTS.md or CLAUDE.md in standard locations.
    Returns list of found paths in priority order.
    """
    candidates = []
    search_dirs = [
        Path.cwd(),                                           # current working directory
        Path.home() / '.openclaw' / 'workspace',             # OpenClaw main workspace
        Path.home() / '.openclaw',                           # OpenClaw home
        Path.home() / '.claude',                             # Claude Code home
        Path.home(),                                         # user home
    ]
    # Also add per-agent workspaces dynamically
    agents_dir = Path.home() / '.openclaw' / 'agents'
    if agents_dir.exists():
        for agent_ws in agents_dir.glob('*/workspace'):
            if agent_ws not in search_dirs:
                search_dirs.append(agent_ws)
    filenames = ['AGENTS.md', 'CLAUDE.md', 'agents.md', 'claude.md']
    seen = set()
    for d in search_dirs:
        for fname in filenames:
            p = d / fname
            if p.exists() and str(p) not in seen:
                candidates.append(p)
                seen.add(str(p))
    return candidates


def load_constraints(skill_name, inline_constraints=None):
    """
    Load Y*_t with versioning metadata

    Priority:
    1. Inline constraints (runtime override)
    2. Config file (~/.k9log/config/skill_name.json)
    3. AGENTS.md / CLAUDE.md auto-detection (OpenClaw / Claude Code)
    4. Empty constraints (recorded as UNCONSTRAINED)
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
                logging.getLogger('k9log').warning(
                    'k9log: failed to load constraints from %s: %s', config_file, e)

    # Priority 3: AGENTS.md / CLAUDE.md auto-detection
    if not constraints:
        try:
            from k9log.agents_md_parser import parse_agents_md_to_constraints
            for agents_path in _find_agents_md():
                parsed = parse_agents_md_to_constraints(agents_path)
                if parsed:
                    constraints = parsed
                    source = 'agents_md'
                    source_path = str(agents_path)
                    version = '1.0.0'
                    logging.getLogger('k9log').info(
                        'k9log: loaded constraints from %s (%d rules)',
                        agents_path, sum(len(v) if isinstance(v, list) else 1
                                        for v in parsed.values()))
                    break
        except Exception as e:
            logging.getLogger('k9log').debug(
                'k9log: agents_md auto-load failed: %s', e)

    # Calculate hash
    y_star_hash = hash_ystar(constraints)

    # Warn if no constraints found -- unconstrained calls are recorded
    # but violations cannot be detected, which is a security gap.
    # Warning fires once per skill per process to avoid log spam.
    if not constraints and skill_name not in _unconstrained_warned:
        _unconstrained_warned.add(skill_name)
        logging.getLogger('k9log').warning(
            'k9log: skill "%s" has no constraints (no inline rules, no config file, '
            'no AGENTS.md) -- call will be recorded as UNCONSTRAINED', skill_name
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
                    _pat_norm = _pat.replace("\\", "/").rstrip("/")
                    _path_norm = _path.rstrip("/")
                    # 1. Exact match
                    if _path_norm == _pat_norm:
                        _allowed = True; break
                    # 2. File is inside allowed directory
                    if _path_norm.startswith(_pat_norm + "/"):
                        _allowed = True; break
                    # 3. Glob with **
                    if "**" in _pat_norm:
                        _base = _pat_norm.split("**")[0].rstrip("/").lstrip("./")
                        if _path.lstrip("./").startswith(_base):
                            _allowed = True; break
                    # 4. fnmatch pattern
                    if _fnmatch.fnmatch(_path, _pat_norm) or _fnmatch.fnmatch(_path.lstrip("./"), _pat_norm.lstrip("./")):
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
    
    # ── postcondition: expression evaluated against result + params ──────────
    postconditions = constraints.get('postcondition', [])
    if isinstance(postconditions, str):
        postconditions = [postconditions]
    for expr in postconditions:
        violation = _check_postcondition(expr, params, result)
        if violation:
            violations.append(violation)

    # ── invariant: always-true expression ─────────────────────────────────
    invariants = constraints.get('invariant', [])
    if isinstance(invariants, str):
        invariants = [invariants]
    for expr in invariants:
        violation = _check_invariant(expr, params, result)
        if violation:
            violations.append(violation)

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



def _eval_expr(expr, params, result):
    """
    Safely evaluate a postcondition/invariant expression.
    Available variables:
      - result: the function return value (Y_t+1.result)
      - params: dict of input parameters
      - each param name unpacked as a direct variable
    Returns (bool, exception_or_None)
    """
    # Build a safe namespace
    # Unwrap Y_t+1 envelope: {result: {...}} -> {...}
    # so postconditions can write result["status"] not result["result"]["status"]
    result_val = result
    if isinstance(result, dict) and 'result' in result:
        result_val = result['result']

    namespace = {
        '__builtins__': {
            'abs': abs, 'len': len, 'int': int, 'float': float,
            'str': str, 'bool': bool, 'list': list, 'dict': dict,
            'min': min, 'max': max, 'sum': sum, 'round': round,
            'isinstance': isinstance, 'hasattr': hasattr,
            'True': True, 'False': False, 'None': None,
        },
        'result': result_val,
        'result_raw': result,
        'params': params,
    }
    # Unpack params as direct variables for convenience
    # e.g. postcondition: "amount > 0" instead of "params['amount'] > 0"
    for k, v in (params or {}).items():
        if k.isidentifier():
            namespace[k] = v
    try:
        value = eval(compile(expr, '<postcondition>', 'eval'), namespace)
        return bool(value), None
    except Exception as e:
        return False, e


def _check_postcondition(expr, params, result):
    """Check a postcondition expression against execution result."""
    passed, err = _eval_expr(expr, params, result)
    if err is not None:
        return {
            'type': 'CODE_INVARIANT',
            'rule_id': 'POST-EVAL',
            'field': 'postcondition',
            'matched': expr,
            'severity': 0.7,
            'message': f'Postcondition eval error: {expr!r} — {err}',
        }
    if not passed:
        return {
            'type': 'CODE_INVARIANT',
            'rule_id': 'POST-001',
            'field': 'postcondition',
            'matched': expr,
            'severity': 0.85,
            'message': f'Postcondition violated: {expr!r}',
        }
    return None


def _check_invariant(expr, params, result):
    """Check an invariant expression — must always be true."""
    passed, err = _eval_expr(expr, params, result)
    if err is not None:
        return {
            'type': 'CODE_INVARIANT',
            'rule_id': 'INV-EVAL',
            'field': 'invariant',
            'matched': expr,
            'severity': 0.7,
            'message': f'Invariant eval error: {expr!r} — {err}',
        }
    if not passed:
        return {
            'type': 'CODE_INVARIANT',
            'rule_id': 'INV-001',
            'field': 'invariant',
            'matched': expr,
            'severity': 0.9,
            'message': f'Invariant violated: {expr!r}',
        }
    return None


def parse_k9contract(docstring):
    """
    Parse K9Contract block from a Python function docstring.

    Format:
        K9Contract:
          postcondition: result > 0
          postcondition: result is not None
          invariant: amount > 0

    Returns dict with keys: postcondition (list), invariant (list)
    """
    if not docstring:
        return {}
    contract = {'postcondition': [], 'invariant': []}
    in_contract = False
    for line in docstring.splitlines():
        stripped = line.strip()
        if stripped == 'K9Contract:':
            in_contract = True
            continue
        if in_contract:
            if not stripped:
                continue
            # Stop if we hit another section (unindented text)
            if not line.startswith(' ') and not line.startswith('	'):
                break
            if stripped.startswith('postcondition:'):
                expr = stripped[len('postcondition:'):].strip()
                if expr:
                    contract['postcondition'].append(expr)
            elif stripped.startswith('invariant:'):
                expr = stripped[len('invariant:'):].strip()
                if expr:
                    contract['invariant'].append(expr)
    # Remove empty keys
    return {k: v for k, v in contract.items() if v}


def _infer_contracts_from_ast(source, func_node):
    """
    Apply K9 Law to infer missing contracts from AST.
    Rules:
      INV-NUM:     numeric param used in comparison → invariant: param > 0 (or >= 0)
      INV-STR:     string param used → invariant: len(param) > 0
      POST-RETURN: function returns dict with known keys → postcondition per key
      POST-NOTNONE: function has return statement → postcondition: result is not None
      INV-RAISE:   if param < 0: raise → invariant: param >= 0
    Returns {postcondition: [...], invariant: [...]}
    """
    inferred = {'postcondition': [], 'invariant': []}

    try:
        import ast as _ast_mod
        args = [a.arg for a in func_node.args.args if a.arg != 'self']

        # Collect all comparisons in function body
        for node in _ast_mod.walk(func_node):

            # INV-RAISE: detect `if param < 0: raise ...`
            if isinstance(node, _ast_mod.If):
                test = node.test
                # Check if body contains a Raise
                has_raise = any(isinstance(n, _ast_mod.Raise)
                                for n in _ast_mod.walk(node))
                if has_raise and isinstance(test, _ast_mod.Compare):
                    if isinstance(test.left, _ast_mod.Name):
                        param = test.left.id
                        if param in args and len(test.ops) == 1:
                            op = test.ops[0]
                            comp = test.comparators[0]
                            comp_val = None
                            if isinstance(comp, _ast_mod.Constant):
                                comp_val = comp.value
                            # if param < 0 raise → invariant: param >= 0
                            if isinstance(op, _ast_mod.Lt) and comp_val == 0:
                                inv = f'{param} >= 0'
                                if inv not in inferred['invariant']:
                                    inferred['invariant'].append(inv)
                            # if param <= 0 raise → invariant: param > 0
                            elif isinstance(op, _ast_mod.LtE) and comp_val == 0:
                                inv = f'{param} > 0'
                                if inv not in inferred['invariant']:
                                    inferred['invariant'].append(inv)

            # INV-NUM: param used in numeric comparison (not raise-guarded)
            if isinstance(node, _ast_mod.Compare):
                if isinstance(node.left, _ast_mod.Name):
                    param = node.left.id
                    if param in args:
                        for op, comp in zip(node.ops, node.comparators):
                            if isinstance(comp, _ast_mod.Constant):
                                if isinstance(comp.value, (int, float)):
                                    if comp.value == 0:
                                        inv = f'{param} >= 0'
                                        if inv not in inferred['invariant']:
                                            inferred['invariant'].append(inv)

            # POST-RETURN: detect return {"key": ...} patterns
            if isinstance(node, _ast_mod.Return) and node.value:
                if isinstance(node.value, _ast_mod.Dict):
                    for key in node.value.keys:
                        if isinstance(key, _ast_mod.Constant) and isinstance(key.value, str):
                            post = f'result is not None'
                            if post not in inferred['postcondition']:
                                inferred['postcondition'].append(post)
                            key_post = f'"{key.value}" in result'
                            if key_post not in inferred['postcondition']:
                                inferred['postcondition'].append(key_post)

        # POST-NOTNONE: any function with a return value
        has_return_value = any(
            isinstance(n, _ast_mod.Return) and n.value is not None
            for n in _ast_mod.walk(func_node)
        )
        if has_return_value:
            post = 'result is not None'
            if post not in inferred['postcondition']:
                inferred['postcondition'].append(post)

        # INV-STR: string params (annotated as str or named with str hints)
        for arg in func_node.args.args:
            if arg.arg == 'self':
                continue
            ann = arg.annotation
            if ann and isinstance(ann, _ast_mod.Name) and ann.id == 'str':
                inv = f'len({arg.arg}) > 0'
                if inv not in inferred['invariant']:
                    inferred['invariant'].append(inv)

    except Exception:
        pass

    return {k: v for k, v in inferred.items() if v}


def _merge_contracts(parsed, inferred):
    """
    Merge agent-written contract with K9-inferred contract.
    Agent-written takes priority; inferred fills gaps.
    Records which rules were inferred (for transparency).
    """
    merged = {
        'postcondition': list(parsed.get('postcondition', [])),
        'invariant': list(parsed.get('invariant', [])),
        '_inferred': [],
    }

    for expr in inferred.get('postcondition', []):
        if expr not in merged['postcondition']:
            merged['postcondition'].append(expr)
            merged['_inferred'].append(f'POST:{expr}')

    for expr in inferred.get('invariant', []):
        if expr not in merged['invariant']:
            merged['invariant'].append(expr)
            merged['_inferred'].append(f'INV:{expr}')

    if not merged['_inferred']:
        del merged['_inferred']

    return {k: v for k, v in merged.items() if v}


_MAGIC_AST_RULES = [
    {"name":"file_write","detect":lambda n:isinstance(n,__import__("ast").Call) and isinstance(n.func,__import__("ast").Name) and n.func.id=="open" and any(isinstance(a,__import__("ast").Constant) and isinstance(a.value,str) and "w" in a.value for a in list(n.args[1:])+[kw.value for kw in n.keywords if kw.arg=="mode"]),"suggest":{"allowed_paths":["./output/**","./*.json","./*.yaml"]},"reason":"writes files","confidence":0.85},
    {"name":"network","detect":lambda n:isinstance(n,__import__("ast").Attribute) and n.attr in("get","post","put","delete","patch","request") and isinstance(n.value,__import__("ast").Name) and n.value.id in("requests","httpx","urllib","aiohttp"),"suggest":{"deny_content":["staging.internal","*.internal","localhost","127.0.0.1"]},"reason":"makes HTTP requests","confidence":0.85},
    {"name":"subprocess","detect":lambda n:isinstance(n,__import__("ast").Attribute) and n.attr in("run","call","Popen","check_output") and isinstance(n.value,__import__("ast").Name) and n.value.id=="subprocess","suggest":{"deny_content":["rm -rf","| bash","| sh","dd if="]},"reason":"runs shell commands","confidence":0.85},
    {"name":"db","detect":lambda n:isinstance(n,__import__("ast").Attribute) and n.attr in("execute","executemany","query","raw") and isinstance(n.value,__import__("ast").Name),"suggest":{"deny_content":["DROP TABLE","DROP DATABASE","; --"]},"reason":"executes DB queries","confidence":0.85},
]
_MAGIC_PARAM_RULES = [
    (["endpoint","url","host","base_url","api_url"],{"deny_content":["staging.internal","*.internal","localhost","127.0.0.1"]},"URL param",0.8),
    (["environment","env","target_env","deploy_to"],"blocklist_prod","environment param",0.8),
    (["query","sql","statement"],{"deny_content":["DROP TABLE","DROP DATABASE","; --"]},"SQL param",0.8),
    (["path","file_path","filepath","output_path"],{"allowed_paths":["./output/**","./data/**"]},"file path param",0.75),
    (["command","cmd","shell_cmd"],{"deny_content":["rm -rf","| bash","| sh"]},"command param",0.8),
    (["amount","price","value","quantity","qty"],"max_10000","numeric param",0.7),
    (["token","api_key","secret","password"],{"deny_content":["sk-","ghp_","xoxb-","AKIA"]},"credential param",0.85),
]

def infer_magic_suggestions(source, func_node):
    import ast as _a
    suggestions, seen = [], set()
    for node in _a.walk(func_node):
        for rule in _MAGIC_AST_RULES:
            try:
                if rule["detect"](node):
                    k = str(rule["suggest"])
                    if k not in seen:
                        seen.add(k)
                        suggestions.append({"constraint":rule["suggest"],"reason":f"{func_node.name}() {rule['reason']}","confidence":rule["confidence"],"source":f"ast:{rule['name']}"})
            except Exception:
                pass
    args = [a.arg for a in func_node.args.args if a.arg not in ("self","cls")]
    for arg in args:
        for patterns, suggest_tmpl, reason, conf in _MAGIC_PARAM_RULES:
            if any(p in arg.lower() for p in patterns):
                if suggest_tmpl == "blocklist_prod": final = {arg:{"blocklist":["production","prod"]}}
                elif suggest_tmpl == "max_10000": final = {arg:{"max":10000}}
                else: final = suggest_tmpl
                k = f"{arg}:{final}"
                if k not in seen:
                    seen.add(k)
                    suggestions.append({"constraint":final,"reason":f"param '{arg}': {reason}","confidence":conf,"source":f"param:{arg}"})
    suggestions.sort(key=lambda s:s["confidence"],reverse=True)
    return suggestions
