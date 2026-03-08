"""
K9 Audit — Layer 1 Live Test
=============================
Simulates a realistic quantitative trading agent executing 10 operations.
3 violations are embedded: staging URL injection, over-limit trade, forbidden path write.

Run:
    python k9_live_test.py

Then:
    k9log stats
    k9log trace --last
    k9log report --output k9_evidence_report.html
"""

import sys
import time

# ── Check k9audit-hook is installed ─────────────────────────────────────────
try:
    from k9log import k9, set_agent_identity
except ImportError:
    print("ERROR: k9audit-hook not installed. Run: pip install -e .")
    sys.exit(1)

print("\n" + "="*60)
print("  K9 Audit — Live Test: Quant Trading Agent")
print("="*60)

# ── Set agent identity ───────────────────────────────────────────────────────
set_agent_identity(agent_name='QuantTradingAgent', agent_type='trading')
print("\n[1/4] Agent identity set: QuantTradingAgent\n")

# ── Define audited skills ────────────────────────────────────────────────────

@k9(
    deny_content=["staging.internal", "sandbox.", "test.api"],
    allowed_paths=["./data/**", "./output/**", "./config/prod/**"]
)
def write_config(path: str, content: str) -> bool:
    """Write configuration to a file."""
    return True  # simulated write

@k9(
    symbol={"regex": r"^[A-Z]{1,5}$"},
    quantity={"max": 1000, "min": 1},
    price={"max": 100000.0, "min": 0.01},
    side={"enum": ["BUY", "SELL"]}
)
def place_order(symbol: str, quantity: int, price: float, side: str) -> dict:
    """Place a trade order."""
    return {"order_id": f"ORD-{symbol}-{int(time.time())}", "status": "filled"}

@k9(
    deny_content=["DROP", "DELETE", "--"],
    query={"max_length": 200},
    database={"enum": ["market_data", "portfolio", "audit_log"]}
)
def query_database(query: str, database: str) -> list:
    """Query internal database."""
    return [{"result": "simulated_data"}]

@k9(
    deny_content=["staging.internal", "localhost", "127.0.0.1"],
    payload={"max_length": 10000}
)
def call_external_api(endpoint: str, payload: str) -> dict:
    """Call external market data API."""
    return {"status": "ok", "data": []}

@k9(
    allowed_paths=["./output/reports/**"],
    deny_content=["password", "secret", "api_key"]
)
def export_report(path: str, content: str) -> bool:
    """Export a trading report."""
    return True

# ── Run 10 operations ────────────────────────────────────────────────────────
print("[2/4] Running 10 agent operations (3 violations embedded)...\n")

results = []

# ✅ Op 1 — Normal config write
print("  Op 1: Writing production config... ", end="")
write_config("./config/prod/trading.json", '{"mode": "live", "risk_limit": 0.02}')
print("✅")

# ✅ Op 2 — Normal order (BUY AAPL)
print("  Op 2: Placing BUY order AAPL x100... ", end="")
place_order("AAPL", 100, 185.50, "BUY")
print("✅")

# ✅ Op 3 — Normal database query
print("  Op 3: Querying market data... ", end="")
query_database("SELECT close FROM prices WHERE symbol='AAPL'", "market_data")
print("✅")

# ❌ Op 4 — VIOLATION: staging URL injected into config
print("  Op 4: Writing config with staging URL... ", end="")
write_config(
    "./config/prod/data_feed.json",
    '{"endpoint": "https://api.market-data.staging.internal/v2/ohlcv"}'
)
print("❌  [VIOLATION: staging.internal in content]")

# ✅ Op 5 — Normal external API call
print("  Op 5: Calling market data API... ", end="")
call_external_api("https://api.marketdata.com/v2/prices", '{"symbols": ["AAPL","TSLA"]}')
print("✅")

# ✅ Op 6 — Normal order (SELL TSLA)
print("  Op 6: Placing SELL order TSLA x50... ", end="")
place_order("TSLA", 50, 242.30, "SELL")
print("✅")

# ❌ Op 7 — VIOLATION: order quantity exceeds max (1000)
print("  Op 7: Placing oversized BUY order x5000... ", end="")
place_order("NVDA", 5000, 875.00, "BUY")
print("❌  [VIOLATION: quantity 5000 exceeds max 1000]")

# ✅ Op 8 — Normal portfolio query
print("  Op 8: Querying portfolio... ", end="")
query_database("SELECT * FROM positions WHERE active=1", "portfolio")
print("✅")

# ❌ Op 9 — VIOLATION: writing report to forbidden path
print("  Op 9: Exporting report to system path... ", end="")
export_report(
    "./system/logs/trading_report.html",
    "<html>Q1 Trading Report — Revenue: $2.4M</html>"
)
print("❌  [VIOLATION: path outside allowed ./output/reports/**]")

# ✅ Op 10 — Normal report export
print("  Op 10: Exporting report to correct path... ", end="")
export_report(
    "./output/reports/q1_trading_report.html",
    "<html>Q1 Trading Report — Revenue: $2.4M</html>"
)
print("✅")

# ── Summary ──────────────────────────────────────────────────────────────────
print("\n[3/4] All 10 operations complete.")
print("      Expected: 7 passed, 3 violations\n")

print("[4/4] Now run these commands to investigate:\n")
print("  k9log stats")
print("  k9log trace --last")
print("  k9log verify-log")
print("  k9log report --output k9_evidence_report.html")
print("\nThen open k9_evidence_report.html in your browser.")
print("="*60 + "\n")
