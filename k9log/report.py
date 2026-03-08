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
K9log Report - Generate shareable HTML audit report

Usage:
    k9log report                    # Generate report from current logs
    k9log report --output=report.html  # Specify output file
"""
import logging
import json
import html
from pathlib import Path
from datetime import datetime


def generate_report(log_file=None, output_file=None, output_path=None):
    if output_file is None and output_path is not None:
        output_file = output_path
    """Generate an HTML audit report from K9log data."""
    if log_file is None:
        log_file = Path.home() / '.k9log' / 'logs' / 'k9log.cieu.jsonl'
    if output_file is None:
        output_file = Path('k9log_report.html')

    log_file = Path(log_file)
    output_file = Path(output_file)

    if not log_file.exists():
        logging.getLogger("k9log").warning("k9log: no log file found: %s", log_file)
        return None

    # -- Streaming helper -------------------------------------------------------
    def _stream(path):
        with open(path, 'r', encoding='utf-8') as fh:
            for ln in fh:
                ln = ln.strip()
                if ln:
                    try:
                        yield json.loads(ln)
                    except json.JSONDecodeError:
                        continue

    # -- Pass 1: streaming stats (O(1) memory) ---------------------------------
    total           = 0
    violation_count = 0
    risk_counts     = {'LOW': 0, 'MEDIUM': 0, 'HIGH': 0, 'CRITICAL': 0}
    skill_stats     = {}
    violation_types = {}
    agents          = {}

    for r in _stream(log_file):
        if 'X_t' not in r:
            continue
        total += 1
        passed = r.get('R_t+1', {}).get('passed', True)
        if not passed:
            violation_count += 1
            level = r.get('R_t+1', {}).get('risk_level', 'LOW')
            if level in risk_counts:
                risk_counts[level] += 1
            for v in r.get('R_t+1', {}).get('violations', []):
                vtype = v.get('type', 'unknown')
                violation_types[vtype] = violation_types.get(vtype, 0) + 1

        skill = r.get('U_t', {}).get('skill', 'unknown')
        if skill not in skill_stats:
            skill_stats[skill] = {'total': 0, 'violations': 0}
        skill_stats[skill]['total'] += 1
        if not passed:
            skill_stats[skill]['violations'] += 1

        _raw_name = r.get('X_t', {}).get('agent_name', 'unknown')
        if isinstance(_raw_name, dict):
            name = _raw_name.get('agent_name') or _raw_name.get('agent_id') or 'unknown'
        else:
            name = str(_raw_name) if _raw_name is not None else 'unknown'
        if name not in agents:
            agents[name] = {'total': 0, 'violations': 0}
        agents[name]['total'] += 1
        if not passed:
            agents[name]['violations'] += 1

    passed_count   = total - violation_count
    violation_rate = (violation_count / total * 100) if total > 0 else 0

    # -- Pass 2: last 20 events for timeline (streaming) ----------------------
    from collections import deque
    _tl = deque(maxlen=20)
    for r in _stream(log_file):
        if 'X_t' in r:
            _tl.append(r)
    timeline_events = list(_tl)

    # -- Chain integrity via verifier (authoritative) -------------------------
    from k9log.verifier import LogVerifier
    integrity_result = LogVerifier(log_file).verify_integrity()
    chain_ok = integrity_result.get('passed', False)


    # Generate HTML
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>K9log Audit Report</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {{
    --bg-primary: #0a0e17;
    --bg-secondary: #111827;
    --bg-card: #1a2235;
    --bg-card-hover: #1f2a3f;
    --border: #2a3650;
    --text-primary: #e8ecf4;
    --text-secondary: #8892a6;
    --text-muted: #5a6478;
    --accent-green: #22c55e;
    --accent-green-dim: rgba(34, 197, 94, 0.15);
    --accent-red: #ef4444;
    --accent-red-dim: rgba(239, 68, 68, 0.15);
    --accent-amber: #f59e0b;
    --accent-amber-dim: rgba(245, 158, 11, 0.15);
    --accent-blue: #3b82f6;
    --accent-blue-dim: rgba(59, 130, 246, 0.15);
    --accent-purple: #a855f7;
    --accent-purple-dim: rgba(168, 85, 247, 0.15);
    --accent-cyan: #06b6d4;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    font-family: 'DM Sans', sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    min-height: 100vh;
    line-height: 1.6;
}}

.noise-overlay {{
    position: fixed;
    top: 0; left: 0; width: 100%; height: 100%;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.03'/%3E%3C/svg%3E");
    pointer-events: none;
    z-index: 0;
}}

.container {{
    max-width: 1100px;
    margin: 0 auto;
    padding: 40px 24px;
    position: relative;
    z-index: 1;
}}

/* Header */
.header {{
    text-align: center;
    margin-bottom: 48px;
    position: relative;
}}

.header::before {{
    content: '';
    position: absolute;
    top: -40px; left: 50%; transform: translateX(-50%);
    width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(6, 182, 212, 0.12) 0%, transparent 70%);
    pointer-events: none;
}}

.logo {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 42px;
    font-weight: 700;
    letter-spacing: -1px;
    margin-bottom: 4px;
}}

.logo span {{ color: var(--accent-cyan); }}

.subtitle {{
    font-size: 14px;
    color: var(--text-muted);
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-bottom: 16px;
}}

.timestamp {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--text-muted);
    background: var(--bg-card);
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    border: 1px solid var(--border);
}}

/* Chain status banner */
.chain-status {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 14px 24px;
    border-radius: 12px;
    margin-bottom: 32px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    font-weight: 600;
}}

.chain-ok {{
    background: var(--accent-green-dim);
    border: 1px solid rgba(34, 197, 94, 0.3);
    color: var(--accent-green);
}}

.chain-broken {{
    background: var(--accent-red-dim);
    border: 1px solid rgba(239, 68, 68, 0.3);
    color: var(--accent-red);
}}

/* Stats grid */
.stats-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 32px;
}}

.stat-card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    transition: all 0.2s;
}}

.stat-card:hover {{
    background: var(--bg-card-hover);
    transform: translateY(-2px);
}}

.stat-label {{
    font-size: 12px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 8px;
}}

.stat-value {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 32px;
    font-weight: 700;
    line-height: 1;
}}

.stat-value.green {{ color: var(--accent-green); }}
.stat-value.red {{ color: var(--accent-red); }}
.stat-value.blue {{ color: var(--accent-blue); }}
.stat-value.amber {{ color: var(--accent-amber); }}

.stat-sub {{
    font-size: 12px;
    color: var(--text-secondary);
    margin-top: 6px;
    font-family: 'JetBrains Mono', monospace;
}}

/* Section */
.section {{
    margin-bottom: 32px;
}}

.section-title {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
}}

/* Two column layout */
.two-col {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 32px;
}}

/* Risk bars */
.risk-bar-container {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
}}

.risk-row {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
}}

.risk-row:last-child {{ margin-bottom: 0; }}

.risk-label {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    width: 70px;
    flex-shrink: 0;
}}

.risk-label.critical {{ color: var(--accent-red); }}
.risk-label.high {{ color: #f97316; }}
.risk-label.medium {{ color: var(--accent-amber); }}
.risk-label.low {{ color: var(--accent-green); }}

.risk-bar-track {{
    flex: 1;
    height: 8px;
    background: var(--bg-primary);
    border-radius: 4px;
    overflow: hidden;
}}

.risk-bar-fill {{
    height: 100%;
    border-radius: 4px;
    transition: width 0.6s ease;
}}

.risk-bar-fill.critical {{ background: var(--accent-red); }}
.risk-bar-fill.high {{ background: #f97316; }}
.risk-bar-fill.medium {{ background: var(--accent-amber); }}
.risk-bar-fill.low {{ background: var(--accent-green); }}

.risk-count {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    color: var(--text-secondary);
    width: 30px;
    text-align: right;
    flex-shrink: 0;
}}

/* Table */
.table-card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
}}

table {{
    width: 100%;
    border-collapse: collapse;
}}

th {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 1px;
    text-align: left;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    background: rgba(0,0,0,0.2);
}}

td {{
    padding: 10px 16px;
    font-size: 13px;
    border-bottom: 1px solid rgba(42, 54, 80, 0.5);
    color: var(--text-secondary);
}}

tr:last-child td {{ border-bottom: none; }}

td.mono {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
}}

/* Badges */
.badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 600;
}}

.badge-pass {{
    background: var(--accent-green-dim);
    color: var(--accent-green);
}}

.badge-fail {{
    background: var(--accent-red-dim);
    color: var(--accent-red);
}}

.badge-critical {{
    background: var(--accent-red-dim);
    color: var(--accent-red);
}}

.badge-high {{
    background: rgba(249, 115, 22, 0.15);
    color: #f97316;
}}

.badge-medium {{
    background: var(--accent-amber-dim);
    color: var(--accent-amber);
}}

.badge-low {{
    background: var(--accent-green-dim);
    color: var(--accent-green);
}}

/* Timeline */
.timeline {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
}}

.timeline-item {{
    display: flex;
    gap: 14px;
    padding: 10px 0;
    border-bottom: 1px solid rgba(42, 54, 80, 0.4);
    font-size: 13px;
}}

.timeline-item:last-child {{ border-bottom: none; }}

.timeline-seq {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text-muted);
    min-width: 35px;
}}

.timeline-skill {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--accent-cyan);
    min-width: 140px;
}}

.timeline-status {{ min-width: 60px; }}

.timeline-detail {{
    color: var(--text-muted);
    font-size: 12px;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}}

/* Footer */
.footer {{
    text-align: center;
    padding: 32px 0 16px;
    font-size: 12px;
    color: var(--text-muted);
    border-top: 1px solid var(--border);
    margin-top: 40px;
}}

.footer a {{
    color: var(--accent-cyan);
    text-decoration: none;
}}

/* Responsive */
@media (max-width: 768px) {{
    .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .two-col {{ grid-template-columns: 1fr; }}
    .stat-value {{ font-size: 24px; }}
}}

@media print {{
    body {{ background: #fff; color: #111; }}
    .noise-overlay {{ display: none; }}
    .stat-card, .table-card, .timeline, .risk-bar-container {{
        background: #f8f9fa; border-color: #ddd;
    }}
    .stat-value, .stat-label, td, th {{ color: #111 !important; }}
}}
</style>
</head>
<body>
<div class="noise-overlay"></div>
<div class="container">

<div class="header">
    <div class="logo"><span>K9</span>log</div>
    <div class="subtitle">Causal Audit Report</div>
    <div class="timestamp">Generated {html.escape(now)}</div>
</div>

<div class="chain-status {'chain-ok' if chain_ok else 'chain-broken'}">
    {'&#x2705; Hash Chain Intact &mdash; All ' + str(total) + ' records verified, no tampering detected' if chain_ok else '&#x274C; Hash Chain Broken &mdash; Log integrity compromised, possible tampering'}
</div>

<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-label">Total Events</div>
        <div class="stat-value blue">{total}</div>
        <div class="stat-sub">{len(set(r.get('U_t', {}).get('skill', '') for r in _stream(log_file)))} unique skills</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Passed</div>
        <div class="stat-value green">{passed_count}</div>
        <div class="stat-sub">{100 - violation_rate:.1f}% compliance</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Violations</div>
        <div class="stat-value red">{violation_count}</div>
        <div class="stat-sub">{violation_rate:.1f}% violation rate</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Risk Score</div>
        <div class="stat-value {'red' if risk_counts['CRITICAL'] > 0 else 'amber' if risk_counts['HIGH'] > 0 else 'green'}">{risk_counts['CRITICAL'] * 4 + risk_counts['HIGH'] * 3 + risk_counts['MEDIUM'] * 2 + risk_counts['LOW']}</div>
        <div class="stat-sub">weighted severity index</div>
    </div>
</div>

<div class="two-col">
    <div>
        <div class="section-title">Risk Distribution</div>
        <div class="risk-bar-container">
{_render_risk_bars(risk_counts, violation_count)}
        </div>
    </div>
    <div>
        <div class="section-title">Violation Types</div>
        <div class="table-card">
            <table>
                <tr><th>Type</th><th>Count</th></tr>
{_render_violation_types(violation_types)}
            </table>
        </div>
    </div>
</div>

<div class="section">
    <div class="section-title">Skill Breakdown</div>
    <div class="table-card">
        <table>
            <tr><th>Skill</th><th>Total</th><th>Violations</th><th>Rate</th><th>Status</th></tr>
{_render_skill_table(skill_stats)}
        </table>
    </div>
</div>

<div class="section">
    <div class="section-title">Agent Overview</div>
    <div class="table-card">
        <table>
            <tr><th>Agent</th><th>Total Ops</th><th>Violations</th><th>Compliance</th></tr>
{_render_agent_table(agents)}
        </table>
    </div>
</div>

<div class="section">
    <div class="section-title">Recent Events Timeline</div>
    <div class="timeline">
{_render_timeline(timeline_events)}
    </div>
</div>

<div class="footer">
    <strong>K9log</strong> &mdash; Engineering-grade Causal Audit for AI Agents<br>
    <a href="https://github.com/liuhaotian2024-prog/k9log-core">github.com/liuhaotian2024-prog/k9log-core</a>
    &nbsp;&bull;&nbsp; AGPL-3.0
</div>

</div>
</body>
</html>"""

    output_file.write_text(report_html, encoding='utf-8')
    return str(output_file)


def _render_risk_bars(risk_counts, total):
    rows = []
    for level in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
        count = risk_counts.get(level, 0)
        pct = (count / total * 100) if total > 0 else 0
        css = level.lower()
        rows.append(f"""            <div class="risk-row">
                <span class="risk-label {css}">{level}</span>
                <div class="risk-bar-track"><div class="risk-bar-fill {css}" style="width:{pct}%"></div></div>
                <span class="risk-count">{count}</span>
            </div>""")
    return '\n'.join(rows)


def _render_violation_types(violation_types):
    if not violation_types:
        return '                <tr><td colspan="2" style="color:var(--text-muted);text-align:center;">No violations</td></tr>'
    rows = []
    for vtype, count in sorted(violation_types.items(), key=lambda x: -x[1]):
        rows.append(f'                <tr><td class="mono">{html.escape(vtype)}</td><td class="mono">{count}</td></tr>')
    return '\n'.join(rows)


def _render_skill_table(skill_stats):
    rows = []
    for skill, s in sorted(skill_stats.items(), key=lambda x: -x[1]['violations']):
        rate = s['violations'] / s['total'] * 100 if s['total'] > 0 else 0
        badge = 'badge-pass' if s['violations'] == 0 else 'badge-fail'
        label = 'CLEAN' if s['violations'] == 0 else 'ISSUES'
        rows.append(f"""            <tr>
                <td class="mono">{html.escape(skill)}</td>
                <td class="mono">{s['total']}</td>
                <td class="mono">{s['violations']}</td>
                <td class="mono">{rate:.1f}%</td>
                <td><span class="badge {badge}">{label}</span></td>
            </tr>""")
    return '\n'.join(rows)


def _render_agent_table(agents):
    rows = []
    for name, s in agents.items():
        compliance = (s['total'] - s['violations']) / s['total'] * 100 if s['total'] > 0 else 100
        rows.append(f"""            <tr>
                <td class="mono">{html.escape(name)}</td>
                <td class="mono">{s['total']}</td>
                <td class="mono">{s['violations']}</td>
                <td class="mono">{compliance:.1f}%</td>
            </tr>""")
    return '\n'.join(rows)


def _render_timeline(events):
    rows = []
    for r in events:
        seq = r.get('_integrity', {}).get('seq', '?')
        skill = r.get('U_t', {}).get('skill', 'unknown')
        passed = r.get('R_t+1', {}).get('passed', True)
        risk = r.get('R_t+1', {}).get('risk_level', 'LOW')
        badge_class = 'badge-pass' if passed else f'badge-{risk.lower()}'
        badge_text = 'PASS' if passed else risk

        # Get a detail string
        params = r.get('U_t', {}).get('params', {})
        detail_parts = []
        for k, v in list(params.items())[:3]:
            if isinstance(v, dict) and v.get('_redacted'):
                detail_parts.append(f"{k}=[redacted]")
            else:
                vs = str(v)
                if len(vs) > 30:
                    vs = vs[:27] + '...'
                detail_parts.append(f"{k}={vs}")
        detail = ', '.join(detail_parts)

        rows.append(f"""        <div class="timeline-item">
            <span class="timeline-seq">#{seq}</span>
            <span class="timeline-skill">{html.escape(skill)}</span>
            <span class="timeline-status"><span class="badge {badge_class}">{badge_text}</span></span>
            <span class="timeline-detail">{html.escape(detail)}</span>
        </div>""")
    return '\n'.join(rows)

