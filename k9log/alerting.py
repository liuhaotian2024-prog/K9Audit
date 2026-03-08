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
K9log Alerting - Smart alert system with dedup, aggregation, and DND
Supports: Telegram, Slack, Discord, Webhook
"""
import json
import time
import hashlib
import threading
import urllib.request
import urllib.error
import atexit
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# --- Config ---

DEFAULT_CONFIG = {
    "enabled": False,
    "channels": {},
    "rules": {
        "min_severity": 0.0,
        "skills": [],
        "violation_types": []
    },
    "dedup": {
        "enabled": True,
        "window_seconds": 300
    },
    "aggregation": {
        "enabled": True,
        "window_seconds": 60,
        "max_batch": 10
    },
    "dnd": {
        "enabled": False,
        "start": "23:00",
        "end": "07:00",
        "timezone_offset_hours": 8
    },
    "fuse": {
        "enabled": False,
        "min_severity": 0.85,
        "violation_types": [
            "blocklist_hit",
            "blocklist_substring",
            "numeric_exceeded",
            "allowlist_miss",
            "enum_violation",
            "type_mismatch",
            "regex_mismatch",
        ],
        "scope": "agent",
        "cooldown_seconds": 600,
        "mode": "TOKEN_BUDGET_FREEZE",
        "budget": {"token_cap": 0, "tool_calls": 0},
        "write_cieu_event": True,
        "reason": "risk threshold exceeded"
    }
}

CONFIG_PATH = Path.home() / '.k9log' / 'alerting.json'
HISTORY_PATH = Path.home() / '.k9log' / 'alert_history.jsonl'


def _load_config():
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8-sig') as f:
                user_cfg = json.load(f)
            cfg = {**DEFAULT_CONFIG, **user_cfg}
            for key in ['rules', 'dedup', 'aggregation', 'dnd', 'channels', 'fuse']:
                if key in user_cfg and isinstance(DEFAULT_CONFIG.get(key), dict):
                    cfg[key] = {**DEFAULT_CONFIG[key], **user_cfg[key]}
            return cfg
        except Exception as e:
            print(f"[k9log] Warning: Failed to load alerting config: {e}")
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG


def _save_config(config):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# --- Dedup Engine ---

class DedupEngine:
    def __init__(self, window_seconds=300):
        self.window = window_seconds
        self.seen = {}
        self.lock = threading.Lock()

    def _fingerprint(self, record):
        skill = record.get('U_t', {}).get('skill', '')
        violations = record.get('R_t+1', {}).get('violations', [])
        v_types = sorted(v.get('type', '') for v in violations)
        raw = f"{skill}|{'|'.join(v_types)}"
        return hashlib.md5(raw.encode()).hexdigest()

    def should_send(self, record):
        with self.lock:
            fp = self._fingerprint(record)
            now = time.time()
            expired = [k for k, ts in self.seen.items() if now - ts > self.window]
            for k in expired:
                del self.seen[k]
            if fp in self.seen:
                return False
            self.seen[fp] = now
            return True


# --- Aggregation Engine ---

class AggregationEngine:
    def __init__(self, window_seconds=60, max_batch=10):
        self.window = window_seconds
        self.max_batch = max_batch
        self.buffer = []
        self.lock = threading.Lock()
        self.timer = None
        self._send_fn = None

    def add(self, alert_payload, send_fn):
        with self.lock:
            self._send_fn = send_fn
            self.buffer.append(alert_payload)
            if len(self.buffer) >= self.max_batch:
                self._flush(send_fn)
                return
            if len(self.buffer) == 1:
                self.timer = threading.Timer(self.window, self._flush_from_timer, args=[send_fn])
                self.timer.daemon = True
                self.timer.start()

    def _flush_from_timer(self, send_fn):
        with self.lock:
            self._flush(send_fn)

    def _flush(self, send_fn):
        if not self.buffer:
            return
        batch = self.buffer[:self.max_batch]
        self.buffer = self.buffer[self.max_batch:]
        if self.timer:
            self.timer.cancel()
            self.timer = None
        send_fn(batch)

    def flush_on_exit(self):
        """Flush remaining buffer on program exit"""
        with self.lock:
            if self.buffer and self._send_fn:
                self._flush(self._send_fn)


# --- DND (Do Not Disturb) ---

def _is_dnd_active(dnd_config):
    if not dnd_config.get('enabled', False):
        return False
    offset = dnd_config.get('timezone_offset_hours', 0)
    now = datetime.now(timezone.utc) + timedelta(hours=offset)
    current_time = now.strftime('%H:%M')
    start = dnd_config.get('start', '23:00')
    end = dnd_config.get('end', '07:00')
    if start > end:
        return current_time >= start or current_time < end
    else:
        return start <= current_time < end


# --- Channel Senders ---

def _send_telegram(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[k9log] Telegram send failed: {e}")
        return False


def _send_slack(webhook_url, message):
    payload = json.dumps({"text": message}).encode('utf-8')
    req = urllib.request.Request(webhook_url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[k9log] Slack send failed: {e}")
        return False


def _send_discord(webhook_url, message):
    payload = json.dumps({"content": message}).encode('utf-8')
    req = urllib.request.Request(webhook_url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)
    except Exception as e:
        print(f"[k9log] Discord send failed: {e}")
        return False


def _send_webhook(url, data):
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        print(f"[k9log] Webhook send failed: {e}")
        return False


# --- Message Formatting ---

def _format_single_alert(record):
    import datetime as _dt
    x  = record.get("X_t", {})
    u  = record.get("U_t", {})
    ys = record.get("Y_star_t", {})
    y  = record.get("Y_t+1", {})
    r  = record.get("R_t+1", {})
    seq      = record.get("_seq", record.get("_integrity", {}).get("seq", "?"))
    severity = r.get("overall_severity", 0.0)
    sev_label = "HIGH" if severity >= 0.8 else ("MEDIUM" if severity >= 0.5 else "LOW")
    violations = r.get("violations", [])
    if violations:
        v = violations[0]
        vtype   = v.get("type", "unknown")
        matched = v.get("matched", v.get("actual", ""))
        field   = v.get("field", "")
        finding = f"{vtype}  matched: {matched!r}" + (f"  (field: {field})" if field else "")
    elif r.get("execution_error"):
        finding = f"execution_error: {str(r['execution_error'])[:80]}"
    else:
        finding = "deviation recorded"
    constraints  = ys.get("constraints", {})
    intent_source = ys.get("y_star_meta", {}).get("source", "inline")
    intent_lines  = [f"    {k}: {v}" for k, v in constraints.items()]
    intent_str    = "\n".join(intent_lines) if intent_lines else "    (no constraints defined)"
    params = u.get("params", {})
    param_lines = []
    for i, (k, v) in enumerate(params.items()):
        if i >= 2: param_lines.append("    ..."); break
        val_str = str(v)[:120] + ("..." if len(str(v)) > 120 else "")
        param_lines.append(f"    {k}: {val_str}")
    params_str = "\n".join(param_lines) if param_lines else "    (no params)"
    ts_raw = x.get("datetime") or x.get("ts")
    if isinstance(ts_raw, float):
        ts = _dt.datetime.fromtimestamp(ts_raw, tz=_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        ts = str(ts_raw) if ts_raw else "unknown"
    parts = [
        f"[K9 Audit] Deviation Detected  seq={seq}  severity={sev_label} ({severity:.1f})",
        "",
        "─── X_t  Context ──────────────────────",
        f"  agent:   {x.get('agent_name', x.get('agent_id', 'unknown'))}",
        f"  time:    {ts}",
        f"  action:  {x.get('action_class', 'unknown')}",
        f"  session: {x.get('session_id', 'unknown')}",
        "",
        "─── U_t  What happened ────────────────",
        f"  skill:   {u.get('skill', 'unknown')}",
        params_str,
        "",
        "─── Y*_t  What should have happened ───",
        f"  source:  {intent_source}",
        intent_str,
        "",
        "─── Y_t+1  Outcome ─────────────────────",
        f"  status:  {y.get('status', 'unknown')}",
        "",
        "─── R_t+1  Assessment ──────────────────",
        f"  passed:  {r.get('passed', True)}",
        f"  finding: {finding}",
        "",
        f"->  k9log trace --step {seq}",
    ]
    return "\n".join(parts)


def _format_batch_alert(alerts):
    count = len(alerts)
    skills = set()
    max_severity = 0
    for a in alerts:
        skills.add(a.get('U_t', {}).get('skill', '?'))
        sev = a.get('R_t+1', {}).get('overall_severity', 0)
        if sev > max_severity:
            max_severity = sev
    skill_list = ', '.join(sorted(skills))
    first_ts = alerts[0].get('timestamp', '')
    last_ts = alerts[-1].get('timestamp', '')
    return (
        f"K9log Alert Batch ({count} violations)\n"
        f"-----------------\n"
        f"Skills: {skill_list}\n"
        f"Max severity: {max_severity:.2f}\n"
        f"Period: {first_ts} ~ {last_ts}\n"
        f"Run: k9log alerts --history"
    )


# --- Alert History ---

def _record_history(alerts, channels_sent, suppressed_reason=None):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    alert_list = alerts if isinstance(alerts, list) else [alerts]
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'alert_count': len(alert_list),
        'channels_sent': channels_sent,
        'suppressed': suppressed_reason,
        'skills': list(set(a.get('U_t', {}).get('skill', '?') for a in alert_list))
    }
    with open(HISTORY_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


# --- Core Alert Manager ---

class AlertManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.config = _load_config()
        self.dedup = DedupEngine(
            self.config.get('dedup', {}).get('window_seconds', 300)
        )
        agg_cfg = self.config.get('aggregation', {})
        self.aggregation = AggregationEngine(
            agg_cfg.get('window_seconds', 60),
            agg_cfg.get('max_batch', 10)
        )
        # Register exit handler to flush pending alerts
        atexit.register(self._flush_on_exit)

    def _flush_on_exit(self):
        """Ensure all buffered alerts are sent before program exits"""
        self.aggregation.flush_on_exit()

    def reload_config(self):
        self.config = _load_config()


        self.dedup = DedupEngine(
            self.config.get('dedup', {}).get('window_seconds', 300)
        )
        agg_cfg = self.config.get('aggregation', {})
        self.aggregation = AggregationEngine(
            agg_cfg.get('window_seconds', 60),
            agg_cfg.get('max_batch', 10)
        )

    def on_violation(self, cieu_record):
        if not self.config.get('enabled', False):
            return
        # Skip fuse-generated records to prevent recursion
        if cieu_record.get('event_type') == 'FUSE':
            return
        if (cieu_record.get('U_t') or {}).get('skill') == 'k9log.fuse':
            return
        if not self._passes_rules(cieu_record):
            _record_history(cieu_record, [], suppressed_reason='rules_filter')
            return
        # NOTE: fuse is now evaluated inline in CIEULogger.write_cieu()
        # to guarantee hash chain integrity. No fuse call needed here.
        if _is_dnd_active(self.config.get('dnd', {})):
            _record_history(cieu_record, [], suppressed_reason='dnd')
            return
        if self.config.get('dedup', {}).get('enabled', True):
            if not self.dedup.should_send(cieu_record):
                _record_history(cieu_record, [], suppressed_reason='dedup')
                return
        if self.config.get('aggregation', {}).get('enabled', True):
            self.aggregation.add(cieu_record, self._send_batch)
        else:
            self._send_single(cieu_record)

    def _passes_rules(self, record):
        rules = self.config.get('rules', {})
        min_sev = rules.get('min_severity', 0.0)
        actual_sev = record.get('R_t+1', {}).get('overall_severity', 0)
        if actual_sev < min_sev:
            return False
        skill_filter = rules.get('skills', [])
        if skill_filter:
            skill = record.get('U_t', {}).get('skill', '')
            if skill not in skill_filter:
                return False
        type_filter = rules.get('violation_types', [])
        if type_filter:
            violations = record.get('R_t+1', {}).get('violations', [])
            v_types = [v.get('type', '') for v in violations]
            if not any(vt in type_filter for vt in v_types):
                return False
        return True

    def _send_single(self, record):
        message = _format_single_alert(record)
        channels_sent = self._dispatch(message, record)
        _record_history(record, channels_sent)

    def _send_batch(self, records):
        if len(records) == 1:
            self._send_single(records[0])
            return
        message = _format_batch_alert(records)
        channels_sent = self._dispatch(message, records)
        _record_history(records, channels_sent)

    def _dispatch(self, message, data):
        channels = self.config.get('channels', {})
        sent_to = []
        tg = channels.get('telegram', {})
        if tg.get('enabled', False):
            token = tg.get('bot_token', '')
            chat_id = tg.get('chat_id', '')
            if token and chat_id:
                if _send_telegram(token, chat_id, message):
                    sent_to.append('telegram')
        sl = channels.get('slack', {})
        if sl.get('enabled', False):
            url = sl.get('webhook_url', '')
            if url:
                if _send_slack(url, message):
                    sent_to.append('slack')
        dc = channels.get('discord', {})
        if dc.get('enabled', False):
            url = dc.get('webhook_url', '')
            if url:
                if _send_discord(url, message):
                    sent_to.append('discord')
        wh = channels.get('webhook', {})
        if wh.get('enabled', False):
            url = wh.get('url', '')
            if url:
                webhook_data = {
                    'source': 'k9log',
                    'message': message,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'data': data if not isinstance(data, list) else {'batch': True, 'count': len(data)}
                }
                if _send_webhook(url, webhook_data):
                    sent_to.append('webhook')
        return sent_to


def get_alert_manager():
    return AlertManager()


def _dispatch_direct(config: dict, message: str, record: dict) -> list:
    """同步发送单条告警，绕过 aggregation。
    供 hook.py 子进程使用——子进程 <1s 退出，aggregation timer 永远不触发。
    """
    rules = config.get('rules', {})
    # 严重度过滤
    min_sev = rules.get('min_severity', 0.0)
    sev = (record.get('R_t+1') or {}).get('overall_severity', 0)
    if sev < min_sev:
        return []
    # DND 过滤
    if _is_dnd_active(config.get('dnd', {})):
        return []
    channels = config.get('channels', {})
    sent = []
    tg = channels.get('telegram', {})
    if tg.get('enabled', False) and tg.get('bot_token') and tg.get('chat_id'):
        if _send_telegram(tg['bot_token'], tg['chat_id'], message):
            sent.append('telegram')
    sl = channels.get('slack', {})
    if sl.get('enabled', False) and sl.get('webhook_url'):
        if _send_slack(sl['webhook_url'], message):
            sent.append('slack')
    dc = channels.get('discord', {})
    if dc.get('enabled', False) and dc.get('webhook_url'):
        if _send_discord(dc['webhook_url'], message):
            sent.append('discord')
    wh = channels.get('webhook', {})
    if wh.get('enabled', False) and wh.get('url'):
        payload = {'source': 'k9log', 'message': message,
                   'timestamp': datetime.now(timezone.utc).isoformat(), 'data': record}
        if _send_webhook(wh['url'], payload):
            sent.append('webhook')
    if sent:
        _record_history(record, sent)
    return sent

