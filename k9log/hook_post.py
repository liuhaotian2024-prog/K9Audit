# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
# AGPL-3.0
"""
K9log Hook Post - Claude Code PostToolUse integration
Registered via .claude/settings.json:
  hooks.PostToolUse -> python -m k9log.hook_post

Reads tool result from stdin:
  1. Calls logger.update_outcome() to record execution result
  2. If a .py file was written, parses K9Contract docstrings
     and saves contracts to ~/.k9log/config/{function_name}.json
     so load_constraints() can auto-load them on next @k9 call.

Always exits 0 - never blocks Claude Code.
"""
import sys, json, time
from pathlib import Path


def _extract_contracts_from_file(file_path):
    """
    Parse a Python file, extract K9Contract blocks from all functions,
    then apply K9 Law inference to fill gaps the agent left empty.
    Returns dict: {function_name: {postcondition: [...], invariant: [...]}}
    """
    try:
        import ast
        from k9log.constraints import parse_k9contract, _infer_contracts_from_ast, _merge_contracts
        source = Path(file_path).read_text(encoding='utf-8')
        tree = ast.parse(source)
        contracts = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # Step 1: parse agent-written K9Contract
            docstring = ast.get_docstring(node)
            parsed = parse_k9contract(docstring) if docstring else {}
            # Step 2: infer missing contracts from AST (K9 Law)
            inferred = _infer_contracts_from_ast(source, node)
            # Step 3: merge — agent contract takes priority, K9 Law fills gaps
            merged = _merge_contracts(parsed, inferred)
            if merged:
                # Log what was inferred vs written
                if merged.get('_inferred'):
                    sys.stderr.write(
                        f'[k9log] K9Law inferred for {node.name}: {merged["_inferred"]}\n'
                    )
                contracts[node.name] = merged
        return contracts
    except Exception:
        return {}


def _save_contracts(contracts, file_path):
    """
    Save parsed contracts to ~/.k9log/config/{function_name}.json
    so load_constraints() can find them automatically.
    """
    if not contracts:
        return 0
    config_dir = Path.home() / '.k9log' / 'config'
    config_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for func_name, contract in contracts.items():
        config_file = config_dir / f'{func_name}.json'
        # Merge with existing constraints if present
        existing = {}
        if config_file.exists():
            try:
                existing = json.loads(config_file.read_text(encoding='utf-8'))
            except Exception:
                existing = {}
        existing_constraints = existing.get('constraints', {})
        # K9Contract keys override existing postcondition/invariant
        existing_constraints.update(contract)
        config_out = {
            'skill': func_name,
            'constraints': existing_constraints,
            'version': '1.0.0',
            '_source': str(file_path),
            '_parsed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }
        config_file.write_text(
            json.dumps(config_out, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        saved += 1
    return saved


def _process_py_file_write(payload):
    """
    If this PostToolUse is a Write/Edit of a .py file,
    extract K9Contract blocks and save to config dir.
    """
    try:
        tool_name = payload.get('tool_name', '')
        write_tools = {'Write', 'Edit', 'str_replace_based_edit_tool',
                       'create_file', 'MultiEdit'}
        if tool_name not in write_tools:
            return
        # Get file path from tool input
        tool_input = payload.get("tool_input", {})
        ut = last.get("U_t", {})
        skill = ut.get("skill", payload.get("tool_name", "unknown"))
        file_path = (
            tool_input.get('file_path') or
            tool_input.get('path') or ''
        )
        if not file_path.endswith('.py'):
            return
        if not Path(file_path).exists():
            return
        contracts = _extract_contracts_from_file(file_path)
        if contracts:
            saved = _save_contracts(contracts, file_path)
            if saved > 0:
                sys.stderr.write(
                    f'[k9log] K9Contract: {saved} contract(s) saved from {file_path}\n'
                )
        _suggest_magic_constraints(file_path)
    except Exception as e:
        sys.stderr.write(f'[k9log] K9Contract parse failed: {e}\n')



def _broadcast_root_cause(is_error: bool, payload: dict):
    """
    If execution failed, find the cross-step root cause and write to stderr.
    Claude Code reads stderr and jumps back to fix the actual root cause —
    not the symptom step where the crash happened.

    Only fires when:
      - is_error=True (tool execution actually failed)
      - CausalChainAnalyzer finds a root cause at a DIFFERENT step than the crash
        (same-step errors are self-evident — Claude Code can see them directly)
    """
    if not is_error:
        return
    try:
        from k9log.causal_analyzer import CausalChainAnalyzer
        analyzer = CausalChainAnalyzer()
        if not analyzer.records:
            return

        # Find the most recent failure step
        incident_step = None
        for idx in range(len(analyzer.records) - 1, -1, -1):
            rec = analyzer.records[idx]
            if not rec.get('R_t+1', {}).get('passed', True):
                incident_step = idx
                break
        if incident_step is None:
            return

        analyzer.build_causal_dag()
        result = analyzer.find_root_causes(incident_step)
        if not result or not result.get('root_causes'):
            return

        root_causes = result['root_causes']
        top = root_causes[0]

        # Only broadcast if root cause is at a DIFFERENT step (cross-step)
        # Same-step errors are self-evident — no need to broadcast
        if top.get('step') == incident_step:
            return

        # Build the broadcast message for Claude Code
        tool_name = payload.get('tool_name', 'unknown')
        lines = [
            f"\n[K9 Root Cause] Execution failed at step #{incident_step} ({tool_name})",
            f"  but the ROOT CAUSE is at step #{top['step']} — {top['skill']}",
            f"  Confidence: {int(top['confidence'] * 100)}%",
            f"  Reason: {top['reasoning']}",
        ]
        if top.get('keyword'):
            lines.append(f"  Missing: import {top['keyword']}")
        if top.get('execution_error'):
            lines.append(f"  Error trace: {top['execution_error'][:120]}")
        if top.get('file_path'):
            lines.append(f"  File: {top['file_path']}")
        if len(root_causes) > 1:
            lines.append(f"  Other candidates: " +
                ", ".join(f"step#{r['step']}" for r in root_causes[1:3]))
        lines.append(f"  → Fix step #{top['step']} first, then re-run.")
        lines.append(f"  → Full trace: k9log causal --last\n")

        sys.stderr.write("\n".join(lines) + "\n")

    except Exception:
        pass  # causal broadcast must never affect hook execution


def _print_human_summary(payload: dict, is_error: bool):
    """用人话打印审计摘要，只在发现问题时打印。"""
    try:
        import json as _json
        from pathlib import Path as _Path
        log_file = _Path.home() / ".k9log" / "logs" / "k9log.cieu.jsonl"
        if not log_file.exists():
            return
        records = []
        with open(log_file, encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line:
                    try:
                        records.append(_json.loads(_line))
                    except Exception:
                        pass
        if not records:
            return
        last = None
        for r in reversed(records):
            if not r.get("R_t+1", {}).get("passed", True):
                last = r
                break
        if not last:
            return
        assessment = last.get("R_t+1", {})
        violations = assessment.get("violations", [])
        if not violations:
            return
        top = violations[0]
        severity = assessment.get("overall_severity", 0)
        matched = top.get("matched", "")
        vtype = top.get("type", "")
        tool_input = payload.get("tool_input", {})
        file_path = (tool_input.get("file_path") or tool_input.get("path") or "unknown")
        tool_name = payload.get("tool_name", "")
        tool_desc = {"Write": "wrote a file", "Edit": "edited a file",
                     "Bash": "ran a command", "Read": "read a file",
                     "create_file": "created a file"}.get(tool_name, f"used {tool_name}")
        if "STAGING" in vtype or (matched and "staging" in matched.lower()):
            problem = "wrote a staging/test server URL — this should never appear in production"
        elif "DENY_CONTENT" in vtype:
            problem = f"wrote forbidden content: \"{matched}\""
        elif "PATH" in vtype or "SCOPE" in vtype:
            problem = "wrote outside the allowed file paths"
        elif "SECRET" in vtype:
            problem = "may have written a hardcoded secret or API key"
        else:
            problem = top.get("message", "violated a constraint")
        badge = "🚨 CRITICAL" if severity >= 0.9 else "⚠️  WARNING" if severity >= 0.7 else "ℹ️  NOTICE"

        # 从 ledger 读取上下文
        xt = last.get("X_t", {})
        session_id = str(xt.get("session_id", "unknown"))[:8]
        agent = xt.get("agent_name", "Claude Code")

        # Y*_t 意图合约
        ystar = last.get("Y_star_t", {})
        deny = ystar.get("constraints", {}).get("deny_content", [])
        allowed = ystar.get("constraints", {}).get("allowed_paths", [])
        if deny:
            intended_desc = "deny: " + ", ".join(str(d) for d in deny[:2])
        elif allowed:
            intended_desc = "only write to: " + ", ".join(allowed[:2])
        else:
            intended_desc = "no violations expected"

        # 实际内容
        ut = last.get("U_t", {})
        params = ut.get("params", {})
        actual = matched or params.get("content", params.get("command", str(params)))[:80]

        sys.stderr.write(f"\n[K9 Audit] {badge}\n")
        sys.stderr.write(f"  WHO:       {agent} (session: {session_id}) → {tool_name}\n")
        sys.stderr.write(f"  CONTEXT:   Wrote to: {file_path}\n")
        sys.stderr.write(f"  INTENDED:  {intended_desc}\n")
        sys.stderr.write(f"  ACTUAL:    \"{actual}\"\n")
        sys.stderr.write(f"  DEVIATION: {severity:.2f} — {problem}\n")
        sys.stderr.write(f"  ACTION:    Recorded in tamper-proof ledger · seq #{last.get('_integrity', {}).get('seq', '?')}\n")
        sys.stderr.write(f"             → k9log trace --last\n\n")
    except Exception as _e:
        sys.stderr.write(f"[k9log] summary error: {_e}\n")

def main():
    t0 = time.time()
    try:
        payload = json.loads(sys.stdin.read() or '{}')
    except Exception:
        payload = {}

    tool_use_id = payload.get('tool_use_id', '')
    if not tool_use_id:
        sys.exit(0)

    # Extract outcome from PostToolUse payload
    tool_response = payload.get('tool_response', {})
    output        = tool_response.get('output', '')
    is_error      = tool_response.get('is_error', False)

    outcome = {
        'exit_code':    1 if is_error else 0,
        'stdout':       output if not is_error else '',
        'stderr':       '',
        'error':        output if is_error else '',
        'duration_sec': time.time() - t0,
    }

    # 1. Record execution outcome in CIEU ledger
    try:
        from k9log.logger import get_logger
        get_logger().update_outcome(tool_use_id, outcome)
    except Exception as e:
        sys.stderr.write(f'[k9log] PostToolUse outcome write failed: {e}\n')

    # 2. If a .py file was written, extract and save K9Contract blocks
    _process_py_file_write(payload)

    # 用人话打印审计摘要
    _print_human_summary(payload, is_error)

    # 根因广播
    _broadcast_root_cause(is_error, payload)

    sys.exit(0)


if __name__ == '__main__':
    main()
