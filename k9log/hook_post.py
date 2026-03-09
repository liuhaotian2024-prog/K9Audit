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
        tool_input = payload.get('tool_input', {})
        file_path = (
            tool_input.get('file_path') or
            tool_input.get('path') or ''
        )
        if not file_path.endswith('.py'):
            return
        if not Path(file_path).exists():
            return
        contracts = _extract_contracts_from_file(file_path)
        if not contracts:
            return
        saved = _save_contracts(contracts, file_path)
        if saved > 0:
            sys.stderr.write(
                f'[k9log] K9Contract: {saved} contract(s) saved from {file_path}\n'
            )
    except Exception as e:
        sys.stderr.write(f'[k9log] K9Contract parse failed: {e}\n')


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

    sys.exit(0)


if __name__ == '__main__':
    main()
