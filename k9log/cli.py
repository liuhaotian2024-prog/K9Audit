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
@click.version_option(version='0.1.0')
def main():
    """K9log - Engineering-grade Causal Audit"""
    pass

@main.command()
def init():
    """Interactive setup wizard"""
    from k9log.wizard import run_wizard
    run_wizard()

@main.command()
def stats():
    """Show statistics"""
    from k9log.verifier import LogVerifier
    log_file = Path.home() / '.k9log' / 'logs' / 'k9log.cieu.jsonl'
    if not log_file.exists():
        console.print('[yellow]No logs found[/yellow]')
        return
    verifier = LogVerifier(log_file)
    total = len(verifier.records)
    violations = sum(1 for r in verifier.records if not r.get('R_t+1', {}).get('passed', True))
    passed = total - violations
    console.print('\n[cyan]K9log Statistics[/cyan]\n')
    console.print(f'[green]Total records:[/green] {total}')
    console.print(f'[green]Passed:[/green] {passed}')
    console.print(f'[red]Violations:[/red] {violations}')
    if total > 0:
        console.print(f'[yellow]Violation rate:[/yellow] {violations/total*100:.1f}%')
    if violations > 0:
        violation_types = {}
        for r in verifier.records:
            for v in r.get('R_t+1', {}).get('violations', []):
                vtype = v.get('type', 'unknown')
                violation_types[vtype] = violation_types.get(vtype, 0) + 1
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
@click.option('--step', type=int, required=True, help='Incident step number')
@click.option('--export', is_flag=True, help='Export DAG to JSON')
def causal(step, export):
    """Analyze causal chain and identify root causes"""
    from k9log.causal_analyzer import CausalChainAnalyzer
    log_file = Path.home() / '.k9log' / 'logs' / 'k9log.cieu.jsonl'
    if not log_file.exists():
        console.print('[yellow]No logs found[/yellow]')
        return
    analyzer = CausalChainAnalyzer(log_file)
    console.print('[cyan]Building causal DAG...[/cyan]')
    dag = analyzer.build_causal_dag()
    console.print(f"[green]DAG built: {dag['metadata']['total_nodes']} nodes, {dag['metadata']['total_edges']} edges[/green]\n")
    analyzer.visualize_causal_chain(step)
    if export:
        analyzer.export_dag()

@main.command()
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

@main.command()
def taint():
    """Analyze taint propagation and detect violations"""
    from k9log.taint import analyze_taint
    log_file = Path.home() / '.k9log' / 'logs' / 'k9log.cieu.jsonl'
    if not log_file.exists():
        console.print('[yellow]No logs found[/yellow]')
        return
    console.print('[cyan]Analyzing taint propagation...[/cyan]\n')
    analyze_taint(log_file)

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
    console.print(f"[green]Y* verification complete[/green]")
    console.print(f"   Total unique Y* versions: {result['total_versions']}\n")
    if result['versions']:
        table = Table(show_header=True)
        table.add_column("Skill")
        table.add_column("Hash")
        table.add_column("Source")
        table.add_column("Count")
        for v in result['versions']:
            table.add_row(
                v['skill'],
                v['hash'][:16] + '...' if v['hash'] != 'none' else 'none',
                v['source'] or 'none',
                str(v['count'])
            )
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
    for record in verifier.records:
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

@main.group()
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
@main.group()
def fuse():
    """Circuit breaker (FUSE) management"""
    pass


@fuse.command()
def status():
    """Show current fuse state"""
    from k9log.fuse import load_state, STATE_PATH
    state = load_state()
    console.print('\n[cyan]FUSE Status[/cyan]\n')
    if state.get('active'):
        console.print('[red bold]Status: ACTIVE (agent halted)[/red bold]')
    elif state.get('armed') is False:
        console.print('[yellow]Status: DISARMED[/yellow]')
    else:
        console.print('[green]Status: ARMED (ready, not triggered)[/green]')
    if state.get('active'):
        console.print(f"  Agent ID   : {state.get('agent_id', '-')}")
        console.print(f"  Session ID : {state.get('session_id', '-')}")
        console.print(f"  Severity   : {state.get('severity', '-')}")
        console.print(f"  Scope      : {state.get('scope', '-')}")
        console.print(f"  Mode       : {state.get('mode', '-')}")
        console.print(f"  Reason     : {state.get('reason', '-')}")
        console.print(f"  Types      : {state.get('trigger_types', [])}")
        console.print(f"  Triggered  : {state.get('ts', '-')}")
        console.print(f"\n  To resume: [bold]k9log fuse disarm[/bold]")
    if not STATE_PATH.exists():
        console.print('\n  [dim](No state file yet - fuse has never fired)[/dim]')


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
    from k9log.fuse import arm as _arm
    _arm()
    console.print('[green]FUSE armed. Will trigger on next qualifying violation.[/green]')


# --- Policy Commands ---
@main.group()
def policy():
    """Policy Pack management"""
    pass


@policy.command()
def status():
    """Show current active policy status"""
    from k9log.policy_pack import get_active_policy, policy_hash, POLICY_PATH
    pol = get_active_policy()
    console.print('\n[cyan]Policy Pack Status[/cyan]\n')
    if pol is None:
        console.print('[yellow]No policy loaded.[/yellow]')
        console.print('  Run: k9log policy load --path <file>')
        console.print('  Using built-in defaults.')
        return
    h = policy_hash(pol)
    console.print(f'[green]Policy loaded[/green]')
    console.print(f'  ID      : {pol.policy_id}')
    console.print(f'  Version : {pol.version}')
    console.print(f'  Created : {pol.created_at}')
    console.print(f'  Hash    : {h}')
    console.print(f'  File    : {POLICY_PATH}')
    fuse_enabled = pol.fuse.get('enabled', False)
    console.print(f'  Fuse    : {"[red]ENABLED[/red]" if fuse_enabled else "[dim]disabled[/dim]"}')


@policy.command()
@click.option('--path', required=True, help='Path to policy JSON file')
@click.option('--sig', default=None, help='Path to .sig file for HMAC verification')
def load(path, sig):
    """Load a policy file as the active policy"""
    from k9log.policy_pack import (
        load_policy, save_active_policy, policy_hash, verify_policy_signature
    )
    from k9log.decision import reset_decision_engine
    # Signature check
    if sig:
        ok = verify_policy_signature(path, sig)
        if not ok:
            console.print('[red]Signature verification FAILED. Policy not loaded.[/red]')
            # Write K9_INTERNAL audit record
            try:
                from k9log.logger import get_logger
                get_logger().write_cieu({
                    'event_type': 'K9_INTERNAL',
                    'U_t': {'skill': 'k9log.policy', 'action': 'LOAD_REJECTED'},
                    'X_t': {},
                    'Y_star_t': {},
                    'Y_t+1': {},
                    'R_t+1': {
                        'passed': True,
                        'violations': [],
                        'overall_severity': 0.0,
                        'message': f'Policy signature verification failed: {path}',
                    },
                })
            except Exception:
                pass
            return
    pol = load_policy(path)
    save_active_policy(pol)
    reset_decision_engine()
    h = policy_hash(pol)
    console.print(f'[green]Policy loaded: {pol.policy_id} v{pol.version}[/green]')
    console.print(f'  Hash: {h}')


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


@main.command()
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


@main.group()
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



@main.group()
def grants():
    """Federated grant library management"""
    pass

@grants.command("import")
@click.argument("source")
def grants_import(source):
    """Import a grant from URL or local file path"""
    from k9log.federated import import_grant
    import_grant(source)

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
    from k9log.federated import list_grants
    list_grants()

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

@main.command("learn")
def learn_cmd():
    """Run causal metalearning — suggest grants from incident history"""
    from k9log.metalearning import learn
    learn()


@main.command("health")
@click.option("--log", default=None, help="CIEU log path (default: ~/.k9log/logs/k9log.cieu.jsonl)")
def health_cmd(log):
    """CIEU-driven system health report"""
    import json, os
    from pathlib import Path
    from rich.panel import Panel

    log_path = log or str(Path.home() / ".k9log" / "logs" / "k9log.cieu.jsonl")
    if not os.path.exists(log_path):
        console.print("[red]CIEU log not found: " + log_path + "[/red]")
        return

    records = [json.loads(l) for l in open(log_path, encoding="utf-8-sig")]
    console.print(Panel.fit("[bold cyan]K9log Health Report[/bold cyan]\n[dim]" + log_path + "[/dim]", border_style="cyan"))

    # 1. Hash chain
    from k9log.verifier import LogVerifier
    integrity = LogVerifier(log_path).verify_integrity()
    chain_ok = integrity["passed"]
    chain_tag = "[green]OK[/green]" if chain_ok else "[red]BROKEN[/red]"
    console.print("\n[bold]Hash Chain[/bold]  " + chain_tag + "  records=" + str(integrity.get("total_records", 0)))
    if not chain_ok:
        console.print("  [red]断点: Step#" + str(integrity.get("break_point")) + " - " + str(integrity.get("message")) + "[/red]")

    # 2. Constraint coverage
    from collections import Counter
    skill_total = Counter()
    skill_covered = Counter()
    violation_types = Counter()
    violations_total = 0
    for r in records:
        skill = r.get("U_t", {}).get("skill", "?")
        skill_total[skill] += 1
        if r.get("Y_star_t", {}).get("constraints"):
            skill_covered[skill] += 1
        for v in r.get("R_t+1", {}).get("violations", []):
            violation_types[v.get("type", "?")] += 1
            violations_total += 1

    total = sum(skill_total.values())
    covered = sum(skill_covered.values())
    pct = int(100 * covered / total) if total else 0
    console.print("\n[bold]Constraint Coverage[/bold]  " + str(covered) + "/" + str(total) + " (" + str(pct) + "%)")

    tbl = Table(show_header=True, header_style="bold")
    tbl.add_column("Skill")
    tbl.add_column("Calls", justify="right")
    tbl.add_column("Constrained", justify="right")
    tbl.add_column("Status")
    for skill in sorted(skill_total.keys()):
        c = skill_covered[skill]
        t = skill_total[skill]
        if c == t:
            status = "[green]OK[/green]"
        elif c > 0:
            status = "[yellow]PARTIAL[/yellow]"
        else:
            status = "[red]UNCOVERED[/red]"
        tbl.add_row(skill, str(t), str(c), status)
    console.print(tbl)

    # 3. Violations
    console.print("\n[bold]Violations[/bold]  total=" + str(violations_total))
    for vt, cnt in violation_types.most_common():
        console.print("  " + vt + ": " + str(cnt))

    # 3b. Taint analysis
    try:
        from k9log.taint import TaintTracker
        tracker = TaintTracker(log_path)
        taint_result = tracker.analyze_taint_propagation()
        tv = taint_result.get("violations", [])
        tr = taint_result.get("taint_rate", 0)
        ts = taint_result.get("total_tainted_steps", 0)
        tm = len(taint_result.get("taint_map", {}))
        console.print("\n[bold]Taint Analysis[/bold]  tainted_steps=" + str(ts) + "/" + str(tm) + " (" + str(int(100 * tr)) + "%)  violations=" + str(len(tv)))
        if tv:
            from collections import Counter
            by_skill = Counter(v["skill"] for v in tv)
            for skill, cnt in by_skill.most_common():
                console.print("  " + skill + ": " + str(cnt) + " taint violation(s)")
        else:
            console.print("  [green]no taint violations[/green]")
    except Exception as e:
        console.print("\n[bold]Taint Analysis[/bold]  [yellow]unavailable: " + str(e) + "[/yellow]")

    # 4. Metalearning
    from k9log.metalearning import CausalMetaLearner
    learner = CausalMetaLearner(log_path)
    incidents = learner._extract_incidents()
    candidates = learner._enumerate_candidates(incidents)
    cover, _ = learner._find_minimum_cover(incidents, candidates)
    console.print("\n[bold]Metalearning[/bold]  incidents=" + str(len(incidents)) + "  candidates=" + str(len(candidates)) + "  cover=" + str(len(cover)))
    for mc in cover:
        r = mc["rule"]
        console.print("  [" + str(r.get("rule_type", "?")) + "] " + r["id"] + "  cut=Step#" + str(mc["cut_point"]) + "  fp=" + str(mc["false_positives"]))

    # 5. Learned rules
    lr_path = Path.home() / ".k9log" / "learned_rules.json"
    if lr_path.exists():
        lr = json.loads(lr_path.read_text(encoding="utf-8"))
        console.print("\n[bold]Learned Rules[/bold]  " + str(len(lr["rules"])) + " rules  " + str(len(lr["sessions"])) + " sessions")
        for rid, rule in lr["rules"].items():
            console.print("  [" + str(rule.get("rule_type", "?")) + "] " + rid + "  learned=" + str(rule.get("learned_at", "?"))[:19])
    else:
        console.print("\n[bold]Learned Rules[/bold]  [yellow]not found[/yellow]")

    # 6. Grants
    grants_dir = Path.home() / ".k9log" / "grants"
    active_g   = list(grants_dir.glob("*.json"))
    suggested  = list((grants_dir / "suggested").glob("*.json")) if (grants_dir / "suggested").exists() else []
    deprecated = list((grants_dir / "deprecated").glob("*.json")) if (grants_dir / "deprecated").exists() else []
    console.print("\n[bold]Grants[/bold]  active=" + str(len(active_g)) + "  suggested=" + str(len(suggested)) + "  deprecated=" + str(len(deprecated)))

    # 7. Fuse
    fuse_state = Path.home() / ".k9log" / "fuse" / "state.json"
    if fuse_state.exists():
        fs = json.loads(fuse_state.read_text(encoding="utf-8"))
        a = fs.get("active")
        color = "red" if a else "green"
        console.print("\n[bold]Fuse[/bold]  [" + color + "]active=" + str(a) + "[/" + color + "]  severity=" + str(fs.get("severity")))
    else:
        console.print("\n[bold]Fuse[/bold]  [dim]no state[/dim]")

    console.print()




@main.group()
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Merged from openclaw branch: fuse management, policy pack, html report
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@main.group()
def fuse():
    """Circuit breaker (FUSE) management"""
    pass


@fuse.command()
def status():
    """Show current fuse state"""
    from k9log.fuse import load_state, STATE_PATH
    state = load_state()
    console.print('\n[cyan]FUSE Status[/cyan]\n')
    if state.get('active'):
        console.print('[red bold]Status: ACTIVE (agent halted)[/red bold]')
    elif state.get('armed') is False:
        console.print('[yellow]Status: DISARMED[/yellow]')
    else:
        console.print('[green]Status: ARMED (ready, not triggered)[/green]')
    if state.get('active'):
        console.print(f"  Agent ID   : {state.get('agent_id', '-')}")
        console.print(f"  Session ID : {state.get('session_id', '-')}")
        console.print(f"  Severity   : {state.get('severity', '-')}")
        console.print(f"  Scope      : {state.get('scope', '-')}")
        console.print(f"  Mode       : {state.get('mode', '-')}")
        console.print(f"  Reason     : {state.get('reason', '-')}")
        console.print(f"  Types      : {state.get('trigger_types', [])}")
        console.print(f"  Triggered  : {state.get('ts', '-')}")
        console.print(f"\n  To resume: [bold]k9log fuse disarm[/bold]")
    if not STATE_PATH.exists():
        console.print('\n  [dim](No state file yet - fuse has never fired)[/dim]')


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
    from k9log.fuse import arm as _arm
    _arm()
    console.print('[green]FUSE armed. Will trigger on next qualifying violation.[/green]')


@main.group()
def policy():
    """Policy Pack management"""
    pass


@policy.command()
def status():
    """Show current active policy status"""
    from k9log.policy_pack import get_active_policy, policy_hash, POLICY_PATH
    pol = get_active_policy()
    console.print('\n[cyan]Policy Pack Status[/cyan]\n')
    if pol is None:
        console.print('[yellow]No policy loaded.[/yellow]')
        console.print('  Run: k9log policy load --path <file>')
        console.print('  Using built-in defaults.')
        return
    h = policy_hash(pol)
    console.print('[green]Policy loaded[/green]')
    console.print(f'  ID      : {pol.policy_id}')
    console.print(f'  Version : {pol.version}')
    console.print(f'  Created : {pol.created_at}')
    console.print(f'  Hash    : {h}')
    console.print(f'  File    : {POLICY_PATH}')
    fuse_enabled = pol.fuse.get('enabled', False)
    console.print(f'  Fuse    : {"[red]ENABLED[/red]" if fuse_enabled else "[dim]disabled[/dim]"}')


@policy.command()
@click.option('--path', required=True, help='Path to policy JSON file')
@click.option('--sig', default=None, help='Path to .sig file for HMAC verification')
def load(path, sig):
    """Load a policy file as the active policy"""
    from k9log.policy_pack import (
        load_policy, save_active_policy, policy_hash, verify_policy_signature
    )
    from k9log.decision import reset_decision_engine
    if sig:
        ok = verify_policy_signature(path, sig)
        if not ok:
            console.print('[red]Signature verification FAILED. Policy not loaded.[/red]')
            return
    pol = load_policy(path)
    save_active_policy(pol)
    reset_decision_engine()
    h = policy_hash(pol)
    console.print(f'[green]Policy loaded: {pol.policy_id} v{pol.version}[/green]')
    console.print(f'  Hash: {h}')


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



# ── 联邦学习命令组 ──────────────────────────────────────────────────────────

@main.group()
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
    from k9log.wizard import federated_join
    federated_join()


@federated.command("leave")
def federated_leave_cmd():
    """退出联邦学习计划。"""
    from k9log.wizard import federated_leave
    federated_leave()


@federated.command("status")
def federated_status_cmd():
    """查看联邦学习参与状态。"""
    from k9log.wizard import federated_status
    federated_status()


# ── Skill 推荐命令组 ────────────────────────────────────────────────────────

@main.group()
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
    from k9log.skill_recommender import SkillRecommender
    log_file = Path.home() / ".k9log" / "logs" / "k9log.cieu.jsonl"
    engine = SkillRecommender(log_file)

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
    from k9log.skill_recommender import SkillRecommender
    log_file = Path.home() / ".k9log" / "logs" / "k9log.cieu.jsonl"
    ranking  = SkillRecommender(log_file).k_ranking(top)

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
    from k9log.skill_recommender import diagnose_skill
    ctx = {}
    if action:     ctx["action_class"] = action.upper()
    if agent_type: ctx["agent_type"]   = agent_type.lower()

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

if __name__ == '__main__':
    main()

