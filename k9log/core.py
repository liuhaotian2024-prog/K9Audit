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
K9log Core - @k9 decorator and CIEU recording engine

Log level control
-----------------
Set the environment variable K9LOG_LEVEL to control verbosity:

  K9LOG_LEVEL=DEBUG   -- emit detailed per-call trace to the k9log logger
  K9LOG_LEVEL=INFO    -- emit violation summaries only (default)
  K9LOG_LEVEL=OFF     -- suppress all k9log diagnostic output

Example (PowerShell):
  $env:K9LOG_LEVEL = "DEBUG"
  python my_agent.py
"""
import time
import functools
import inspect
import logging
import os
import socket
from datetime import datetime, timezone

from k9log.logger import get_logger
from k9log.identity import get_agent_identity
from k9log.constraints import load_constraints, check_compliance
from k9log.redact import redact_params, redact_context, redact_result, _redact_value

# -- Log level control --------------------------------------------------------
_K9_LEVEL = os.environ.get('K9LOG_LEVEL', 'INFO').upper()
_DEBUG   = _K9_LEVEL == 'DEBUG'
_SILENT  = _K9_LEVEL == 'OFF'
_k9_log  = logging.getLogger('k9log.core')

def k9(func=None, **inline_constraints):
    """
    K9log decorator for automatic CIEU recording
    
    Args:
        func: Function to wrap (when used without parameters)
        **inline_constraints: Inline constraint definitions
    
    Usage:
        @k9
        def my_skill(param1, param2):
            return result
        
        # Or with inline constraints:
        @k9(param1={'max': 100})
        def my_skill(param1, param2):
            return result
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            start_time = time.time()

            if _DEBUG:
                _k9_log.debug('[k9] -> entering %s', f.__name__)

            # Get logger and identity
            logger = get_logger()
            identity = get_agent_identity()

            # 1. Capture X_t (Context)
            x_t = _capture_context(f, identity)

            # 2. Capture U_t (Action)
            u_t = _capture_action(f, args, kwargs)

            if _DEBUG:
                _k9_log.debug('[k9] U_t params: %s', list(u_t['params'].keys()))

            # 3. Load Y*_t (Constraints)
            y_star_t = _load_constraints(f, inline_constraints)

            if _DEBUG:
                _k9_log.debug('[k9] constraints loaded: hash=%s',
                              y_star_t.get('hash', 'none')[:16])
            
            # 4. Execute function and capture Y_t+1
            execution_error = None
            y_t_plus_1 = None
            
            try:
                result = f(*args, **kwargs)
                y_t_plus_1 = {'result': result, 'status': 'success'}
            except Exception as e:
                execution_error = str(e)
                y_t_plus_1 = {'status': 'error', 'error': execution_error}
                raise
            finally:
                # 5. Calculate R_t+1 (Assessment)
                end_time = time.time()
                r_t_plus_1 = _assess_compliance(
                    u_t['params'], 
                    y_t_plus_1, 
                    y_star_t,
                    execution_error
                )
                r_t_plus_1['duration_sec'] = end_time - start_time
                
                # 6. Apply redaction
                x_t = redact_context(x_t)
                u_t_redacted = dict(u_t)
                u_t_redacted['params'] = redact_params(u_t['params'])
                y_t_plus_1 = redact_result(y_t_plus_1)

                # 6b. Redact sensitive values leaked into violations
                if r_t_plus_1.get('violations'):
                    for v in r_t_plus_1['violations']:
                        if 'actual' in v and isinstance(v['actual'], str):
                            v['actual'] = _redact_value(v['actual'])
                        if 'message' in v and isinstance(v['message'], str):
                            v['message'] = _redact_value(v['message'])

                # 7. Write CIEU record
                cieu_record = {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'X_t': x_t,
                    'U_t': u_t_redacted,
                    'Y_star_t': y_star_t,
                    'Y_t+1': y_t_plus_1,
                    'R_t+1': r_t_plus_1
                }

                if _DEBUG:
                    status = 'PASS' if r_t_plus_1.get('passed') else 'FAIL'
                    _k9_log.debug('[k9] %s %s -- %.3fs -- severity=%.2f',
                                  status, f.__name__,
                                  r_t_plus_1['duration_sec'],
                                  r_t_plus_1.get('overall_severity', 0.0))
                    for v in r_t_plus_1.get('violations', []):
                        _k9_log.debug('[k9]   violation: %s on field=%s',
                                      v.get('type'), v.get('field'))
                elif not _SILENT and not r_t_plus_1.get('passed', True):
                    _k9_log.info('[k9] violation in %s: %s',
                                 f.__name__,
                                 ', '.join(v.get('type', '?')
                                           for v in r_t_plus_1.get('violations', [])))

                if not _SILENT:
                    logger.write_cieu(cieu_record)

                # 8. Trigger alerting on violations
                if not r_t_plus_1.get('passed', True):
                    try:
                        from k9log.alerting import get_alert_manager
                        manager = get_alert_manager()
                        manager.on_violation(cieu_record)
                    except Exception:
                        pass  # alerting failure must never break the decorated function
            
            return result
        
        # Remove __wrapped__ to prevent bypass via direct original function call
        try:
            del wrapper.__wrapped__
        except AttributeError:
            pass
        return wrapper
    
    # Handle both @k9 and @k9(...) syntax
    if func is None:
        return decorator
    else:
        return decorator(func)

def _capture_context(func, identity):
    """Capture X_t (Context)"""
    frame = inspect.currentframe().f_back.f_back
    
    x_t = {
        'ts': time.time(),
        'datetime': datetime.now(timezone.utc).isoformat(),
        'user': os.environ.get('USER', os.environ.get('USERNAME', 'unknown')),
        'hostname': socket.gethostname(),
        'pid': os.getpid(),
        'caller': {
            'file': frame.f_code.co_filename,
            'line': frame.f_lineno,
            'function': frame.f_code.co_name
        }
    }
    
    # Add agent identity if available
    if identity:
        x_t['agent_id'] = identity.get('agent_id')
        x_t['agent_name'] = identity.get('agent_name')
        x_t['agent_type'] = identity.get('agent_type')
        x_t['agent_metadata'] = identity.get('metadata', {})

    # Add skill provenance (X_t.skill_source)
    try:
        from k9log.skill_source import get_active_skill_source
        x_t['skill_source'] = get_active_skill_source(
            session_id=x_t.get('agent_id', '')
        )
    except Exception:
        pass  # never break decorated functions

    return x_t

def _capture_action(func, args, kwargs):
    """Capture U_t (Action)"""
    sig = inspect.signature(func)
    bound_args = sig.bind(*args, **kwargs)
    bound_args.apply_defaults()

    import json as _json
    def _safe(v):
        if v is None or isinstance(v, (bool, int, float, str)):
            return v
        if isinstance(v, (list, tuple)):
            return [_safe(i) for i in v]
        if isinstance(v, dict):
            return {str(k): _safe(val) for k, val in v.items()}
        try:
            _json.dumps(v)
            return v
        except (TypeError, ValueError):
            return f'<{type(v).__name__}>'

    safe_params = {
        k: _safe(v)
        for k, v in bound_args.arguments.items()
        if k != 'self'
    }

    return {
        'skill': func.__name__,
        'skill_module': func.__module__,
        'params': safe_params
    }

def _load_constraints(func, inline_constraints):
    """Load Y*_t (Constraints) with versioning"""
    from k9log.constraints import load_constraints
    return load_constraints(func.__name__, inline_constraints)

def _assess_compliance(params, result, y_star_t, execution_error):
    """Calculate R_t+1 (Assessment)"""
    from k9log.constraints import check_compliance
    
    if execution_error:
        # Runtime errors (ModuleNotFoundError, FileNotFoundError, timeout, etc.)
        # are NOT security violations — use lower severity to avoid false fuse triggers
        err_str = str(execution_error)
        is_security = any(k in err_str.lower() for k in [
            'permission', 'access denied', 'blocklist', 'constraint', 'violation',
            'unauthorized', 'forbidden', 'inject', 'traversal'
        ])
        severity = 0.8 if is_security else 0.2
        risk = 'HIGH' if is_security else 'LOW'
        return {
            'passed': False,
            'violations': [],
            'execution_error': execution_error,
            'overall_severity': severity,
            'risk_level': risk,
            'error_type': 'security_error' if is_security else 'runtime_error',
        }
    
    return check_compliance(params, result, y_star_t)

