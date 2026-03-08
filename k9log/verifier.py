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
K9log Verifier - Verify log integrity and Y* consistency
"""
import json
import hashlib
import gzip
from pathlib import Path


class LogVerifier:
    """Verify CIEU log integrity"""

    def __init__(self, log_file):
        self.log_file = Path(log_file)
        self.records = []
        self._load_records()

    def _load_records(self):
        """Load records from log file"""
        if not self.log_file.exists():
            return  # 文件不存在视为空日志，不抛异常
        if self.log_file.suffix == '.gz':
            opener = gzip.open
        else:
            opener = open
        with opener(self.log_file, 'rt', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        self.records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # 跳过非 JSON 行，不崩溃

    def verify_integrity(self):
        """Verify hash chain integrity."""
        if not self.records:
            return {'passed': True, 'message': 'No records to verify', 'total_records': 0}

        expected_prev_hash = '0' * 64
        seen_seqs = []

        for idx, record in enumerate(self.records):
            if record.get('event_type') == 'SESSION_END':
                continue

            if '_integrity' not in record:
                return {
                    'passed': False,
                    'message': f'Missing _integrity at record {idx}',
                    'break_point': idx,
                    'event_type': record.get('event_type', record.get('U_t', {}).get('skill', '?')),
                }

            integrity = record['_integrity']
            seq = integrity.get('seq')
            event_type = record.get('event_type', (record.get('U_t') or {}).get('skill', '?'))

            # Check seq monotonicity
            seen_seqs.append(seq)

            # Check prev_hash matches
            if integrity['prev_hash'] != expected_prev_hash:
                return {
                    'passed': False,
                    'message': f'Hash chain broken at record {idx}',
                    'break_point': idx,
                    'record_seq': seq,
                    'event_type': event_type,
                    'expected_prev_hash': expected_prev_hash,
                    'actual_prev_hash': integrity['prev_hash'],
                }

            # Verify event_hash
            clean_record = {k: v for k, v in record.items() if k != '_integrity'}
            canonical = self._canonicalize(clean_record)
            calculated_hash = hashlib.sha256(
                (expected_prev_hash + canonical).encode()
            ).hexdigest()

            if calculated_hash != integrity['event_hash']:
                return {
                    'passed': False,
                    'message': f'Hash mismatch at record {idx}',
                    'break_point': idx,
                    'record_seq': seq,
                    'event_type': event_type,
                    'expected_hash': calculated_hash,
                    'actual_hash': integrity['event_hash'],
                }

            expected_prev_hash = integrity['event_hash']

        # Check for duplicate seqs
        non_none_seqs = [s for s in seen_seqs if s is not None]
        if len(non_none_seqs) != len(set(non_none_seqs)):
            duplicates = [s for s in non_none_seqs if non_none_seqs.count(s) > 1]
            return {
                'passed': False,
                'message': f'Duplicate seq numbers found: {sorted(set(duplicates))}',
                'break_point': None,
            }

        return {
            'passed': True,
            'message': 'Log integrity verified',
            'total_records': len([r for r in self.records if r.get('event_type') != 'SESSION_END']),
            'session_root_hash': expected_prev_hash,
        }

    def verify_ystar_consistency(self):
        """Constraint coverage report — replaces naive group-by counting.

        Returns actionable audit data derived from CIEU log:
          - per-skill constraint coverage rate
          - constraint execution confirmation (R_t+1 has violations field)
          - actual violation hits per skill
          - Y*_t hash consistency (detect constraint version drift)
          - uncovered skills (zero constraints = audit blind spot)
        """
        from collections import defaultdict
        from k9log.constraints import check_compliance

        skill_stats = defaultdict(lambda: {
            "total": 0,
            "with_constraints": 0,
            "constraints_executed": 0,
            "violations_found": 0,
            "violation_details": [],
            "hashes": set(),
        })

        for idx, record in enumerate(self.records):
            skill  = record.get("U_t", {}).get("skill", "unknown")
            y_star = record.get("Y_star_t", {})
            r_t1   = record.get("R_t+1", {})
            constraints = y_star.get("constraints", {})
            h = y_star.get("y_star_meta", {}).get("hash", "")

            st = skill_stats[skill]
            st["total"] += 1
            if constraints:
                st["with_constraints"] += 1
            if h:
                st["hashes"].add(h)
            if "violations" in r_t1:
                st["constraints_executed"] += 1
            if not r_t1.get("passed", True):
                st["violations_found"] += 1
                for v in r_t1.get("violations", []):
                    st["violation_details"].append({
                        "step": idx,
                        "type": v.get("type"),
                        "field": v.get("field") or v.get("param"),
                        "severity": r_t1.get("overall_severity", 0.0),
                    })

        # Build report
        skills_report = []
        uncovered = []
        multi_version = []

        for skill, st in sorted(skill_stats.items()):
            coverage_rate = st["with_constraints"] / st["total"] if st["total"] else 0.0
            hash_count = len(st["hashes"])
            entry = {
                "skill": skill,
                "total_calls": st["total"],
                "with_constraints": st["with_constraints"],
                "coverage_rate": round(coverage_rate, 3),
                "constraints_executed": st["constraints_executed"],
                "violations_found": st["violations_found"],
                "violation_details": st["violation_details"],
                "constraint_versions": hash_count,
                "status": (
                    "UNCOVERED"      if coverage_rate == 0.0 else
                    "MULTI_VERSION"  if hash_count > 1 else
                    "OK"
                ),
            }
            skills_report.append(entry)
            if coverage_rate == 0.0:
                uncovered.append(skill)
            if hash_count > 1:
                multi_version.append(skill)

        total_calls = sum(s["total_calls"] for s in skills_report)
        covered_calls = sum(s["with_constraints"] for s in skills_report)
        total_violations = sum(s["violations_found"] for s in skills_report)

        return {
            "summary": {
                "total_records": total_calls,
                "covered_records": covered_calls,
                "overall_coverage_rate": round(covered_calls / total_calls, 3) if total_calls else 0.0,
                "total_violations": total_violations,
                "uncovered_skills": uncovered,
                "multi_version_skills": multi_version,
            },
            "skills": skills_report,
        }


    def _canonicalize(self, record):
        """Canonicalize record for hashing.
        Must match logger._write_record_locked exactly:
          - exclude _integrity (the field being verified)
          - ensure_ascii=False (logger writes non-ASCII as-is)
          - sort_keys=True, separators=(',', ':')
        """
        clean = {k: v for k, v in record.items() if k != '_integrity'}
        return json.dumps(clean, sort_keys=True, ensure_ascii=True, separators=(',', ':'))


def verify_log(log_file):
    """Convenience function to verify log"""
    verifier = LogVerifier(log_file)
    return verifier.verify_integrity()


def verify_ystar(log_file):
    """Convenience function to verify Y* consistency"""
    verifier = LogVerifier(log_file)
    return verifier.verify_ystar_consistency()

