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

Design note -- streaming first
------------------------------
Both verify_integrity() and verify_ystar_consistency() are fully streaming:
records are read and processed one line at a time without accumulating them
in memory. This keeps peak memory O(1) regardless of log size, which matters
for long-running agent sessions that can produce tens of thousands of records.
"""
import json
import hashlib
import gzip
import logging
from pathlib import Path
from collections import defaultdict

_log = logging.getLogger("k9log.verifier")

# Coverage below this threshold triggers a warning in the report.
COVERAGE_WARN_THRESHOLD = 0.80


class LogVerifier:
    """Verify CIEU log integrity -- streaming, O(1) memory."""

    def __init__(self, log_file):
        self.log_file = Path(log_file)

    def _stream_records(self):
        """Yield parsed records one at a time. Never accumulates in memory."""
        if not self.log_file.exists():
            return
        opener = gzip.open if self.log_file.suffix == ".gz" else open
        with opener(self.log_file, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    pass  # skip corrupt lines -- do not abort verification

    def _canonicalize(self, record):
        # SYNC WARNING -- keep this function identical to
        # k9log/logger.py : _write_record_locked()
        #
        # Both must use:
        #   json.dumps(..., sort_keys=True, ensure_ascii=True,
        #              separators=(",", ":"))
        #
        # Any change to serialization in logger.py MUST be mirrored
        # here, or verify_integrity() will silently produce false
        # "chain broken" errors on every record.
        clean = {k: v for k, v in record.items() if k != "_integrity"}
        return json.dumps(clean, sort_keys=True, ensure_ascii=True,
                          separators=(",", ":"))

    def verify_integrity(self):
        """Verify hash chain integrity -- streaming, O(1) memory."""
        expected_prev_hash = "0" * 64
        seen_seqs = set()
        total = 0
        idx = 0

        for record in self._stream_records():
            if record.get("event_type") == "SESSION_END":
                continue

            if "_integrity" not in record:
                return {
                    "passed": False,
                    "message": f"Missing _integrity at record {idx}",
                    "break_point": idx,
                    "event_type": record.get(
                        "event_type",
                        record.get("U_t", {}).get("skill", "?")
                    ),
                }

            integrity = record["_integrity"]
            seq = integrity.get("seq")
            event_type = record.get(
                "event_type",
                (record.get("U_t") or {}).get("skill", "?")
            )

            if seq is not None:
                if seq in seen_seqs:
                    return {
                        "passed": False,
                        "message": f"Duplicate seq number: {seq}",
                        "break_point": idx,
                    }
                seen_seqs.add(seq)

            if integrity["prev_hash"] != expected_prev_hash:
                return {
                    "passed": False,
                    "message": f"Hash chain broken at record {idx}",
                    "break_point": idx,
                    "record_seq": seq,
                    "event_type": event_type,
                    "expected_prev_hash": expected_prev_hash,
                    "actual_prev_hash": integrity["prev_hash"],
                }

            canonical = self._canonicalize(record)
            calculated_hash = hashlib.sha256(
                (expected_prev_hash + canonical).encode()
            ).hexdigest()

            if calculated_hash != integrity["event_hash"]:
                return {
                    "passed": False,
                    "message": f"Hash mismatch at record {idx}",
                    "break_point": idx,
                    "record_seq": seq,
                    "event_type": event_type,
                    "expected_hash": calculated_hash,
                    "actual_hash": integrity["event_hash"],
                }

            expected_prev_hash = integrity["event_hash"]
            total += 1
            idx += 1

        return {
            "passed": True,
            "message": "Log integrity verified",
            "total_records": total,
            "session_root_hash": expected_prev_hash,
        }

    def verify_ystar_consistency(self):
        """Constraint coverage report -- streaming, O(skills) memory."""
        skill_stats = defaultdict(lambda: {
            "total": 0,
            "with_constraints": 0,
            "constraints_executed": 0,
            "violations_found": 0,
            "violation_details": [],
            "hashes": set(),
        })

        idx = 0
        for record in self._stream_records():
            skill       = record.get("U_t", {}).get("skill", "unknown")
            y_star      = record.get("Y_star_t", {})
            r_t1        = record.get("R_t+1", {})
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
            idx += 1

        skills_report = []
        uncovered     = []
        multi_version = []

        for skill, st in sorted(skill_stats.items()):
            total = st["total"]
            coverage_rate = st["with_constraints"] / total if total else 0.0
            hash_count    = len(st["hashes"])
            entry = {
                "skill": skill,
                "total_calls": total,
                "with_constraints": st["with_constraints"],
                "coverage_rate": round(coverage_rate, 3),
                "constraints_executed": st["constraints_executed"],
                "violations_found": st["violations_found"],
                "violation_details": st["violation_details"],
                "constraint_versions": hash_count,
                "status": (
                    "UNCOVERED"     if coverage_rate == 0.0 else
                    "MULTI_VERSION" if hash_count > 1        else
                    "OK"
                ),
            }
            skills_report.append(entry)
            if coverage_rate == 0.0:
                uncovered.append(skill)
            if hash_count > 1:
                multi_version.append(skill)

        total_calls      = sum(s["total_calls"]      for s in skills_report)
        covered_calls    = sum(s["with_constraints"] for s in skills_report)
        total_violations = sum(s["violations_found"] for s in skills_report)
        overall_coverage = round(covered_calls / total_calls, 3) if total_calls else 0.0

        coverage_warning = None
        if total_calls > 0 and overall_coverage < COVERAGE_WARN_THRESHOLD:
            blind_pct = round((1 - overall_coverage) * 100, 1)
            coverage_warning = (
                f"WARNING: Constraint coverage {overall_coverage*100:.1f}% is below "
                f"{COVERAGE_WARN_THRESHOLD*100:.0f}% threshold -- "
                f"{blind_pct}% of skill calls have no rules defined (audit blind spots)"
            )
            _log.warning(coverage_warning)

        return {
            "summary": {
                "total_records":         total_calls,
                "covered_records":       covered_calls,
                "overall_coverage_rate": overall_coverage,
                "coverage_warning":      coverage_warning,
                "total_violations":      total_violations,
                "uncovered_skills":      uncovered,
                "multi_version_skills":  multi_version,
            },
            "skills": skills_report,
        }


def verify_log(log_file):
    return LogVerifier(log_file).verify_integrity()


def verify_ystar(log_file):
    return LogVerifier(log_file).verify_ystar_consistency()
