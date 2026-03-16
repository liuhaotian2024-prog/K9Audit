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
K9log CLI - Complete command line interface
"""
import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
console = Console()

@click.group()
@click.version_option(version='0.3.1')
def main():
    """K9log - Engineering-grade Causal Audit"""
    pass

@main.command()
def init():
    """Set up K9 Audit in the current project (creates .claude/settings.json)"""
    import json
    from pathlib import Path

    cwd = Path.cwd()
    claude_dir = cwd / ".claude"
    settings_path = claude_dir / "settings.json"

    console.print("[bold cyan]K9 Audit Setup[/bold cyan]")
    console.print(f"[dim]Project: {cwd}[/dim]\n")

    claude_dir.mkdir(exist_ok=True)

    existing = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
            console.print("[dim]Found existing .claude/settings.json — merging...[/dim]")
        except Exception:
            pass

    hooks = existing.get("hooks", {})
    hooks["PreToolUse"] = [{"matcher": ".*", "hooks": [{"type": "command", "command": "python -m k9log.hook"}]}]
    hooks["PostToolUse"] = [{"matcher": ".*", "hooks": [{"type": "command", "command": "python -m k9log.hook_post"}]}]
    existing["hooks"] = hooks

    settings_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    console.print("[green]✓ .claude/settings.json created[/green]")
    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print("  1. Run Claude Code in this directory — K9 will monitor every action")
    console.print("  2. Check results: [cyan]k9log stats[/cyan]")
    console.print("  3. Inspect violations: [cyan]k9log trace --last[/cyan]")
    console.print()
    console.print("[dim]Quick test — trigger your first violation:[/dim]")
    console.print("  [cyan]python -c \"from k9log.core import k9; @k9(deny_content=[\'staging.internal\']) \ndef f(x): return x\nf(\'https://api.staging.internal/v2\')\"[/cyan]")
    console.print("  [cyan]k9log trace --last[/cyan]")


@main.command()
def stats():
    """Show statistics"""
    from k9log.verifier import LogVerifier
    log_file = Path.home() / '.k9log' / 'logs' / 'k9log.cieu.jsonl'
    if not log_file.exists():
        console.print('[yellow]No logs found[/yellow]')
        return
    verifier = LogVerifier(log_file)
    total = 0
    violations = 0
    violation_types = {}
    for r in verifier._stream_records():
        if r.get('event_type') == 'SESSION_END':
            continue
        total += 1
        if not r.get('R_t+1', {}).get('passed', True):
            violations += 1
            for v in r.get('R_t+1', {}).get('violations', []):
                vtype = v.get('type', 'unknown')
                violation_types[vtype] = violation_types.get(vtype, 0) + 1
    passed = total - violations
    console.print('\n[cyan]K9log Statistics[/cyan]\n')
    console.print(f'[green]Total records:[/green] {total}')
    console.print(f'[green]Passed:[/green] {passed}')
    console.print(f'[red]Violations:[/red] {violations}')
    if total > 0:
        console.print(f'[yellow]Violation rate:[/yellow] {violations/total*100:.1f}%')
    if violation_types:
        console.print('\n[bold]Violation Types:[/bold]')
        for vtype, count in sorted(violation_types.items(), key=lambda x: -x[1]):
            console.print(f'  {vtype}: {count}')

@main.command()
@click.option('--step', type=int, help='Step number to trace')
@click.option('--last', is_flag=True, help='Trace last violation')
def trace(step, last):
    """Trace incident"""
    from k9log.tracer import IncidentTracer
    log_file = Path.home() / '.k9log' / 'logs' / 'k9log.cieu.jsonl'
    if not log_file.exists():
        console.print('[yellow]No logs found[/yellow]')
        return
    tracer = IncidentTracer(log_file)
    if last:
        tracer.trace_last_violation()
    elif step is not None:
        tracer.trace_step(step)
    else:
        console.print('[yellow]Please specify --step=N or --last[/yellow]')

@main.command()
@click.option('--step', type=int, default=None, help='Step number to analyze')
@click.option('--last', is_flag=True, default=False, help='Auto-find most recent failure')
@click.option('--export', type=click.Path(), default=None, help='Export causal analysis to JSON')
def causal(step, last, export):
    """Analyze causal chain and find root cause of a failure.

    Examples:

      k9log causal --last          # auto-find most recent failure

      k9log causal --step 7        # analyze specific step

      k9log causal --last --export causal.json
    """
    from k9log.causal_analyzer import CausalChainAnalyzer

    log_file = Path.home() / '.k9log' / 'logs' / 'k9log.cieu.jsonl'
    if not log_file.exists():
        console.print('[yellow]No logs found. Run some @k9-decorated functions first.[/yellow]')
        return

    analyzer = CausalChainAnalyzer(log_file)

    if not analyzer.records:
        console.print('[yellow]No records found in ledger.[/yellow]')
        return

    # Resolve which step to analyze
    if last:
        # Find the most recent execution failure or constraint violation
        incident_step = None
        for idx in range(len(analyzer.records) - 1, -1, -1):
            rec = analyzer.records[idx]
            r = rec.get('R_t+1', {})
            if not r.get('passed', True) or rec.get('_has_execution_failure'):
                incident_step = idx
                break
        if incident_step is None:
            console.print('[green]No failures found in ledger. All steps passed.[/green]')
            return
        console.print(f'[cyan]Auto-detected failure at Step #{incident_step}[/cyan]')
    elif step is not None:
        incident_step = step
    else:
        console.print('[red]Specify --last or --step N[/red]')
        console.print('  k9log causal --last')
        console.print('  k9log causal --step 7')
        return

    analyzer.build_causal_dag()
    analyzer.visualize_causal_chain(incident_step)

    if export:
        result = analyzer.find_root_causes(incident_step)
        import json as _json
        from pathlib import Path as _Path
        out = _Path(export)
        out.write_text(_json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        console.print(f'[green]Causal analysis exported to {export}[/green]')

@main.command(hidden=True)
@click.option('--policy', type=click.Path(exists=True), required=True, help='Policy config file (JSON)')
def counterfactual(policy):
    """Run counterfactual replay with alternative policy"""
    import json
    from k9log.counterfactual import replay_counterfactual
    log_file = Path.home() / '.k9log' / 'logs' / 'k9log.cieu.jsonl'
    if not log_file.exists():
        console.print('[yellow]No logs found[/yellow]')
        return
    with open(policy, 'r', encoding='utf-8-sig') as f:
        policy_config = json.load(f)
    console.print(f'[cyan]Loading policy: {policy_config.get("id", "unnamed")}[/cyan]\n')
    replay_counterfactual(policy_config, log_file)

@main.command(hidden=True)
def taint():
    """Analyze taint propagation and detect violations"""
    console.print("[yellow]This command is not included in the Phase 1 public release.[/yellow]")
    console.print("[dim]Available: stats, agents, trace, verify-log, verify-ystar, report, health[/dim]")
    return

@main.command('verify-log')
@click.argument('log_file', type=click.Path(exists=True), required=False)
def verify_log_cmd(log_file):
    """Verify log integrity"""
    from k9log.verifier import verify_log
    if not log_file:
        log_file = Path.home() / '.k9log' / 'logs' / 'k9log.cieu.jsonl'
    console.print(f'[cyan]Verifying {log_file}[/cyan]\n')
    result = verify_log(log_file)
    if result['passed']:
        console.print('[green]Log integrity verified[/green]')
        console.print(f"   Total records: {result['total_records']}")
        if 'session_root_hash' in result:
            console.print(f"   Session root hash: {result['session_root_hash'][:16]}...")
    else:
        console.print('[red]Log integrity verification failed[/red]')
        console.print(f"   Break point: Step #{result.get('break_point')}")
        console.print(f"   Reason: {result['message']}")

@main.command('verify-ystar')
@click.argument('log_file', type=click.Path(exists=True), required=False)
def verify_ystar_cmd(log_file):
    """Verify Y* consistency"""
    from k9log.verifier import verify_ystar
    if not log_file:
        log_file = Path.home() / '.k9log' / 'logs' / 'k9log.cieu.jsonl'
    console.print(f'[cyan]Verifying Y* in {log_file}[/cyan]\n')
    result = verify_ystar(log_file)
    summary = result['summary']
    console.print(f"[green]Y* verification complete[/green]")
    console.print(f"   Overall coverage: {summary['overall_coverage_rate']*100:.1f}%  "
                  f"({summary['covered_records']}/{summary['total_records']} calls)")
    if summary.get('coverage_warning'):
        console.print(f"   [yellow]{summary['coverage_warning']}[/yellow]")
    if summary['uncovered_skills']:
        console.print(f"   [red]Uncovered skills: {', '.join(summary['uncovered_skills'])}[/red]")
    if summary['multi_version_skills']:
        console.print(f"   [yellow]Constraint drift: {', '.join(summary['multi_version_skills'])}[/yellow]")
    if result['skills']:
        from rich.table import Table as _Table
        table = _Table(show_header=True)
        table.add_column("Skill")
        table.add_column("Calls")
        table.add_column("Coverage")
        table.add_column("Violations")
        table.add_column("Status")
        for s in result['skills']:
            sc = 'red' if s['status'] == 'UNCOVERED' else 'yellow' if s['status'] == 'MULTI_VERSION' else 'green'
            table.add_row(s['skill'], str(s['total_calls']),
                          f"{s['coverage_rate']*100:.0f}%", str(s['violations_found']),
                          f"[{sc}]{s['status']}[/{sc}]")
        console.print(table)

@main.command()
def agents():
    """Show agent statistics"""
    from k9log.verifier import LogVerifier
    log_file = Path.home() / '.k9log' / 'logs' / 'k9log.cieu.jsonl'
    if not log_file.exists():
        console.print('[yellow]No logs found[/yellow]')
        return
    verifier = LogVerifier(log_file)
    agent_stats = {}
    for record in verifier._stream_records():
        if record.get('event_type') == 'SESSION_END':
            continue
        agent_id = record.get('X_t', {}).get('agent_id', 'unknown')
        agent_name = record.get('X_t', {}).get('agent_name', 'unknown')
        passed = record.get('R_t+1', {}).get('passed', True)
        if agent_id not in agent_stats:
            agent_stats[agent_id] = {'name': agent_name, 'total': 0, 'violations': 0}
        agent_stats[agent_id]['total'] += 1
        if not passed:
            agent_stats[agent_id]['violations'] += 1
    console.print('\n[cyan]Agent Statistics[/cyan]\n')
    table = Table(show_header=True)
    table.add_column("Agent ID")
    table.add_column("Name")
    table.add_column("Total Ops")
    table.add_column("Violations")
    table.add_column("Rate")
    for agent_id, s in agent_stats.items():
        rate = s['violations'] / s['total'] * 100 if s['total'] > 0 else 0
        table.add_row(agent_id[:16] + '...', s['name'], str(s['total']), str(s['violations']), f"{rate:.1f}%")
    console.print(table)

# --- Week 9-10: Alerting Commands ---

@main.group(hidden=True)
def alerts():
    """Smart alerting system management"""
    pass

@alerts.command()
def status():
    """Show current alerting configuration and status"""
    from k9log.alerting import _load_config, HISTORY_PATH
    config = _load_config()
    enabled = config.get('enabled', False)
    console.print('\n[cyan]Alerting System Status[/cyan]\n')
    if enabled:
        console.print('[green]Status: ENABLED[/green]')
    else:
        console.print('[yellow]Status: DISABLED[/yellow]')
        console.print('  Run: k9log alerts enable')
    # Channels
    console.print('\n[bold]Channels:[/bold]')
    channels = config.get('channels', {})
    for name in ['telegram', 'slack', 'discord', 'webhook']:
        ch = channels.get(name, {})
        if ch.get('enabled', False):
            console.print(f'  [green]{name}: ON[/green]')
        else:
            console.print(f'  [dim]{name}: OFF[/dim]')
    # Rules
    rules = config.get('rules', {})
    console.print(f"\n[bold]Rules:[/bold]")
    console.print(f"  Min severity: {rules.get('min_severity', 0.0)}")
    console.print(f"  Skill filter: {rules.get('skills', []) or 'all'}")
    console.print(f"  Type filter: {rules.get('violation_types', []) or 'all'}")
    # Dedup
    dedup = config.get('dedup', {})
    console.print(f"\n[bold]Dedup:[/bold] {'ON' if dedup.get('enabled', True) else 'OFF'} (window: {dedup.get('window_seconds', 300)}s)")
    # Aggregation
    agg = config.get('aggregation', {})
    console.print(f"[bold]Aggregation:[/bold] {'ON' if agg.get('enabled', True) else 'OFF'} (window: {agg.get('window_seconds', 60)}s, batch: {agg.get('max_batch', 10)})")
    # DND
    dnd = config.get('dnd', {})
    if dnd.get('enabled', False):
        console.print(f"[bold]DND:[/bold] ON ({dnd.get('start', '23:00')} ~ {dnd.get('end', '07:00')}, UTC+{dnd.get('timezone_offset_hours', 8)})")
    else:
        console.print(f"[bold]DND:[/bold] OFF")
    # History stats
    if HISTORY_PATH.exists():
        import json as _json
        lines = HISTORY_PATH.read_text(encoding='utf-8').strip().split('\n')
        total_alerts = len(lines)
        suppressed = sum(1 for l in lines if '"suppressed":' in l and '"suppressed": null' not in l)
        console.print(f"\n[bold]History:[/bold] {total_alerts} events ({suppressed} suppressed)")

@alerts.command()
def enable():
    """Enable alerting system"""
    from k9log.alerting import _load_config, _save_config
    config = _load_config()
    config['enabled'] = True
    _save_config(config)
    console.print('[green]Alerting system ENABLED[/green]')

@alerts.command()
def disable():
    """Disable alerting system"""
    from k9log.alerting import _load_config, _save_config
    config = _load_config()
    config['enabled'] = False
    _save_config(config)
    console.print('[yellow]Alerting system DISABLED[/yellow]')

@alerts.command('set-telegram')
@click.option('--token', required=True, help='Telegram Bot API token')
@click.option('--chat-id', required=True, help='Telegram chat ID')
def set_telegram(token, chat_id):
    """Configure Telegram channel"""
    from k9log.alerting import _load_config, _save_config
    config = _load_config()
    if 'channels' not in config:
        config['channels'] = {}
    config['channels']['telegram'] = {
        'enabled': True,
        'bot_token': token,
        'chat_id': chat_id
    }
    _save_config(config)
    console.print('[green]Telegram channel configured and enabled[/green]')

@alerts.command('set-slack')
@click.option('--webhook-url', required=True, help='Slack Incoming Webhook URL')
def set_slack(webhook_url):
    """Configure Slack channel"""
    from k9log.alerting import _load_config, _save_config
    config = _load_config()
    if 'channels' not in config:
        config['channels'] = {}
    config['channels']['slack'] = {
        'enabled': True,
        'webhook_url': webhook_url
    }
    _save_config(config)
    console.print('[green]Slack channel configured and enabled[/green]')

@alerts.command('set-discord')
@click.option('--webhook-url', required=True, help='Discord Webhook URL')
def set_discord(webhook_url):
    """Configure Discord channel"""
    from k9log.alerting import _load_config, _save_config
    config = _load_config()
    if 'channels' not in config:
        config['channels'] = {}
    config['channels']['discord'] = {
        'enabled': True,
        'webhook_url': webhook_url
    }
    _save_config(config)
    console.print('[green]Discord channel configured and enabled[/green]')

@alerts.command('set-webhook')
@click.option('--url', required=True, help='Generic webhook URL')
def set_webhook(url):
    """Configure generic webhook channel"""
    from k9log.alerting import _load_config, _save_config
    config = _load_config()
    if 'channels' not in config:
        config['channels'] = {}
    config['channels']['webhook'] = {
        'enabled': True,
        'url': url
    }
    _save_config(config)
    console.print('[green]Webhook channel configured and enabled[/green]')

@alerts.command('set-dnd')
@click.option('--start', default='23:00', help='DND start time (HH:MM)')
@click.option('--end', default='07:00', help='DND end time (HH:MM)')
@click.option('--offset', default=8, type=int, help='UTC offset hours')
def set_dnd(start, end, offset):
    """Configure Do Not Disturb window"""
    from k9log.alerting import _load_config, _save_config
    config = _load_config()
    config['dnd'] = {
        'enabled': True,
        'start': start,
        'end': end,
        'timezone_offset_hours': offset
    }
    _save_config(config)
    console.print(f'[green]DND enabled: {start} ~ {end} (UTC+{offset})[/green]')

@alerts.command('disable-dnd')
def disable_dnd():
    """Disable Do Not Disturb"""
    from k9log.alerting import _load_config, _save_config
    config = _load_config()
    config['dnd'] = config.get('dnd', {})
    config['dnd']['enabled'] = False
    _save_config(config)
    console.print('[yellow]DND disabled[/yellow]')

@alerts.command()
def test():
    """Send a test alert to all configured channels"""
    from k9log.alerting import get_alert_manager, _format_single_alert
    manager = get_alert_manager()
    manager.reload_config()
    if not manager.config.get('enabled', False):
        console.print('[yellow]Alerting is disabled. Run: k9log alerts enable[/yellow]')
        return
    channels = manager.config.get('channels', {})
    has_channel = any(ch.get('enabled', False) for ch in channels.values())
    if not has_channel:
        console.print('[yellow]No channels configured. Use k9log alerts set-telegram/set-slack/set-discord/set-webhook[/yellow]')
        return
    test_record = {
        'timestamp': '2026-02-11T12:00:00Z',
        'X_t': {'agent_id': 'test-agent-001', 'agent_name': 'TestAgent'},
        'U_t': {'skill': 'test_skill', 'params': {'amount': 9999}},
        'Y_star_t': {'constraints': {'amount': {'max': 1000}}},
        'Y_t+1': {'status': 'success', 'result': {}},
        'R_t+1': {
            'passed': False,
            'violations': [{'param': 'amount', 'type': 'max_exceeded', 'actual': 9999, 'constraint': 1000}],
            'overall_severity': 0.9,
            'risk_level': 'HIGH'
        },
        '_integrity': {'seq': 0, 'event_hash': 'test', 'prev_hash': 'test'}
    }
    console.print('[cyan]Sending test alert...[/cyan]')
    message = _format_single_alert(test_record)
    sent = manager._dispatch(message, test_record)
    if sent:
        console.print(f'[green]Test alert sent to: {", ".join(sent)}[/green]')
    else:
        console.print('[red]Failed to send test alert. Check your channel configuration.[/red]')

@alerts.command()
@click.option('--last', default=20, type=int, help='Number of recent entries to show')
def history(last):
    """Show alert history"""
    import json as _json
    from k9log.alerting import HISTORY_PATH
    if not HISTORY_PATH.exists():
        console.print('[yellow]No alert history found[/yellow]')
        return
    lines = HISTORY_PATH.read_text(encoding='utf-8').strip().split('\n')
    recent = lines[-last:]
    console.print(f'\n[cyan]Alert History (last {min(last, len(lines))} of {len(lines)})[/cyan]\n')
    table = Table(show_header=True)
    table.add_column("Time")
    table.add_column("Count")
    table.add_column("Skills")
    table.add_column("Channels")
    table.add_column("Suppressed")
    for line in recent:
        try:
            entry = _json.loads(line)
            ts = entry.get('timestamp', '?')[:19]
            count = str(entry.get('alert_count', 1))
            skills = ', '.join(entry.get('skills', []))
            channels = ', '.join(entry.get('channels_sent', [])) or '-'
            suppressed = entry.get('suppressed') or '-'
            table.add_row(ts, count, skills, channels, suppressed)
        except Exception:
            pass
    console.print(table)
    # Summary
    total = len(lines)
    sent_count = sum(1 for l in lines if '"channels_sent": []' not in l and '"suppressed": null' not in l)
    console.print(f'\n  Total: {total} | Sent: {sent_count} | Suppressed: {total - sent_count}')



# --- Fuse Commands ---
@main.group(hidden=True)
def fuse():
    """Circuit breaker (FUSE) management"""
    pass


@fuse.command()
def status():
    """Show current fuse state"""
    console.print("[yellow]This command is not included in the Phase 1 public release.[/yellow]")
    console.print("[dim]Available: stats, agents, trace, verify-log, verify-ystar, report, health[/dim]")
    return


@fuse.command()
def disarm():
    """Clear fuse state (allow agent to resume)"""
    from k9log.fuse import disarm as _disarm, load_state
    state = load_state()
    if not state.get('active'):
        console.print('[yellow]FUSE is not currently active.[/yellow]')
    else:
        _disarm()
        console.print('[green]FUSE disarmed. Agent may resume.[/green]')
        console.print('  Run [bold]k9log fuse arm[/bold] to re-enable fuse for future violations.')


@fuse.command()
def arm():
    """Re-arm fuse so it can trigger on future violations"""
    console.print("[yellow]This command is not included in the Phase 1 public release.[/yellow]")
    console.print("[dim]Available: stats, agents, trace, verify-log, verify-ystar, report, health[/dim]")
    return


# --- Policy Commands ---
@main.group(hidden=True)
def policy():
    """Policy Pack management"""
    pass


@policy.command()
def status():
    """Show current active policy status"""
    console.print("[yellow]This command is not included in the Phase 1 public release.[/yellow]")
    console.print("[dim]Available: stats, agents, trace, verify-log, verify-ystar, report, health[/dim]")
    return


@policy.command()
@click.option('--path', required=True, help='Path to policy JSON file')
@click.option('--sig', default=None, help='Path to .sig file for HMAC verification')
def load(path, sig):
    """Load a policy file as the active policy"""
    console.print("[yellow]This command is not included in the Phase 1 public release.[/yellow]")
    console.print("[dim]Available: stats, agents, trace, verify-log, verify-ystar, report, health[/dim]")
    return


@policy.command()
def pin():
    """Output current policy hash (for reproducibility)"""
    from k9log.policy_pack import get_active_policy, policy_hash
    pol = get_active_policy()
    if pol is None:
        console.print('[yellow]No policy loaded. Hash: (none)[/yellow]')
        return
    console.print(policy_hash(pol))

@main.command()
@click.option('--output', default='k9log_report.html', help='Output file path')
def report(output):
    """Generate HTML audit report"""
    from k9log.report import generate_report
    log_file = Path.home() / '.k9log' / 'logs' / 'k9log.cieu.jsonl'
    if not log_file.exists():
        console.print('[yellow]No logs found[/yellow]')
        return
    console.print('[cyan]Generating report...[/cyan]')
    result = generate_report(log_file, output)
    if result:
        console.print(f'[green]Report saved: {result}[/green]')


@main.command(hidden=True)
@click.option('--run-dir', required=True, help='Replay result directory')
@click.option('--out', required=True, help='Output zip path')
def bundle(run_dir, out):
    """Package a replay run into a portable evidence bundle (zip)"""
    import zipfile
    import json as _json
    from pathlib import Path as _Path
    from datetime import datetime, timezone

    run_path = _Path(run_dir)
    out_path  = _Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not run_path.exists():
        console.print(f'[red]Run dir not found: {run_path}[/red]')
        return

    files_added = []
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname in ['k9log.cieu.jsonl', 'metrics.json', 'replay_summary.json',
                      'alert_history.jsonl', 'policy.json', 'policy.sig']:
            fp = run_path / fname
            if fp.exists():
                zf.write(fp, fname)
                files_added.append(fname)
        for fname in ['fuse/state.json', 'fuse/events.jsonl']:
            fp = run_path / fname
            if fp.exists():
                zf.write(fp, fname)
                files_added.append(fname)
        for fp in run_path.glob('*.html'):
            zf.write(fp, fp.name)
            files_added.append(fp.name)
        log_file = run_path / 'k9log.cieu.jsonl'
        if log_file.exists():
            try:
                from k9log.verifier import verify_log
                import json as _json2
                result = verify_log(log_file)
                # Policy pin summary
                policy_id = 'N/A'; policy_version = 'N/A'; policy_hash_val = 'N/A'
                try:
                    records = [_json2.loads(l) for l in log_file.read_text(encoding='utf-8').splitlines() if l.strip()]
                    pins = [r.get('_policy') for r in records if r.get('_policy')]
                    if pins:
                        policy_id = pins[0].get('policy_id', 'N/A')
                        policy_version = pins[0].get('version', 'N/A')
                        policy_hash_val = pins[0].get('hash', 'N/A')
                        hashes = {p.get('hash') for p in pins}
                        policy_consistent = 'YES' if len(hashes) == 1 else f'NO ({len(hashes)} hashes)'
                    else:
                        policy_consistent = 'no policy pin'
                except Exception:
                    policy_consistent = 'unknown'
                # File manifest hashes
                manifest_lines = []
                for mf in files_added:
                    fp = run_path / mf
                    if fp.exists():
                        import hashlib as _hl
                        h = _hl.sha256(fp.read_bytes()).hexdigest()[:16]
                        manifest_lines.append(f'  {mf}: sha256:{h}')
                manifest_str = '\n'.join(manifest_lines) if manifest_lines else '  (none)'
                verify_txt = (
                    f"k9log verify-log\n"
                    f"==================\n"
                    f"File         : {log_file.name}\n"
                    f"Passed       : {result.get('passed')}\n"
                    f"Records      : {result.get('total_records', '?')}\n"
                    f"Root hash    : {result.get('session_root_hash', 'N/A')}\n"
                    f"Message      : {result.get('message', '')}\n"
                    f"Policy ID    : {policy_id}\n"
                    f"Policy ver   : {policy_version}\n"
                    f"Policy hash  : {policy_hash_val}\n"
                    f"Policy pin   : {policy_consistent}\n"
                    f"File hashes  :\n{manifest_str}\n"
                    f"Generated    : {datetime.now(timezone.utc).isoformat()}\n"
                )
                zf.writestr('verify_summary.txt', verify_txt)
                files_added.append('verify_summary.txt')
            except Exception as e:
                zf.writestr('verify_summary.txt', f'verify failed: {e}')
                files_added.append('verify_summary.txt')
        manifest = {
            'bundle_created': datetime.now(timezone.utc).isoformat(),
            'source_dir': str(run_path),
            'files': files_added,
        }
        zf.writestr('MANIFEST.json', _json.dumps(manifest, indent=2))

    console.print(f'[green]Bundle created: {out_path}[/green]')
    for f in files_added:
        console.print(f'  + {f}')
    console.print(f'  + MANIFEST.json')


@main.group(hidden=True)
def hooks():
    "k9log git hooks management"
    pass


@hooks.command('install')
def hooks_install():
    "Install k9log pre-commit hook into current git repository"
    import sys
    from pathlib import Path
    installer = Path(__file__).parent.parent / 'hooks' / 'install.py'
    if not installer.exists():
        console.print('[red]Error: hooks/install.py not found[/red]')
        sys.exit(1)
    import importlib.util
    spec = importlib.util.spec_from_file_location('install', installer)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.install()



@main.group(hidden=True)
def grants():
    """Federated grant library management"""
    pass

@grants.command("import")
@click.argument("source")
def grants_import(source):
    """Import a grant from URL or local file path"""
    console.print("[yellow]This command is not included in the Phase 1 public release.[/yellow]")
    console.print("[dim]Available: stats, agents, trace, verify-log, verify-ystar, report, health[/dim]")
    return

@grants.command("export")
@click.option("--id", "grant_id", required=True, help="Grant ID to export")
@click.option("--output", default=".", help="Output directory")
def grants_export(grant_id, output):
    """Export a grant file for sharing with other teams"""
    from k9log.federated import export_grant
    export_grant(grant_id, output)

@grants.command("list")
def grants_list():
    """List all active and suggested grants"""
    console.print("[yellow]This command is not included in the Phase 1 public release.[/yellow]")
    console.print("[dim]Available: stats, agents, trace, verify-log, verify-ystar, report, health[/dim]")
    return

@grants.command("verify")
@click.argument("grant_path")
def grants_verify(grant_path):
    """Verify a grant file against local CIEU log"""
    from k9log.federated import verify_grant
    verify_grant(grant_path)

@grants.command("approve")
@click.argument("grant_id", required=False)
@click.option("--all", "approve_all", is_flag=True, help="Approve all suggested grants")
def grants_approve(grant_id, approve_all):
    """Move suggested grant(s) to active grants directory"""
    import json, shutil
    from rich.console import Console
    from rich.table import Table
    console = Console()
    suggested_dir = Path.home() / ".k9log" / "grants" / "suggested"
    active_dir = Path.home() / ".k9log" / "grants"
    if not suggested_dir.exists():
        console.print("[yellow]No suggested grants found.[/yellow]")
        return
    files = sorted(suggested_dir.glob("*.json"))
    if not files:
        console.print("[yellow]No suggested grants to approve.[/yellow]")
        return
    if not approve_all and not grant_id:
        # Show list and ask
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Grant ID")
        table.add_column("Description")
        for f in files:
            try:
                g = json.loads(f.read_text(encoding="utf-8"))
                table.add_row(g.get("grant_id", f.stem), g.get("description", "")[:80])
            except Exception:
                table.add_row(f.stem, "(unreadable)")
        console.print(table)
        console.print("[dim]Use --all to approve all, or pass a grant_id to approve one.[/dim]")
        return
    approved = []
    for f in files:
        try:
            g = json.loads(f.read_text(encoding="utf-8"))
            gid = g.get("grant_id", f.stem)
            if approve_all or gid == grant_id:
                dest = active_dir / f.name
                shutil.copy2(f, dest)
                f.unlink()
                approved.append(gid)
                console.print(f"[green]✅ Approved:[/green] {gid}")
        except Exception as e:
            console.print(f"[red]Failed to approve {f.name}: {e}[/red]")
    if not approved:
        console.print(f"[yellow]No grant matching '{grant_id}' found in suggested.[/yellow]")
    else:
        console.print(f"[bold green]{len(approved)} grant(s) activated.[/bold green]")

@main.command("learn", hidden=True)
def learn_cmd():
    """Run causal metalearning — suggest grants from incident history"""
    console.print("[yellow]This command is not included in the Phase 1 public release.[/yellow]")
    console.print("[dim]Available: stats, agents, trace, verify-log, verify-ystar, report, health[/dim]")
    return


@main.command("health")
@click.option("--log", default=None, help="CIEU log path (default: ~/.k9log/logs/k9log.cieu.jsonl)")
def health_cmd(log):
    """System health -- Ledger stats + chain integrity + coverage in one view"""
    import os, json as _json
    from pathlib import Path
    from rich.panel import Panel

    log_path = Path(log) if log else Path.home() / ".k9log" / "logs" / "k9log.cieu.jsonl"
    if not log_path.exists():
        console.print("[red]CIEU log not found: " + str(log_path) + "[/red]")
        return

    console.print(Panel.fit(
        "[bold cyan]K9log Health Report[/bold cyan]\n[dim]" + str(log_path) + "[/dim]",
        border_style="cyan"
    ))

    # -- 1. Streaming stats ---------------------------------------------------
    from collections import Counter
    total = 0; violations_tot = 0
    violation_types = Counter()
    skill_total = Counter(); skill_covered = Counter()

    with open(log_path, encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line: continue
            try: r = _json.loads(line)
            except Exception: continue
            if "X_t" not in r: continue
            total += 1
            skill = r.get("U_t", {}).get("skill", "?")
            skill_total[skill] += 1
            if r.get("Y_star_t", {}).get("constraints"):
                skill_covered[skill] += 1
            if not r.get("R_t+1", {}).get("passed", True):
                violations_tot += 1
                for v in r.get("R_t+1", {}).get("violations", []):
                    violation_types[v.get("type", "?")] += 1

    passed_tot = total - violations_tot
    vrate = violations_tot / total * 100 if total else 0
    covered = sum(skill_covered.values())
    cov_pct = int(100 * covered / total) if total else 0

    # -- 2. Chain integrity ---------------------------------------------------
    from k9log.verifier import LogVerifier, COVERAGE_WARN_THRESHOLD
    integrity = LogVerifier(log_path).verify_integrity()
    chain_ok  = integrity["passed"]

    # -- 3. Summary -----------------------------------------------------------
    chain_line = (
        "[green]OK  Chain Intact[/green]" if chain_ok
        else "[red]BROKEN -- " + str(integrity.get("message", "")) + "[/red]"
    )
    cov_color = "green" if cov_pct >= int(COVERAGE_WARN_THRESHOLD * 100) else "yellow"
    console.print(
        f"\n  Ledger     [white]{total}[/white] records  "
        f"[green]{passed_tot} passed[/green]  "
        f"[red]{violations_tot} violations[/red]  "
        f"([yellow]{vrate:.1f}%[/yellow] rate)"
    )
    console.print(f"  Integrity  {chain_line}")
    console.print(
        f"  Coverage   [{cov_color}]{cov_pct}%[/{cov_color}]  "
        f"({covered}/{total} calls constrained)"
    )
    if cov_pct < int(COVERAGE_WARN_THRESHOLD * 100):
        console.print(
            f"  [yellow]Coverage below {int(COVERAGE_WARN_THRESHOLD*100)}% -- "
            f"add @k9 constraints to uncovered skills[/yellow]"
        )

    # -- 4. Skill table -------------------------------------------------------
    console.print("\n[bold]Skill Coverage[/bold]")
    tbl = Table(show_header=True, header_style="bold")
    tbl.add_column("Skill"); tbl.add_column("Calls", justify="right")
    tbl.add_column("Constrained", justify="right"); tbl.add_column("Status")
    for skill in sorted(skill_total.keys()):
        c = skill_covered[skill]; t = skill_total[skill]
        status = "[green]OK[/green]" if c == t else "[yellow]PARTIAL[/yellow]" if c > 0 else "[red]UNCOVERED[/red]"
        tbl.add_row(skill, str(t), str(c), status)
    console.print(tbl)

    # -- 5. Violation breakdown -----------------------------------------------
    if violation_types:
        console.print("\n[bold]Violation Types[/bold]")
        for vt, cnt in violation_types.most_common():
            console.print(f"  [red]{vt}[/red]: {cnt}")

    # -- 6. Module availability -----------------------------------------------
    console.print("\n[bold]Module Availability[/bold]")
    for mod, label in [
        ("k9log.logger","Logger"),("k9log.constraints","Constraints"),
        ("k9log.verifier","Verifier"),("k9log.tracer","Tracer"),
        ("k9log.report","Report"),("k9log.alerting","Alerting"),
        ("k9log.taint","Taint analysis"),("k9log.metalearning","Metalearning"),
    ]:
        try:
            __import__(mod)
            console.print(f"  [green]OK[/green]  {label}")
        except ImportError:
            console.print(f"  [yellow]--[/yellow]  {label} unavailable")

    console.print()

@main.group(hidden=True)
def task():
    """Task-scoped session grant management"""
    pass

@task.command("start")
@click.option("--goal", required=True, help="Task goal description")
@click.option("--allow-write", multiple=True, help="Allowed write paths")
@click.option("--allow-run", multiple=True, help="Allowed commands")
@click.option("--deny-content", multiple=True, help="Blocked content keywords")
@click.option("--expires", default="session", help="Expiry: session or ISO datetime")
def task_start(goal, allow_write, allow_run, deny_content, expires):
    """Start a task — create session-scoped grant and write to CLAUDE.md"""
    import json, os
    from datetime import datetime, timezone
    from pathlib import Path

    task_id = f"task-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    grant = {
        "grant_id": task_id,
        "issuer": "user",
        "reason": goal,
        "allowed_action_classes": ["READ", "WRITE", "EXECUTE"],
        "scope": {
            "paths": list(allow_write),
            "commands": list(allow_run),
            "deny_content": list(deny_content),
        },
        "expires_at": None if expires == "session" else expires,
        "session_scoped": expires == "session",
        "granted_at": datetime.now(timezone.utc).isoformat(),
    }

    # 写入 active grants
    grants_dir = Path.home() / ".k9log" / "grants"
    grants_dir.mkdir(parents=True, exist_ok=True)
    grant_path = grants_dir / f"{task_id}.json"
    grant_path.write_text(json.dumps(grant, indent=2, ensure_ascii=False), encoding="utf-8")

    # 写入 Agent 上下文文件（文件名从 identity 配置读取，默认 AGENTS.md，兜底 CLAUDE.md）
    # 支持任意 Agent 的上下文文件：通过 ~/.k9log/config/identity.json 的
    # "context_file" 字段配置，例如 "AGENTS.md" / "SYSTEM.md" / "CLAUDE.md"
    import json as _json_id
    _id_cfg_path = Path.home() / ".k9log" / "config" / "identity.json"
    _context_filename = "AGENTS.md"  # universal default (agent-agnostic)
    if _id_cfg_path.exists():
        try:
            _id_cfg = _json_id.loads(_id_cfg_path.read_text(encoding="utf-8"))
            _context_filename = _id_cfg.get("context_file", _context_filename)
        except Exception:
            pass
    claude_md = Path.cwd() / _context_filename
    if claude_md.exists():
        content = claude_md.read_text(encoding="utf-8")
        # 移除旧的 task 段
        import re
        content = re.sub(r'<!-- k9:task:start -->.*?<!-- k9:task:end -->', '', content, flags=re.DOTALL)
    else:
        content = ""

    task_block = f"""
<!-- k9:task:start -->
## Current Task Grant
task_id: {task_id}
goal: {goal}
allow_paths: {list(allow_write)}
allow_commands: {list(allow_run)}
deny_content: {list(deny_content)}
expires: {expires}
grant_file: {grant_path}
<!-- k9:task:end -->
"""
    claude_md.write_text(content.strip() + task_block, encoding="utf-8")

    console.print(f"[green]✅ Task started: {task_id}[/green]")
    console.print(f"   Goal: {goal}")
    console.print(f"   Grant: {grant_path}")
    console.print(f"   CLAUDE.md updated")
    console.print(f"   Expires: {expires}")

@task.command("stop")
def task_stop():
    """Stop current task — remove session-scoped grants"""
    import re, json
    from pathlib import Path

    grants_dir = Path.home() / ".k9log" / "grants"
    removed = []
    for f in grants_dir.glob("task-*.json"):
        try:
            g = json.loads(f.read_text(encoding="utf-8"))
            if g.get("session_scoped"):
                f.unlink()
                removed.append(f.stem)
        except Exception:
            pass

    # 清理 Agent 上下文文件的 task 段（读取与 task_start 相同的 context_file 配置）
    import json as _json_id2
    _id_cfg_path2 = Path.home() / ".k9log" / "config" / "identity.json"
    _context_filename2 = "AGENTS.md"
    if _id_cfg_path2.exists():
        try:
            _id_cfg2 = _json_id2.loads(_id_cfg_path2.read_text(encoding="utf-8"))
            _context_filename2 = _id_cfg2.get("context_file", _context_filename2)
        except Exception:
            pass
    claude_md = Path.cwd() / _context_filename2
    if claude_md.exists():
        content = claude_md.read_text(encoding="utf-8")
        content = re.sub(r'\n<!-- k9:task:start -->.*?<!-- k9:task:end -->\n', '', content, flags=re.DOTALL)
        claude_md.write_text(content, encoding="utf-8")

    if removed:
        console.print(f"[green]✅ Task stopped. Removed grants: {removed}[/green]")
    else:
        console.print("[yellow]No active session-scoped tasks found.[/yellow]")



# ── 联邦学习命令组 ──────────────────────────────────────────────────────────

@main.group(hidden=True)
def federated():
    """联邦学习：匿名贡献 skill 行为统计，获得社区共享的风险画像。"""
    pass


@federated.command("join")
def federated_join_cmd():
    """加入联邦学习计划。

    \b
    K9log 会把本地观测到的 skill 行为统计（脱敏后）贡献给社区知识库，
    您也将获得来自整个社区的 skill 风险画像和提前预警。

    原始操作记录永远不会离开您的设备。数学保证，开源可审查。
    """
    console.print("[yellow]This command is not included in the Phase 1 public release.[/yellow]")
    console.print("[dim]Available: stats, agents, trace, verify-log, verify-ystar, report, health[/dim]")
    return


@federated.command("leave")
def federated_leave_cmd():
    """退出联邦学习计划。"""
    from k9log.wizard import federated_leave
    federated_leave()


@federated.command("status")
def federated_status_cmd():
    """查看联邦学习参与状态。"""
    console.print("[yellow]This command is not included in the Phase 1 public release.[/yellow]")
    console.print("[dim]Available: stats, agents, trace, verify-log, verify-ystar, report, health[/dim]")
    return


# ── Skill 推荐命令组 ────────────────────────────────────────────────────────

@main.group(hidden=True)
def skills():
    """Skill 因果推荐与 K 指数排行榜。"""
    pass


@skills.command("recommend")
@click.option("--action", default=None, help="当前操作类型（READ/WRITE/EXECUTE/...）")
@click.option("--agent-type", default=None, help="Agent 类型（coding/research/...）")
@click.option("--top", default=5, type=int, help="返回条数（默认 5）")
@click.option("--json-out", is_flag=True, help="输出原始 JSON")
def skills_recommend(action, agent_type, top, json_out):
    """基于当前上下文推荐 K 指数最高的 skill。

    \b
    示例：
      k9log skills recommend --action EXECUTE --agent-type coding
      k9log skills recommend --top 10 --json-out
    """
    console.print("[yellow]This command is not included in the Phase 1 public release.[/yellow]")
    console.print("[dim]Available: stats, agents, trace, verify-log, verify-ystar, report, health[/dim]")
    return

    ctx = {}
    if action:     ctx["action_class"] = action.upper()
    if agent_type: ctx["agent_type"]   = agent_type.lower()

    results = engine.recommend(context=ctx or None, top_n=top)

    if json_out:
        import json as _json
        console.print(_json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False))
        return

    if not results:
        console.print("[yellow]暂无推荐数据（CIEU 日志为空或无 skill_source 记录）[/yellow]")
        console.print("[dim]提示：使用 set_active_skill() 注册 skill 后，运行记录会自动积累[/dim]")
        return

    console.print()
    console.print("[bold cyan]K9log Skill 推荐[/bold cyan]")
    if ctx:
        console.print(f"[dim]上下文：{ctx}[/dim]")
    console.print()

    for i, r in enumerate(results, 1):
        k_color = "green" if r.k_index > 0.1 else "yellow" if r.k_index > 0 else "red"
        console.print(
            f"  [{k_color}]{i}. {r.skill.name}[/{k_color}] "
            f"v{r.skill.version}  [bold]K={r.k_index:.3f}[/bold]"
        )
        console.print(f"     理由：{r.reason}")
        if r.caution:
            console.print(f"     [yellow]注意：{r.caution}[/yellow]")
        console.print(f"     [dim]安全增益={r.safety_gain:+.3f}  能力增益={r.capability_gain:+.3f}"
                      f"  不确定性={r.uncertainty:.3f}  上下文匹配={r.context_sim:.2f}[/dim]")
        console.print()


@skills.command("ranking")
@click.option("--top", default=20, type=int, help="排行榜条数（默认 20）")
@click.option("--json-out", is_flag=True, help="输出原始 JSON")
def skills_ranking(top, json_out):
    """K 指数全局排行榜（不考虑上下文，公平对比所有 skill）。"""
    console.print("[yellow]This command is not included in the Phase 1 public release.[/yellow]")
    console.print("[dim]Available: stats, agents, trace, verify-log, verify-ystar, report, health[/dim]")
    return

    if json_out:
        import json as _json
        console.print(_json.dumps(ranking, indent=2, ensure_ascii=False))
        return

    if not ranking:
        console.print("[yellow]暂无排行数据[/yellow]")
        return

    console.print()
    console.print("[bold cyan]K 技术指数排行榜[/bold cyan]  [dim]（新旧 skill 公平竞争，不含累计运行次数）[/dim]")
    console.print()
    console.print(f"  {'排名':<4} {'Skill':<28} {'版本':<10} {'K 指数':>8} {'安全增益':>9} {'不确定性':>9} {'观测天数':>9}")
    console.print("  " + "─" * 80)

    for i, r in enumerate(ranking, 1):
        k = r["k_index"]
        k_str = f"{k:+.3f}"
        k_color = "green" if k > 0.1 else "yellow" if k > 0 else "red"
        console.print(
            f"  {i:<4} [{k_color}]{r['name']:<28}[/{k_color}]"
            f" {r['version']:<10} [{k_color}]{k_str:>8}[/{k_color}]"
            f" {r['safety_gain']:>+9.3f} {r['uncertainty']:>9.3f}"
            f" {r['observation_days']:>9.1f}"
        )
    console.print()


@skills.command("diagnose")
@click.argument("skill_hash")
@click.option("--action", default=None, help="当前操作类型")
@click.option("--agent-type", default=None)
def skills_diagnose(skill_hash, action, agent_type):
    """诊断单个 skill 在当前上下文中是否值得使用。

    \b
    示例：
      k9log skills diagnose 3f9a8b2c --action EXECUTE
    """
    console.print("[yellow]This command is not included in the Phase 1 public release.[/yellow]")
    console.print("[dim]Available: stats, agents, trace, verify-log, verify-ystar, report, health[/dim]")
    return

    d = diagnose_skill(skill_hash, context=ctx or None)

    if not d.get("found"):
        console.print(f"[red]未找到 skill：{skill_hash}[/red]")
        return

    verdict_color = {
        "RECOMMENDED": "green", "ACCEPTABLE": "cyan",
        "WATCH": "yellow", "NOT_RECOMMENDED": "red"
    }.get(d["verdict"], "white")

    lo, hi = d.get("violation_rate_ci", [0, 1])
    console.print()
    console.print(f"[bold]{d['name']}[/bold] v{d['version']}  ({d['publisher']})")
    console.print(f"  verdict:  [{verdict_color}]{d['verdict']}[/{verdict_color}]")
    console.print(f"  K 指数:   {d['k_index']:+.4f}")
    console.print(f"  安全增益: {d['safety_gain']:+.4f}")
    console.print(f"  能力增益: {d['capability_gain']:+.4f}")
    console.print(f"  违规率:   {d['violation_rate']:.3f}  95%CI [{lo:.3f}, {hi:.3f}]")
    console.print(f"  不确定性: {d['uncertainty']:.4f}")
    console.print(f"  观测:     {d['total_ops']} 次操作 / {d['observation_days']} 天")
    if d.get("reason"):
        console.print(f"  理由：{d['reason']}")
    if d.get("caution"):
        console.print(f"  [yellow]注意：{d['caution']}[/yellow]")
    console.print()



# ── Ledger Sync Commands ────────────────────────────────────────────────────

@main.group()
def sync():
    """Optional ledger sync to a remote endpoint (half-local mode)"""
    pass


@sync.command()
def push():
    """Push unsynced CIEU records to configured endpoint"""
    from k9log.ledger_sync import push_pending, SyncResult
    cfg_check = __import__("k9log.ledger_sync", fromlist=["_load_sync_config"])._load_sync_config()
    if not cfg_check.get("enabled", False):
        console.print("[yellow]Sync is disabled. Enable it first:[/yellow]")
        console.print("  k9log sync enable --endpoint https://your-server/api/ingest")
        return
    console.print("[cyan]Pushing pending records...[/cyan]")
    result = push_pending()
    if result.skipped_reason:
        console.print(f"[yellow]Skipped: {result.skipped_reason}[/yellow]")
        return
    if result.pushed_records > 0:
        console.print(f"[green]Pushed {result.pushed_records} records in {result.pushed_batches} batches[/green]")
        console.print(f"  Last synced seq: {result.last_synced_seq}")
    else:
        console.print("[green]No new records to sync[/green]")
    if result.failed_batches > 0:
        console.print(f"[red]{result.failed_batches} batches failed[/red]")
        if result.queued_to_retry > 0:
            console.print(f"  {result.queued_to_retry} records queued to retry (run: k9log sync retry)")


@sync.command()
def status():
    """Show sync cursor and pending record count"""
    from k9log.ledger_sync import sync_status
    s = sync_status()
    console.print("\n[cyan]Ledger Sync Status[/cyan]\n")
    if s["enabled"]:
        console.print(f"[green]Status: ENABLED[/green]")
        console.print(f"  Endpoint:       {s['endpoint']}")
        console.print(f"  Mode:           {'deviations only' if s['on_deviation_only'] else 'all records'}")
        console.print(f"  Batch size:     {s['batch_size']}")
    else:
        console.print("[yellow]Status: DISABLED[/yellow]")
        console.print("  Run: k9log sync enable --endpoint <url>")
    console.print(f"\n  Last synced seq: {s['last_synced_seq']}")
    console.print(f"  Pending records: {s['pending_records']}")
    if s["retry_queue_size"] > 0:
        console.print(f"  [yellow]Retry queue:     {s['retry_queue_size']} records[/yellow]")
    console.print(f"\n  Cursor file:    {s['cursor_path']}")


@sync.command()
@click.option("--endpoint", required=True, help="Remote ingest endpoint URL")
@click.option("--api-key", default="", help="API key (sent as Bearer token)")
@click.option("--deviation-only", is_flag=True, help="Only sync violation records")
@click.option("--batch-size", default=100, type=int, help="Records per HTTP request")
def enable(endpoint, api_key, deviation_only, batch_size):
    """Enable sync and configure endpoint"""
    from k9log.alerting import _load_config, _save_config
    cfg = _load_config()
    cfg["sync"] = {
        "enabled":            True,
        "endpoint":           endpoint,
        "api_key":            api_key,
        "batch_size":         batch_size,
        "on_deviation_only":  deviation_only,
        "retry_on_failure":   True,
        "cursor_path":        "",
    }
    _save_config(cfg)
    console.print(f"[green]Sync enabled → {endpoint}[/green]")
    mode = "deviations only" if deviation_only else "all records"
    console.print(f"  Mode: {mode} | Batch: {batch_size}")
    console.print("  Run: k9log sync push   to push now")


@sync.command()
def disable():
    """Disable sync (keeps cursor and retry queue intact)"""
    from k9log.alerting import _load_config, _save_config
    cfg = _load_config()
    if "sync" not in cfg:
        cfg["sync"] = {}
    cfg["sync"]["enabled"] = False
    _save_config(cfg)
    console.print("[yellow]Sync disabled[/yellow]")


@sync.command()
def reset():
    """Reset sync cursor — next push will re-send all records"""
    from k9log.ledger_sync import reset_cursor
    reset_cursor()
    console.print("[yellow]Cursor reset. Next push will re-send all records.[/yellow]")


@sync.command()
def retry():
    """Flush the retry queue (re-attempt failed batches)"""
    from k9log.ledger_sync import flush_retry
    from k9log.ledger_sync import _RETRY_PATH
    if not _RETRY_PATH.exists():
        console.print("[green]Retry queue is empty[/green]")
        return
    console.print("[cyan]Flushing retry queue...[/cyan]")
    result = flush_retry()
    if result.pushed_records > 0:
        console.print(f"[green]Re-sent {result.pushed_records} records[/green]")
    if result.failed_batches > 0:
        console.print(f"[red]{result.failed_batches} batches still failing[/red]")



@main.command("audit")
@click.argument("path", default=".", required=False)
@click.option("--checks", default="staging,secrets,imports,scope,constraints",
              help="Comma-separated checks: staging,secrets,imports,scope,constraints")
@click.option("--output", default=None, help="Output file (.html or .json)")
@click.option("--verbose", is_flag=True, default=False, help="Include LOW severity findings")
def audit_cmd(path, checks, output, verbose):
    """Static audit of an AI-written codebase — no execution required.

    \b
    Examples:
      k9log audit ./my-project
      k9log audit ./my-project --checks staging,secrets
      k9log audit ./my-project --output report.html
      k9log audit ./my-project --verbose
    """
    from k9log.auditor import run_audit, DEFAULT_CHECKS
    from rich.panel import Panel
    from pathlib import Path

    check_list = [c.strip() for c in checks.split(",") if c.strip()]

    console.print(Panel.fit(
        f"[bold cyan]K9 Post-hoc Codebase Audit[/bold cyan]\n"
        f"[dim]{Path(path).resolve()}[/dim]",
        border_style="cyan"
    ))
    console.print(f"[dim]Checks: {', '.join(check_list)}[/dim]\n")

    try:
        findings = run_audit(path, checks=check_list, output=output, verbose=verbose)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return

    if not findings:
        console.print("[green]✓ No findings — codebase looks clean[/green]")
        if output:
            console.print(f"[dim]Report saved: {output}[/dim]")
        return

    # Count by severity
    from collections import Counter
    sev_counts = Counter(f.severity for f in findings)

    console.print(
        f"  [red]{sev_counts.get('HIGH', 0)} HIGH[/red]  "
        f"[yellow]{sev_counts.get('MEDIUM', 0)} MEDIUM[/yellow]  "
        f"[cyan]{sev_counts.get('LOW', 0)} LOW[/cyan]\n"
    )

    # Display findings
    for f in findings:
        sev_color = "red" if f.severity == "HIGH" else "yellow" if f.severity == "MEDIUM" else "cyan"
        loc = f.file + (f":{f.line}" if f.line else "")
        console.print(f"  [{sev_color}][{f.severity}][/{sev_color}] [bold]{f.title}[/bold]")
        console.print(f"       [dim]{f.detail}[/dim]")
        console.print(f"       [dim]{loc}[/dim]")
        if f.command:
            console.print(f"       [yellow]→ {f.command}[/yellow]")
        console.print()

    if output:
        console.print(f"[green]Report saved: {output}[/green]")
    else:
        console.print(f"[dim]Tip: add --output report.html for a full HTML report[/dim]")


if __name__ == '__main__':
    main()

