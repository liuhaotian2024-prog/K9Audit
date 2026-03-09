# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
# AGPL-3.0
"""
K9log AutoContract - Automatic contract injection via sys.meta_path

When imported, installs a module loader that automatically wraps
functions with K9Contract in ~/.k9log/config/ with a lightweight
@k9-style validator. No @k9 decorator required.

Usage (add to top of any Python file written by Claude Code):
    import k9log.autocontract

After this, any function in the same module that has a saved contract
in ~/.k9log/config/{function_name}.json will be automatically monitored.
"""
import sys
import json
import time
import importlib.abc
import importlib.machinery
from pathlib import Path


def _load_contract(func_name):
    """Load saved K9Contract from ~/.k9log/config/{func_name}.json"""
    config_file = Path.home() / ".k9log" / "config" / f"{func_name}.json"
    if not config_file.exists():
        return None
    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
        constraints = data.get("constraints", {})
        if constraints:
            return {"constraints": constraints}
    except Exception:
        pass
    return None


def _make_wrapper(func, y_star_t, func_name):
    """
    Wrap a function with lightweight K9 contract verification.
    Records violation to CIEU ledger and fires alert if contract broken.
    Never raises - always returns the original result.
    """
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        t0 = time.time()
        result = None
        error = None
        try:
            result = func(*args, **kwargs)
        except Exception as e:
            error = e

        try:
            from k9log.constraints import check_compliance
            from k9log.logger import get_logger

            # Build params dict from positional + keyword args
            import inspect
            try:
                sig = inspect.signature(func)
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                params = dict(bound.arguments)
                # Remove self/cls
                params.pop("self", None)
                params.pop("cls", None)
            except Exception:
                params = {}

            result_wrapped = {"result": result}
            r = check_compliance(params, result_wrapped, y_star_t)

            if not r["passed"]:
                # Write violation to CIEU ledger
                import os, socket, hashlib
                from datetime import datetime, timezone

                cieu = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event_type": "AUTOCONTRACT",
                    "X_t": {
                        "agent_name": "autocontract",
                        "agent_type": "runtime_verifier",
                        "session_id": "autocontract",
                        "user": os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
                        "hostname": socket.gethostname(),
                    },
                    "U_t": {"skill": func_name, "params": _safe_params(params)},
                    "Y_star_t": y_star_t,
                    "Y_t+1": {
                        "status": "error" if error else "success",
                        "result": _safe_result(result),
                    },
                    "R_t+1": r,
                }
                try:
                    get_logger().write_cieu(cieu)
                except Exception:
                    pass

                # Fire alert
                try:
                    from k9log.alerting import get_alert_manager
                    get_alert_manager().on_violation(cieu)
                except Exception:
                    pass

                # Write to stderr so Claude Code can see it
                for v in r["violations"]:
                    sys.stderr.write(
                        f"[k9log] CONTRACT VIOLATION in {func_name}: "
                        f"{v['message']}\n"
                    )

        except Exception:
            pass  # autocontract must never crash the wrapped function

        if error:
            raise error
        return result

    return wrapper


def _safe_params(params):
    """Serialize params safely for CIEU record."""
    out = {}
    for k, v in params.items():
        try:
            json.dumps(v)
            out[k] = v
        except Exception:
            out[k] = str(v)[:200]
    return out


def _safe_result(result):
    """Serialize result safely for CIEU record."""
    try:
        json.dumps(result)
        return result
    except Exception:
        return str(result)[:200]


def inject_contracts(module):
    """
    Scan a module's functions and wrap those with saved K9Contracts.
    Called after module import completes.
    """
    import inspect
    injected = 0
    for name, obj in list(vars(module).items()):
        if not inspect.isfunction(obj):
            continue
        if name.startswith("_"):
            continue
        y_star_t = _load_contract(name)
        if y_star_t is None:
            continue
        wrapped = _make_wrapper(obj, y_star_t, name)
        setattr(module, name, wrapped)
        injected += 1
    if injected > 0:
        sys.stderr.write(
            f"[k9log] AutoContract: {injected} function(s) monitored "
            f"in {getattr(module, '__name__', '?')}\n"
        )
    return injected


class K9ContractLoader(importlib.abc.Loader):
    """Wraps an existing loader, injecting contracts after exec."""

    def __init__(self, original_loader, module_name):
        self._original = original_loader
        self._module_name = module_name

    def create_module(self, spec):
        if hasattr(self._original, "create_module"):
            return self._original.create_module(spec)
        return None

    def exec_module(self, module):
        self._original.exec_module(module)
        # After module is fully loaded, inject contracts
        try:
            inject_contracts(module)
        except Exception:
            pass


class K9ContractFinder(importlib.abc.MetaPathFinder):
    """
    sys.meta_path finder that intercepts module imports and
    wraps functions that have saved K9Contracts.
    Only intercepts modules that are NOT k9log itself.
    """

    def find_spec(self, fullname, path, target=None):
        # Never intercept k9log internals
        if fullname.startswith("k9log"):
            return None
        # Only intercept if contracts exist for this module
        # (optimization: check config dir for any matching contracts)
        config_dir = Path.home() / ".k9log" / "config"
        if not config_dir.exists():
            return None

        # Find the original spec without our finder
        original_finders = [
            f for f in sys.meta_path
            if not isinstance(f, K9ContractFinder)
        ]
        spec = None
        for finder in original_finders:
            try:
                spec = finder.find_spec(fullname, path, target)
                if spec is not None:
                    break
            except Exception:
                continue

        if spec is None or spec.loader is None:
            return None

        # Wrap the loader
        spec.loader = K9ContractLoader(spec.loader, fullname)
        return spec


# Install the finder once when this module is imported
_finder = K9ContractFinder()
if not any(isinstance(f, K9ContractFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _finder)
    sys.stderr.write("[k9log] AutoContract: contract injection active\n")
