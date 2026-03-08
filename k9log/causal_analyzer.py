# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
# AGPL-3.0
"""
K9log Causal Analyzer - L1 Causal Chain Analysis
"""
import re
import json
from pathlib import Path
from collections import defaultdict
from rich.console import Console
from rich.tree import Tree

console = Console()

class CausalChainAnalyzer:
    """
    L1 Causal Chain Analyzer

    Analyzes CIEU logs to build causal chains and identify root causes.
    PreToolUse records are merged with OUTCOME records using tool_use_id.
    """

    def __init__(self, log_file=None):
        if log_file is None:
            log_file = Path.home() / '.k9log' / 'logs' / 'k9log.cieu.jsonl'
        self.log_file = Path(log_file)
        self.records = []
        self.causal_graph = None
        self._load_records()

    def _load_records(self):
        if not self.log_file.exists():
            return
        raw = []
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        raw.append(json.loads(line))
                    except Exception:
                        continue
        tool_use_index = {}
        for record in raw:
            event_type = record.get('event_type', '')
            if event_type in ('SESSION_END',):
                continue
            if event_type == 'OUTCOME':
                tid = (record.get('X_t') or {}).get('tool_use_id', '')
                if tid and tid in tool_use_index:
                    idx = tool_use_index[tid]
                    pre = self.records[idx]
                    pre['Y_t+1'] = record['Y_t+1']
                    if not record['R_t+1']['passed']:
                        pre['R_t+1']['passed'] = False
                        pre['R_t+1']['execution_error'] = (
                            record['Y_t+1'].get('error') or
                            record['Y_t+1'].get('stderr', '')
                        )[:200]
                        pre['_has_execution_failure'] = True
            else:
                tid = (record.get('X_t') or {}).get('tool_use_id', '')
                if tid:
                    tool_use_index[tid] = len(self.records)
                self.records.append(record)

    def build_causal_dag(self):
        nodes = []
        edges = []
        for idx, record in enumerate(self.records):
            node = {
                'id': idx,
                'step': idx,
                'skill': record.get('U_t', {}).get('skill', 'unknown'),
                'agent_id': record.get('X_t', {}).get('agent_id', 'unknown'),
                'timestamp': record.get('timestamp', 'N/A'),
                'passed': record.get('R_t+1', {}).get('passed', True),
                'violations': record.get('R_t+1', {}).get('violations', []),
                'params': record.get('U_t', {}).get('params', {}),
                'result': record.get('Y_t+1', {}).get('result'),
                'has_execution_failure': record.get('_has_execution_failure', False),
                'execution_error': record.get('R_t+1', {}).get('execution_error', ''),
                'stdout': record.get('Y_t+1', {}).get('stdout', ''),
                'stderr': record.get('Y_t+1', {}).get('stderr', ''),
            }
            nodes.append(node)
        for idx in range(len(self.records)):
            if idx > 0:
                edges.append({'from': idx-1, 'to': idx, 'type': 'temporal', 'weight': 1.0})
            edges.extend(self._find_data_dependencies(idx, nodes))
        self.causal_graph = {
            'nodes': nodes, 'edges': edges,
            'metadata': {
                'total_nodes': len(nodes),
                'total_edges': len(edges),
                'violations': sum(1 for n in nodes if not n['passed']),
                'execution_failures': sum(1 for n in nodes if n['has_execution_failure']),
            }
        }
        return self.causal_graph

    def _find_data_dependencies(self, current_idx, nodes):
        edges = []
        if current_idx == 0:
            return edges
        current_params = nodes[current_idx]['params']
        for prev_idx in range(max(0, current_idx - 10), current_idx):
            prev_result = nodes[prev_idx]['result']
            if prev_result and isinstance(prev_result, dict):
                prev_result_str = json.dumps(prev_result)
                for param_key, param_value in current_params.items():
                    if param_value is None:
                        continue
                    pv_str = str(param_value)
                    if len(pv_str) < 4:
                        continue
                    matched = any(param_value == rv for rv in prev_result.values())
                    if not matched and len(pv_str) >= 8:
                        matched = pv_str in prev_result_str
                    if matched:
                        edges.append({'from': prev_idx, 'to': current_idx,
                                      'type': 'data_flow', 'field': param_key, 'weight': 2.0})
                        break
        return edges

    def find_root_causes(self, incident_step):
        if not self.causal_graph:
            self.build_causal_dag()
        nodes = self.causal_graph['nodes']
        edges = self.causal_graph['edges']
        if incident_step >= len(nodes):
            return None
        visited = set()
        causal_chain = []
        def trace_back(step_id, depth=0, path=None):
            if path is None:
                path = []
            if step_id in visited or depth > 10:
                return
            visited.add(step_id)
            node = nodes[step_id]
            causal_chain.append({
                'step': step_id, 'depth': depth,
                'skill': node['skill'], 'passed': node['passed'],
                'violations': node['violations'],
                'has_execution_failure': node['has_execution_failure'],
                'execution_error': node['execution_error'],
                'path': path + [step_id]
            })
            incoming = sorted([e for e in edges if e['to'] == step_id],
                              key=lambda e: -e['weight'])
            for edge in incoming:
                trace_back(edge['from'], depth+1, path+[step_id])
        trace_back(incident_step)
        root_causes = self._identify_root_causes(causal_chain, incident_step)
        chain_depth = max((n['depth'] for n in causal_chain), default=0)
        return {
            'incident_step': incident_step,
            'causal_chain': causal_chain,
            'chain_depth': chain_depth,
            'root_causes': root_causes,
            'chain_length': len(causal_chain)
        }

    def _identify_root_causes(self, causal_chain, incident_step):
        root_causes = []

        # Strategy 1: Earliest failure in chain
        failures_in_chain = [
            c for c in causal_chain
            if (not c['passed'] or c['has_execution_failure'])
            and c['step'] != incident_step
        ]
        if failures_in_chain:
            earliest = min(failures_in_chain, key=lambda c: c['step'])
            label = 'execution_error' if earliest['has_execution_failure'] else 'constraint_violation'
            root_causes.append({
                'type': label, 'step': earliest['step'], 'skill': earliest['skill'],
                'violations': earliest['violations'],
                'execution_error': earliest['execution_error'],
                'file_path': '', 'keyword': '',
                'confidence': 0.9, 'reasoning': 'First failure in causal chain'
            })

        # Strategy 2: High-severity constraint violations
        high_severity = [
            c for c in failures_in_chain
            if any(v.get('severity', 0) >= 0.7 for v in c['violations'])
        ]
        for hv in high_severity[:3]:
            if hv['step'] not in [rc['step'] for rc in root_causes]:
                root_causes.append({
                    'type': 'high_severity_violation', 'step': hv['step'],
                    'skill': hv['skill'], 'violations': hv['violations'],
                    'execution_error': '', 'file_path': '', 'keyword': '',
                    'confidence': 0.8, 'reasoning': 'High severity violation in chain'
                })

        # Strategy 3: Error keyword backtracking
        # Extract symbol name from NameError/ImportError/AttributeError,
        # find Write steps whose content uses the symbol but never defines it.
        incident_node = next((c for c in causal_chain if c['step'] == incident_step), None)
        if incident_node and incident_node['execution_error']:
            err = incident_node['execution_error']
            # Try double-quote variant first, then single-quote
            name_match = re.search(
                r'(?:name "([^"]+)" is not defined'
                r'|cannot import name "([^"]+)"'
                r'|No module named "([^"]+)"'
                r'|has no attribute "([^"]+)")',
                err
            )
            if not name_match:
                name_match = re.search(
                    r"(?:name '([^']+)' is not defined"
                    r"|cannot import name '([^']+)'"
                    r"|No module named '([^']+)'"
                    r"|has no attribute '([^']+)')",
                    err
                )
            if name_match:
                keyword = next((g for g in name_match.groups() if g), None)
                if keyword:
                    write_skills = {'Write', 'Edit', 'str_replace_based_edit_tool',
                                    'create_file', 'MultiEdit'}
                    for c in causal_chain:
                        if c['step'] == incident_step:
                            continue
                        if c['step'] in [rc['step'] for rc in root_causes]:
                            continue
                        orig = self.records[c['step']] if c['step'] < len(self.records) else {}
                        skill = (orig.get('U_t') or {}).get('skill', '')
                        if skill not in write_skills:
                            continue
                        params = (orig.get('U_t') or {}).get('params', {})
                        content = str(
                            params.get('content', '') or
                            params.get('new_str', '') or
                            params.get('new_content', '') or ''
                        )
                        if keyword not in content:
                            continue
                        missing = (
                            ('import ' + keyword) not in content and
                            ('from ' + keyword) not in content and
                            ('def ' + keyword) not in content and
                            (keyword + ' =') not in content and
                            (keyword + '=') not in content
                        )
                        if missing:
                            file_path = params.get('file_path',
                                        params.get('path', 'unknown'))
                            root_causes.append({
                                'type': 'missing_definition',
                                'step': c['step'],
                                'skill': skill,
                                'violations': [],
                                'execution_error': '',
                                'file_path': file_path,
                                'keyword': keyword,
                                'confidence': 0.85,
                                'reasoning': (
                                    'Written content uses "' + keyword + '" but '
                                    'missing import/definition. '
                                    'Error propagated to Step #' + str(incident_step) + '.'
                                )
                            })

        # Strategy 4: Chain origin (no failures found)
        if not root_causes and causal_chain:
            origin = max(causal_chain, key=lambda c: c['depth'])
            root_causes.append({
                'type': 'chain_origin', 'step': origin['step'],
                'skill': origin['skill'], 'violations': [],
                'execution_error': '', 'file_path': '', 'keyword': '',
                'confidence': 0.5,
                'reasoning': 'Origin of causal chain (no failures detected)'
            })

        root_causes.sort(key=lambda rc: -rc['confidence'])
        return root_causes

    def visualize_causal_chain(self, incident_step):
        analysis = self.find_root_causes(incident_step)
        if not analysis:
            console.print('[yellow]No causal chain found[/yellow]')
            return
        tree = Tree(
            '[bold cyan]Causal Chain Analysis[/bold cyan]\n'
            'Incident: Step #' + str(incident_step)
        )
        rc_branch = tree.add('[bold red]Root Causes[/bold red]')
        for rc in analysis['root_causes']:
            color = 'green' if rc['confidence'] > 0.8 else 'yellow'
            label = rc['skill']
            if rc.get('file_path'):
                label += ' (' + rc['file_path'] + ')'
            rc_node = rc_branch.add(
                '[' + color + ']Step #' + str(rc['step']) + '[/' + color + '] - ' +
                label + ' (confidence: ' + str(int(rc['confidence']*100)) + '%)'
            )
            rc_node.add('[dim]' + rc['reasoning'] + '[/dim]')
            if rc.get('keyword'):
                rc_node.add('[red]Missing: import ' + rc['keyword'] + '[/red]')
            if rc['violations']:
                viol_str = ', '.join([v.get('message', '?') for v in rc['violations'][:2]])
                rc_node.add('[red]Violations: ' + viol_str + '[/red]')
            if rc['execution_error']:
                rc_node.add('[red]Error: ' + rc['execution_error'][:120] + '[/red]')
        chain_branch = tree.add('[bold blue]Full Causal Chain[/bold blue]')
        by_depth = defaultdict(list)
        for c in analysis['causal_chain']:
            by_depth[c['depth']].append(c)
        for depth in sorted(by_depth.keys()):
            depth_node = chain_branch.add('[dim]Depth ' + str(depth) + '[/dim]')
            for c in sorted(by_depth[depth], key=lambda x: x['step']):
                if c['has_execution_failure']:
                    status = '[red]EXEC_FAIL[/red]'
                elif not c['passed']:
                    status = '[red]VIOLATION[/red]'
                else:
                    status = '[green]OK[/green]'
                depth_node.add(status + ' Step #' + str(c['step']) + ' - ' + c['skill'])
        console.print()
        console.print(tree)
        console.print(
            '[cyan]Chain length: ' + str(analysis['chain_length']) +
            ' steps | Depth: ' + str(analysis['chain_depth']) + '[/cyan]'
        )

    def export_dag(self, output_file='causal_dag.json'):
        if not self.causal_graph:
            self.build_causal_dag()
        with open(output_file, 'w') as f:
            json.dump(self.causal_graph, f, indent=2)
        console.print('[green]Causal DAG exported to ' + output_file + '[/green]')


def analyze_causal_chain(incident_step, log_file=None):
    """Convenience function for causal chain analysis"""
    analyzer = CausalChainAnalyzer(log_file)
    analyzer.visualize_causal_chain(incident_step)
    return analyzer.find_root_causes(incident_step)
