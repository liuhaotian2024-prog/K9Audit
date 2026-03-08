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
K9log Tracer - Incident tracing and root cause analysis
"""
import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

class IncidentTracer:
    """Trace incidents from CIEU logs"""
    
    def __init__(self, log_file=None):
        if log_file is None:
            log_file = Path.home() / '.k9log' / 'logs' / 'k9log.cieu.jsonl'
        
        self.log_file = Path(log_file)
        self.records = []
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
    
    def trace_step(self, step_number):
        """Trace a specific step"""
        if step_number >= len(self.records):
            console.print(f"[red]Step {step_number} not found[/red]")
            return
        
        record = self.records[step_number]
        
        # Build context (3 steps before and after)
        context_start = max(0, step_number - 3)
        context_end = min(len(self.records), step_number + 4)
        context = self.records[context_start:context_end]
        
        self._display_trace(step_number, record, context, context_start)
    
    def trace_last_violation(self):
        """Trace the most recent violation"""
        for i in range(len(self.records) - 1, -1, -1):
            record = self.records[i]
            if not record.get('R_t+1', {}).get('passed', True):
                self.trace_step(i)
                return
        
        console.print("[yellow]No violations found[/yellow]")
    
    def _display_trace(self, step_number, record, context, context_start):
        """Display trace report"""
        x_t = record.get('X_t', {})
        u_t = record.get('U_t', {})
        y_star_t = record.get('Y_star_t', {})
        y_t = record.get('Y_t+1', {})
        r_t = record.get('R_t+1', {})
        
        console.print("\n")
        console.print(Panel.fit(
            f"[bold cyan]🔍 K9log Incident Trace Report[/bold cyan]\n"
            f"Step #{step_number} - {record.get('timestamp', 'N/A')}",
            border_style="cyan"
        ))
        
        # Location info
        console.print("\n[bold]📍 Location[/bold]")
        console.print(f"   Skill: [cyan]{u_t.get('skill', 'unknown')}[/cyan]")
        console.print(f"   Agent: [cyan]{x_t.get('agent_name', 'unknown')}[/cyan] ({x_t.get('agent_id', 'N/A')})")
        console.print(f"   User: [cyan]{x_t.get('user', 'unknown')}[/cyan]")
        console.print(f"   Host: [cyan]{x_t.get('hostname', 'unknown')}[/cyan]")
        
        # Action
        console.print("\n[bold]⚡ Action Executed (U_t)[/bold]")
        params = u_t.get('params', {})
        for key, value in params.items():
            console.print(f"   {key} = [yellow]{value}[/yellow]")
        
        # Constraints
        console.print("\n[bold]🎯 Rules to Follow (Y*_t)[/bold]")
        y_star_meta = y_star_t.get('y_star_meta', {})
        console.print(f"   Source: [cyan]{y_star_meta.get('source', 'none')}[/cyan]")
        console.print(f"   Hash: [dim]{y_star_meta.get('hash', 'N/A')[:32]}...[/dim]")
        
        constraints = y_star_t.get('constraints', {})
        if constraints:
            for param, rules in constraints.items():
                console.print(f"   {param}:")
                for rule, value in rules.items():
                    console.print(f"      {rule} = {value}")
        else:
            console.print("   [dim]No constraints defined[/dim]")
        
        # Result
        console.print("\n[bold]📊 Result (Y_t+1)[/bold]")
        console.print(f"   Status: [cyan]{y_t.get('status', 'unknown')}[/cyan]")
        if 'result' in y_t:
            console.print(f"   Result: {y_t['result']}")
        
        # Assessment
        console.print("\n[bold]❌ Assessment (R_t+1)[/bold]")
        passed = r_t.get('passed', True)
        if passed:
            console.print("   [green]✅ Passed[/green]")
        else:
            console.print("   [red]❌ Failed[/red]")
            console.print(f"   Severity: [yellow]{r_t.get('overall_severity', 0):.2f}[/yellow]")
            console.print(f"   Risk: [red]{r_t.get('risk_level', 'UNKNOWN')}[/red]")
            
            violations = r_t.get('violations', [])
            if violations:
                console.print("\n   [bold]Violations:[/bold]")
                for v in violations:
                    severity_color = self._severity_color(v.get('severity', 0))
                    console.print(f"   • [{severity_color}]{v.get('message', 'Unknown')}[/{severity_color}]")
        
        # Timeline
        console.print("\n[bold]🔗 Timeline Context[/bold]")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Step", style="dim")
        table.add_column("Skill")
        table.add_column("Status")
        
        for i, ctx_record in enumerate(context):
            ctx_step = context_start + i
            ctx_skill = ctx_record.get('U_t', {}).get('skill', 'unknown')
            ctx_passed = ctx_record.get('R_t+1', {}).get('passed', True)
            
            if ctx_step == step_number:
                status = "[red]❌ ← Problem here![/red]" if not ctx_passed else "[green]✅[/green]"
                table.add_row(f"→ {ctx_step}", f"[bold]{ctx_skill}[/bold]", status)
            else:
                status = "[green]✅[/green]" if ctx_passed else "[red]❌[/red]"
                table.add_row(f"  {ctx_step}", ctx_skill, status)
        
        console.print(table)
        
        # Evidence integrity
        console.print("\n[bold]🛡️  Evidence Integrity[/bold]")
        integrity = record.get('_integrity', {})
        console.print(f"   Hash: [dim]{integrity.get('event_hash', 'N/A')[:32]}...[/dim]")
        console.print("   [green]✅ Verified[/green]")
    
    def _severity_color(self, severity):
        """Get color based on severity"""
        if severity >= 0.8:
            return "red"
        elif severity >= 0.5:
            return "yellow"
        else:
            return "blue"

def trace_incident(step=None, log_file=None):
    """Trace an incident"""
    tracer = IncidentTracer(log_file)
    
    if step is not None:
        tracer.trace_step(step)
    else:
        tracer.trace_last_violation()

