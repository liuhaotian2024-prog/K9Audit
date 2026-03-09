# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
# AGPL-3.0
"""
K9log OpenClaw Adapter

Wraps an entire OpenClaw skill module with @k9 audit in one call:

    from k9log.openclaw import k9_wrap_module
    import my_skills

    k9_wrap_module(my_skills)
    # every public function in my_skills is now audited

Or wrap with shared constraints applied to all skills:

    k9_wrap_module(my_skills, deny_content=['staging.internal'])

Or wrap selectively:

    k9_wrap_module(my_skills, only=['transfer', 'send_email'])
    k9_wrap_module(my_skills, exclude=['debug_helper'])
"""
import inspect
import logging
from types import ModuleType
from typing import List, Optional

from k9log.core import k9

_log = logging.getLogger("k9log")


def k9_wrap_module(
    module: ModuleType,
    only: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    **shared_constraints,
) -> ModuleType:
    """
    Wrap every public function in a module with @k9.

    Args:
        module:             The skill module to wrap.
        only:               If given, only wrap these function names.
        exclude:            Function names to skip.
        **shared_constraints: Constraints applied to all wrapped functions
                            (e.g. deny_content=['secret']).
                            Per-skill intent contract files take precedence.

    Returns:
        The same module object, with functions replaced in-place.
    """
    if not isinstance(module, ModuleType):
        raise TypeError(f"k9_wrap_module: expected a module, got {type(module).__name__}")

    exclude_set = set(exclude or [])
    only_set = set(only or [])
    wrapped = []
    skipped = []

    for name, obj in list(vars(module).items()):
        # Skip non-functions, private/dunder, and already-wrapped
        if not inspect.isfunction(obj):
            continue
        if name.startswith("_"):
            continue
        if only_set and name not in only_set:
            skipped.append(name)
            continue
        if name in exclude_set:
            skipped.append(name)
            continue
        # Skip functions defined outside this module (imports)
        if getattr(obj, '__module__', None) != module.__name__:
            skipped.append(name)
            continue

        wrapped_fn = k9(**shared_constraints)(obj) if shared_constraints else k9(obj)
        wrapped_fn = _add_outcome_tracking(wrapped_fn, name)
        setattr(module, name, wrapped_fn)
        wrapped.append(name)

    _log.info(
        "k9log: k9_wrap_module(%s) wrapped=%s skipped=%s",
        module.__name__, wrapped, skipped
    )
    return module


def k9_wrap_class(
    cls,
    only: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    **shared_constraints,
):
    """
    Wrap every public method in a class with @k9.
    Useful for OpenClaw skill classes.

        from k9log.openclaw import k9_wrap_class
        k9_wrap_class(MySkillClass)
    """
    exclude_set = set(exclude or [])
    only_set = set(only or [])
    wrapped = []

    for name, obj in inspect.getmembers(cls, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        if only_set and name not in only_set:
            continue
        if name in exclude_set:
            continue
        wrapped_fn = k9(**shared_constraints)(obj) if shared_constraints else k9(obj)
        wrapped_fn = _add_outcome_tracking(wrapped_fn, name)
        setattr(cls, name, wrapped_fn)
        wrapped.append(name)

    _log.info(
        "k9log: k9_wrap_class(%s) wrapped=%s",
        cls.__name__, wrapped
    )
    return cls


def _add_outcome_tracking(func, func_name):
    """Add update_outcome() call after @k9 wrapper for causal chain support."""
    import functools, time, uuid as _uuid

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        tool_use_id = str(_uuid.uuid4())
        t0 = time.time()
        error = None
        result = None
        try:
            result = func(*args, **kwargs)
        except Exception as e:
            error = e
        finally:
            try:
                from k9log.logger import get_logger
                outcome = {
                    "exit_code":    1 if error else 0,
                    "stdout":       str(result)[:500] if result is not None else "",
                    "stderr":       str(error) if error else "",
                    "error":        str(error) if error else "",
                    "duration_sec": time.time() - t0,
                }
                get_logger().update_outcome(tool_use_id, outcome)
            except Exception:
                pass
        if error:
            raise error
        return result

    return wrapper
