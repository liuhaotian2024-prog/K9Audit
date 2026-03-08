# K9log - Engineering-grade Causal Audit for AI Agent Ecosystems
# Copyright (C) 2026 Haotian Liu
# AGPL-3.0 - see LICENSE for details
"""
K9log Logger - CIEU log writer with hash chain and verification
"""
import json
import hashlib
import gzip
from pathlib import Path
from datetime import datetime, timezone
import threading


class CIEULogger:
    """CIEU Logger with hash chain"""

    def __init__(self, log_dir=None, max_size_mb=100):
        self.log_dir = log_dir or (Path.home() / '.k9log' / 'logs')
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / 'k9log.cieu.jsonl'
        self.prev_hash = '0' * 64
        self.seq_counter = 0
        self.max_size = max_size_mb * 1024 * 1024
        self.lock = threading.Lock()
        self._load_last_hash()

    def _load_last_hash(self):
        """Load the last valid hash from existing log file (reads last 200 lines)."""
        if not self.log_file.exists():
            return
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            for line in reversed(lines[-200:]):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if '_integrity' in record:
                        self.prev_hash = record['_integrity']['event_hash']
                        self.seq_counter = record['_integrity']['seq'] + 1
                        return
                except Exception:
                    continue
        except Exception as e:
            print(f'Warning: Could not load last hash: {e}')

    def write_cieu(self, record):
        """Write CIEU record with hash chain.

        Decision Engine evaluates fuse inline (inside lock) so FUSE record
        is always immediately after the triggering violation with correct
        prev_hash/seq.  Channel alerting is called outside the lock.
        """
        is_violation = not (record.get('R_t+1') or {}).get('passed', True)
        is_fuse_record = (
            record.get('event_type') == 'FUSE'
            or (record.get('U_t') or {}).get('skill') == 'k9log.fuse'
        )

        # Attach policy pin (does not affect hash chain correctness)
        self._attach_policy_pin(record)

        # ── v0.5 Constitutional Gate (default OFF) ───────────────────────────
        # Zero impact when constitutional.enabled is absent or False.
        try:
            from k9log.governance.constitutional_gate import (
                is_constitutional_enabled, apply_constitutional_gate)
            from k9log.policy_pack import get_active_policy
            _active = get_active_policy()
            _pcfg   = {"constitutional": _active.constitutional} if _active else None
            if is_constitutional_enabled(_pcfg):
                _pid = _active.policy_id if _active else ""
                _pv  = _active.version   if _active else ""
                apply_constitutional_gate(record, _pcfg, _pid, _pv)
        except Exception:
            pass  # Constitutional gate must never break core audit path
        # ── end v0.5 gate ────────────────────────────────────────────────────

        with self.lock:
            if self.log_file.exists() and self.log_file.stat().st_size > self.max_size:
                self._rotate_log()

            self._write_record_locked(record)

            # Fuse evaluated inline (same lock) to keep chain intact
            if is_violation and not is_fuse_record:
                self._maybe_write_fuse_inline(record)

        # Channel alerting outside lock - slow I/O must not block writers
        if is_violation and not is_fuse_record:
            try:
                from k9log.alerting import get_alert_manager
                get_alert_manager().on_violation(record)
            except Exception:
                pass

    def _attach_policy_pin(self, record):
        """Attach _policy pin to record if an active policy is loaded."""
        try:
            from k9log.policy_pack import get_active_policy, policy_hash
            policy = get_active_policy()
            if policy is not None:
                record['_policy'] = {
                    'policy_id': policy.policy_id,
                    'version':   policy.version,
                    'hash':      policy_hash(policy),
                }
        except Exception:
            pass

    def _write_record_locked(self, record):
        """Compute hash and append record. Must be called with self.lock held."""
        canonical = self._canonicalize(record)
        current_hash = hashlib.sha256(
            (self.prev_hash + canonical).encode()
        ).hexdigest()
        record['_integrity'] = {
            'event_hash': current_hash,
            'prev_hash':  self.prev_hash,
            'seq':        self.seq_counter,
        }
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        self.prev_hash = current_hash
        self.seq_counter += 1

    def _maybe_write_fuse_inline(self, violation_record):
        """Evaluate fuse via DecisionEngine and write FUSE record inline.

        Uses self (same lock) to guarantee correct prev_hash/seq continuity.
        activate() called with write_cieu_event=False to prevent duplicate write.
        """
        try:
            # Quick guard: read fuse.enabled directly to respect live config patches
            from k9log.alerting import _load_config as _ac
            if not _ac().get('fuse', {}).get('enabled', False):
                return
            from k9log.decision import get_decision_engine, reset_decision_engine, DecisionEngine
            from k9log.policy_pack import get_active_policy
            from k9log.fuse import activate, FuseDecision
            _policy = get_active_policy()
            dec_result = DecisionEngine(policy=_policy).evaluate(violation_record)
            if not dec_result.fuse:
                return

            profile = dec_result.profile.get('fuse', {})
            x_t = violation_record.get('X_t') or {}
            agent_id   = x_t.get('agent_id',   '')
            session_id = x_t.get('session_id', '')

            fuse_record = {
                'event_type': 'FUSE',
                'X_t': x_t,
                'U_t': {
                    'skill': 'k9log.fuse',
                    'params': {
                        'action': 'FUSE',
                        'mode':   profile.get('mode', 'TOKEN_BUDGET_FREEZE'),
                        'scope':  {'agent_id': agent_id, 'session_id': session_id},
                        'budget': profile.get('budget', {}),
                        'until':  'USER_ACK',
                        'reason': dec_result.reason,
                        'trigger': {
                            'severity': dec_result.severity,
                            'types':    dec_result.tags,
                        },
                    },
                },
                'Y_star_t': {'constraints': {}, 'y_star_meta': {'source': 'k9log.fuse', 'version': '1.0', 'hash': 'builtin', 'loaded_at': ''}},
                'Y_t+1': {'status': 'fuse_triggered', 'result': {'mode': profile.get('mode', 'TOKEN_BUDGET_FREEZE'), 'agent_id': agent_id}},
                'R_t+1': {
                    'passed':           True,
                    'overall_severity': dec_result.severity,
                    'violations':       [],
                },
            }
            self._write_record_locked(fuse_record)

            # Persist fuse state/events only (no CIEU write)
            fuse_dec = FuseDecision(
                fuse=True,
                reason=dec_result.reason,
                severity=dec_result.severity,
                scope=profile.get('scope', 'agent'),
                agent_id=agent_id,
                session_id=session_id,
                trigger_types=tuple(dec_result.tags),
                mode=profile.get('mode', 'TOKEN_BUDGET_FREEZE'),
                token_cap=int((profile.get('budget') or {}).get('token_cap', 0)),
                tool_calls=int((profile.get('budget') or {}).get('tool_calls', 0)),
            )
            activate(fuse_dec, violation_record, write_cieu_event=False)
        except Exception as _fuse_ex:
            import traceback, os; err_path = os.path.expanduser("~/.k9log/fuse_inline_error.txt"); open(err_path, "w", encoding="utf-8").write(traceback.format_exc())

    def _canonicalize(self, record):
        """Canonicalize record for consistent hashing."""
        clean = {k: v for k, v in record.items() if k != '_integrity'}
        return json.dumps(clean, sort_keys=True, ensure_ascii=True, separators=(',', ':'))

    def _rotate_log(self):
        """Rotate log file when it gets too large.

        After rotation:
        - Old file is compressed to k9log.cieu.<timestamp_ms>.jsonl.gz
        - New log file starts a fresh hash chain (prev_hash reset to zeros)
        - seq_counter continues from current value (not reset) for uniqueness
        """
        # Use microsecond precision to avoid collisions on rapid rotation
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        archive_name = self.log_dir / f'k9log.cieu.{timestamp}.jsonl'
        self.log_file.rename(archive_name)
        with open(archive_name, 'rb') as f_in:
            with gzip.open(f'{archive_name}.gz', 'wb') as f_out:
                f_out.writelines(f_in)
        archive_name.unlink()
        # ── Reset hash chain for the new file ─────────────────────────────
        # Each rotated file is an independent, self-verifiable chain segment.
        self.prev_hash = '0' * 64
        print(f'Log rotated: {archive_name}.gz')

    def finalize_session(self, session_id=None):
        """Write session end marker with root hash."""        # ── 统计本次 session ──────────────────────────────────────────────────
        session_records = [
            r for r in self._iter_session_records(session_id or 'default')
        ]
        total   = len(session_records)
        viols   = sum(1 for r in session_records
                      if not (r.get('R_t+1') or {}).get('passed', True))
        skills  = set(
            (r.get('U_t') or {}).get('skill', '?')
            for r in session_records
        )

        session_end = {
            'event_type':        'SESSION_END',
            'session_id':        session_id or 'default',
            'session_root_hash': self.prev_hash,
            'total_events':      self.seq_counter,
            'timestamp':         datetime.now(timezone.utc).isoformat(),
        }
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(session_end, ensure_ascii=False) + '\n')

        # ── Session 结束小结（打印到 stderr，让用户/Agent 立刻看到）──────────
        import sys as _sys
        status = '✓ 无违规' if viols == 0 else f'⚠ {viols} 次违规'
        _sys.stderr.write(
            f'\n[K9] Session 结束  操作:{total}  {status}  '
            f'审计日志: {self.log_file}\n'
        )
        if viols > 0:
            _sys.stderr.write('[K9] 下一步: k9log trace --last  # 查看违规详情\n')
        else:
            _sys.stderr.write('[K9] 下一步: k9log health  # 查看完整健康报告\n')
        _sys.stderr.write('\n')

        # ── Auto-learn on session end ────────────────────────────────────────
        try:
            from k9log.metalearning import learn, cleanup_session_grants
            learn(write_grants=True, silent=True)
            cleanup_session_grants()
        except Exception:
            pass  # Never crash on metalearning failure

    def _iter_session_records(self, session_id: str):
        """从日志文件里读出属于本 session 的 CIEU 记录。"""
        if not self.log_file.exists():
            return
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get('event_type') in ('SESSION_END', 'FUSE'):
                            continue
                        rec_sid = (rec.get('X_t') or {}).get('session_id', '')
                        if not session_id or rec_sid == session_id or session_id == 'default':
                            yield rec
                    except Exception:
                        continue
        except Exception:
            return


# Global logger instance
_logger = None


def get_logger():
    """Get global logger instance."""
    global _logger
    if _logger is None:
        _logger = CIEULogger()
    return _logger

