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
K9log Causal Analyzer - L1 Causal Chain Analysis
"""
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
    This is NOT statistical causal inference - it's engineering-grade
    responsibility chain reconstruction.
    """
    
    def __init__(self, log_file=None):
        if log_file is None:
            log_file = Path.home() / '.k9log' / 'logs' / 'k9log.cieu.jsonl'
        
        self.log_file = Path(log_file)
        self.records = []
        self.causal_graph = None
        self._load_records()
    
    def _load_records(self):
        """Load all records from log file"""
        if not self.log_file.exists():
            return
        
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    if record.get('event_type') != 'SESSION_END':
                        self.records.append(record)
    
    def build_causal_dag(self):
        """
        Build Causal Directed Acyclic Graph (DAG)
        
        Nodes: Events (steps)
        Edges: Causal relationships
        
        Edge types:
        - temporal: Sequential execution (step N -> step N+1)
        - data_flow: Output of step N used as input in step M
        - session: Same session/agent
        """
        nodes = []
        edges = []
        
        # Build nodes
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
                'result': record.get('Y_t+1', {}).get('result')
            }
            nodes.append(node)
        
        # Build edges
        for idx in range(len(self.records)):
            # Temporal edges (sequential)
            if idx > 0:
                edges.append({
                    'from': idx - 1,
                    'to': idx,
                    'type': 'temporal',
                    'weight': 1.0
                })
            
            # Data flow edges (parameter dependency)
            data_edges = self._find_data_dependencies(idx, nodes)
            edges.extend(data_edges)
        
        self.causal_graph = {
            'nodes': nodes,
            'edges': edges,
            'metadata': {
                'total_nodes': len(nodes),
                'total_edges': len(edges),
                'violations': sum(1 for n in nodes if not n['passed'])
            }
        }
        
        return self.causal_graph
    
    def _find_data_dependencies(self, current_idx, nodes):
        """
        Find data flow dependencies between steps
        
        A parameter in step N is dependent on step M if:
        - Step M's result contains a field used in step N's params
        """
        edges = []
        
        if current_idx == 0:
            return edges
        
        current_params = nodes[current_idx]['params']
        
        # Look back at previous steps
        for prev_idx in range(max(0, current_idx - 10), current_idx):
            prev_result = nodes[prev_idx]['result']
            
            if prev_result and isinstance(prev_result, dict):
                # Check if any current param values appear in previous results
                # Use substring matching: param value contained in result value
                prev_result_str = json.dumps(prev_result)
                for param_key, param_value in current_params.items():
                    if param_value is None:
                        continue
                    pv_str = str(param_value)
                    if len(pv_str) < 4:
                        continue  # too short to be meaningful
                    # Exact field match or substring match
                    matched = any(param_value == rv for rv in prev_result.values())
                    if not matched and len(pv_str) >= 8:
                        matched = pv_str in prev_result_str
                    if matched:
                        edges.append({
                            'from': prev_idx,
                            'to': current_idx,
                            'type': 'data_flow',
                            'field': param_key,
                            'weight': 2.0
                        })
                        break  # one data_flow edge per (prev, current) pair is enough
        
        return edges
    
    def find_root_causes(self, incident_step):
        """
        Find root causes of an incident using causal chain analysis
        
        Strategy:
        1. Start from incident step
        2. Trace backwards through causal edges
        3. Identify earliest violation or triggering event
        4. Rank by causal distance and violation severity
        """
        if not self.causal_graph:
            self.build_causal_dag()
        
        nodes = self.causal_graph['nodes']
        edges = self.causal_graph['edges']
        
        if incident_step >= len(nodes):
            return None
        
        # Backward traversal to find causes
        visited = set()
        causal_chain = []
        
        def trace_back(step_id, depth=0, path=None):
            if path is None:
                path = []
            
            if step_id in visited or depth > 10:
                return
            
            visited.add(step_id)
            node = nodes[step_id]
            
            # Record this step in chain
            causal_chain.append({
                'step': step_id,
                'depth': depth,
                'skill': node['skill'],
                'passed': node['passed'],
                'violations': node['violations'],
                'path': path + [step_id]
            })
            
            # Find incoming edges
            incoming = [e for e in edges if e['to'] == step_id]
            
            # Prioritize data_flow edges
            incoming.sort(key=lambda e: -e['weight'])
            
            for edge in incoming:
                trace_back(edge['from'], depth + 1, path + [step_id])
        
        trace_back(incident_step)
        
        # Analyze chain to find root causes
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
        """
        Identify root causes from causal chain
        
        Root cause candidates:
        1. Earliest violation in the chain
        2. Steps with high-severity violations
        3. Data flow source nodes
        """
        root_causes = []
        
        # Find all violations in chain
        violations_in_chain = [
            c for c in causal_chain 
            if not c['passed'] and c['step'] != incident_step
        ]
        
        # Strategy 1: Earliest violation
        if violations_in_chain:
            earliest_violation = min(violations_in_chain, key=lambda c: c['step'])
            root_causes.append({
                'type': 'earliest_violation',
                'step': earliest_violation['step'],
                'skill': earliest_violation['skill'],
                'violations': earliest_violation['violations'],
                'confidence': 0.9,
                'reasoning': 'First violation in causal chain'
            })
        
        # Strategy 2: High-severity violations
        high_severity = [
            c for c in violations_in_chain
            if any(v.get('severity', 0) >= 0.7 for v in c['violations'])
        ]
        
        for hv in high_severity[:3]:  # Top 3
            if hv['step'] not in [rc['step'] for rc in root_causes]:
                root_causes.append({
                    'type': 'high_severity',
                    'step': hv['step'],
                    'skill': hv['skill'],
                    'violations': hv['violations'],
                    'confidence': 0.8,
                    'reasoning': 'High severity violation in chain'
                })
        
        # Strategy 3: Chain origin (if no violations found)
        if not root_causes and causal_chain:
            origin = max(causal_chain, key=lambda c: c['depth'])
            root_causes.append({
                'type': 'chain_origin',
                'step': origin['step'],
                'skill': origin['skill'],
                'violations': [],
                'confidence': 0.5,
                'reasoning': 'Origin of causal chain (no violations detected)'
            })
        
        # Sort by confidence
        root_causes.sort(key=lambda rc: -rc['confidence'])
        
        return root_causes
    
    def visualize_causal_chain(self, incident_step):
        """
        Visualize causal chain as a tree
        """
        analysis = self.find_root_causes(incident_step)
        
        if not analysis:
            console.print("[yellow]No causal chain found[/yellow]")
            return
        
        tree = Tree(
            f"[bold cyan]🔍 Causal Chain Analysis[/bold cyan]\n"
            f"Incident: Step #{incident_step}"
        )
        
        # Root causes
        rc_branch = tree.add("[bold red]🎯 Root Causes[/bold red]")
        for rc in analysis['root_causes']:
            confidence_color = "green" if rc['confidence'] > 0.8 else "yellow"
            rc_node = rc_branch.add(
                f"[{confidence_color}]Step #{rc['step']}[/{confidence_color}] - "
                f"{rc['skill']} "
                f"(confidence: {rc['confidence']:.0%})"
            )
            rc_node.add(f"[dim]{rc['reasoning']}[/dim]")
            
            if rc['violations']:
                viol_str = ', '.join([v.get('message', 'Unknown') for v in rc['violations'][:2]])
                rc_node.add(f"[red]Violations: {viol_str}[/red]")
        
        # Full chain
        chain_branch = tree.add("[bold blue]🔗 Full Causal Chain[/bold blue]")
        
        # Group by depth
        by_depth = defaultdict(list)
        for c in analysis['causal_chain']:
            by_depth[c['depth']].append(c)
        
        for depth in sorted(by_depth.keys()):
            depth_node = chain_branch.add(f"[dim]Depth {depth}[/dim]")
            for c in sorted(by_depth[depth], key=lambda x: x['step']):
                status = "✅" if c['passed'] else "❌"
                depth_node.add(f"{status} Step #{c['step']} - {c['skill']}")
        
        console.print("\n")
        console.print(tree)
        console.print(f"\n[cyan]Chain length: {analysis['chain_length']} steps[/cyan]")
    
    def export_dag(self, output_file='causal_dag.json'):
        """Export causal DAG to JSON"""
        if not self.causal_graph:
            self.build_causal_dag()
        
        with open(output_file, 'w') as f:
            json.dump(self.causal_graph, f, indent=2)
        
        console.print(f"[green]✅ Causal DAG exported to {output_file}[/green]")

def analyze_causal_chain(incident_step, log_file=None):
    """Convenience function for causal chain analysis"""
    analyzer = CausalChainAnalyzer(log_file)
    analyzer.visualize_causal_chain(incident_step)
    return analyzer.find_root_causes(incident_step)

