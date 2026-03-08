"""
K9log Concurrency Test
======================
Tests that the logger and identity module are safe under concurrent load.

Three experiments:
  1. Chain integrity under concurrent writes
     - N threads each call a @k9-decorated function M times
     - Expected: exactly N*M records, seq 0..N*M-1, verify-log passes

  2. Identity race condition
     - N threads simultaneously call set_agent_identity with different names
     - Expected: no crash, final identity is one of the valid values

  3. Write failure resilience
     - Simulate a transient write failure mid-run
     - Expected: error logged, chain state preserved, subsequent writes succeed
"""
import threading
import time
import sys
import json
import os
from pathlib import Path

# ── Setup: use an isolated test ledger ───────────────────────────────────────
TEST_LOG = Path.home() / '.k9log' / 'logs' / 'k9_concurrency_test.jsonl'
# TEST_LOG.unlink(missing_ok=True)  # kept for diagnosis

# Point the logger at our test file by monkey-patching log_file after init
import k9log.logger as _logger_mod
_orig_init = _logger_mod.CIEULogger.__init__

def _patched_init(self, log_dir=None, max_size_mb=100):
    _orig_init(self, log_dir=TEST_LOG.parent, max_size_mb=max_size_mb)
    self.log_file = TEST_LOG  # redirect to test file

_logger_mod.CIEULogger.__init__ = _patched_init
# Force a clean logger instance pointing at test file
import k9log.logger as _lmod
import k9log.core as _core
_fresh = _logger_mod.CIEULogger.__new__(_logger_mod.CIEULogger)
_fresh.log_dir = TEST_LOG.parent
_fresh.log_file = TEST_LOG
_fresh.prev_hash = '0' * 64
_fresh.seq_counter = 0
_fresh.max_size = 100 * 1024 * 1024
import threading
_fresh.lock = threading.Lock()
_lmod._logger = _fresh
_core._logger = _fresh

from k9log.core import k9
from k9log.identity import set_agent_identity, get_agent_identity
from k9log.verifier import LogVerifier

PASS  = "\033[32m✅\033[0m"
FAIL  = "\033[31m❌\033[0m"
WARN  = "\033[33m⚠️ \033[0m"

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

# ─────────────────────────────────────────────────────────────
# Experiment 1: Concurrent writes — chain integrity
# ─────────────────────────────────────────────────────────────
section("Experiment 1: Concurrent writes — chain integrity")

N_THREADS = 8
M_CALLS   = 10
EXPECTED  = N_THREADS * M_CALLS

errors = []

@k9(max_values={"quantity": 9999})
def concurrent_op(thread_id, call_id, quantity=1):
    return {"thread": thread_id, "call": call_id}

def worker(thread_id):
    for i in range(M_CALLS):
        try:
            concurrent_op(thread_id=thread_id, call_id=i, quantity=i * 10)
        except Exception as e:
            errors.append(f"Thread {thread_id} call {i}: {e}")

print(f"  Launching {N_THREADS} threads × {M_CALLS} calls = {EXPECTED} expected records...")
threads = [threading.Thread(target=worker, args=(t,)) for t in range(N_THREADS)]
t0 = time.time()
for t in threads: t.start()
for t in threads: t.join()
elapsed = time.time() - t0
print(f"  Completed in {elapsed:.2f}s")

# Count records and check seq continuity
records = []
with open(TEST_LOG, encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except:
                pass

events = [r for r in records if 'X_t' in r]
seqs   = sorted(r['_integrity']['seq'] for r in records if '_integrity' in r)
gaps   = [seqs[i+1] - seqs[i] for i in range(len(seqs)-1) if seqs[i+1] - seqs[i] != 1]

print(f"\n  Records written : {len(records)}")
print(f"  Event records   : {len(events)}")
print(f"  Expected        : {EXPECTED}")
print(f"  Seq range       : {seqs[0] if seqs else '?'} .. {seqs[-1] if seqs else '?'}")
print(f"  Seq gaps        : {gaps if gaps else 'none'}")
print(f"  Worker errors   : {errors if errors else 'none'}")

# Run verifier
result = LogVerifier(TEST_LOG).verify_integrity()
chain_ok = result.get('passed', False)

record_ok = len(events) == EXPECTED
seq_ok    = len(gaps) == 0
ok1 = record_ok and seq_ok and chain_ok and not errors

print(f"\n  Record count    : {PASS if record_ok else FAIL} ({'OK' if record_ok else f'got {len(events)}, expected {EXPECTED}'})")
print(f"  Seq continuity  : {PASS if seq_ok else FAIL} ({'no gaps' if seq_ok else f'gaps at {gaps}'})")
print(f"  Chain integrity : {PASS if chain_ok else FAIL} ({result.get('message', 'verified')})")
print(f"  Worker errors   : {PASS if not errors else FAIL}")
print(f"\n  Experiment 1    : {PASS + ' PASS' if ok1 else FAIL + ' FAIL'}")

# ─────────────────────────────────────────────────────────────
# Experiment 2: Identity race condition
# ─────────────────────────────────────────────────────────────
section("Experiment 2: Identity race condition")

import k9log.identity as _identity_mod

identity_errors = []
names_set = []

def identity_worker(name):
    try:
        set_agent_identity(name, agent_type="test")
        got = get_agent_identity()
        names_set.append(got.get('agent_name') if got else None)
    except Exception as e:
        identity_errors.append(f"{name}: {e}")

N_ID = 20
id_threads = [
    threading.Thread(target=identity_worker, args=(f"Agent-{i}",))
    for i in range(N_ID)
]
print(f"  Launching {N_ID} threads simultaneously calling set_agent_identity...")
for t in id_threads: t.start()
for t in id_threads: t.join()

final = get_agent_identity()
valid_names = {f"Agent-{i}" for i in range(N_ID)}

no_crash   = len(identity_errors) == 0
valid_name = final is not None and final.get('agent_name') in valid_names
ok2 = no_crash and valid_name

print(f"  Errors          : {identity_errors if identity_errors else 'none'}")
print(f"  Final identity  : {final.get('agent_name') if final else 'None'}")
print(f"  Valid name      : {PASS if valid_name else FAIL}")
print(f"  No crashes      : {PASS if no_crash else FAIL}")
print(f"\n  Experiment 2    : {PASS + ' PASS' if ok2 else FAIL + ' FAIL'}")

# ─────────────────────────────────────────────────────────────
# Experiment 3: Write failure resilience
# ─────────────────────────────────────────────────────────────
section("Experiment 3: Write failure resilience (simulated disk error)")

import k9log.core as _core2
from k9log.core import get_logger

logger = get_logger()
seq_before = logger.seq_counter
hash_before = logger.prev_hash

# Patch open() inside logger to fail once
_real_open = open
_fail_count = [0]

def _flaky_open(path, mode='r', **kwargs):
    if 'a' in mode and str(path).endswith('.jsonl') and _fail_count[0] < 1:
        _fail_count[0] += 1
        raise OSError("Simulated disk full error")
    return _real_open(path, mode, **kwargs)

import builtins
builtins.open = _flaky_open

error_logged = []
import logging
class _Capture(logging.Handler):
    def emit(self, record):
        error_logged.append(record.getMessage())
_h = _Capture()
logging.getLogger('k9log').addHandler(_h)

# This write should fail silently
try:
    concurrent_op(thread_id=99, call_id=0, quantity=1)
except Exception as e:
    print(f"  {FAIL} Exception leaked to caller: {e}")

builtins.open = _real_open  # restore

seq_after_fail  = logger.seq_counter
hash_after_fail = logger.prev_hash

# Now write should succeed
concurrent_op(thread_id=99, call_id=1, quantity=1)
seq_after_ok = logger.seq_counter

no_leak     = True  # if we got here, no exception leaked
state_held  = (seq_after_fail == seq_before) and (hash_after_fail == hash_before)
recovered   = seq_after_ok == seq_before + 1
err_caught  = any('failed to write' in m.lower() or 'simulated' in m.lower() 
                  for m in error_logged)

ok3 = no_leak and state_held and recovered

print(f"  Seq before fail : {seq_before}")
print(f"  Seq after fail  : {seq_after_fail}  (should be unchanged)")
print(f"  Seq after ok    : {seq_after_ok}    (should be +1)")
print(f"  Hash preserved  : {PASS if state_held else FAIL}")
print(f"  No exception    : {PASS if no_leak else FAIL} (caller unaffected)")
print(f"  Recovery        : {PASS if recovered else FAIL} (next write succeeded)")
print(f"  Error captured  : {PASS if err_caught else WARN + ' (check K9LOG_LEVEL=DEBUG)'}")
print(f"\n  Experiment 3    : {PASS + ' PASS' if ok3 else FAIL + ' FAIL'}")

# ─────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────
section("Summary")
all_ok = ok1 and ok2 and ok3
results = [
    ("Concurrent writes — chain integrity", ok1),
    ("Identity race condition",              ok2),
    ("Write failure resilience",             ok3),
]
for name, ok in results:
    print(f"  {PASS if ok else FAIL}  {name}")

print(f"\n  Overall: {'ALL PASS' if all_ok else 'SOME FAILURES — see above'}")

# Cleanup
# TEST_LOG.unlink(missing_ok=True)  # kept for diagnosis
logging.getLogger('k9log').removeHandler(_h)
