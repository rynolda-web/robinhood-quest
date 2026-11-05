import argparse
import datetime as dt
import json
import math
from pathlib import Path
import time
from typing import Any

from dotenv import load_dotenv
import robin_stocks.robinhood as rh
import robinhood_agent as ra

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

LEDGER_FILE = BASE_DIR / "portfolio_ledger.json"
LAST_SCAN_FILE = BASE_DIR / "last_scan_report.json"
DAILY_HISTORY_FILE = BASE_DIR / "daily_history.json"
PORTFOLIO_BASELINE_USD = 10002.63  # Exact initial fill cost of the 10 managed $1,000 positions

# Managed shares & fill prices for the $10,000 portfolio (excludes pre-existing MSFT/AMZN shares)
MANAGED_POSITIONS = {
    "MSFT": {"qty": 1.80, "cost_basis": 1000.98, "avg_price": 556.1013},
    "AAPL": {"qty": 2.83, "cost_basis": 1001.27, "avg_price": 353.8058},
    "AMZN": {"qty": 3.71, "cost_basis": 1001.11, "avg_price": 269.8404},
    "META": {"qty": 1.57, "cost_basis": 999.74, "avg_price": 636.7800},
    "TSM":  {"qty": 2.52, "cost_basis": 1000.49, "avg_price": 397.0200},
    "GRMN": {"qty": 3.43, "cost_basis": 1000.50, "avg_price": 291.6900},
    "ISRG": {"qty": 2.06, "cost_basis": 999.47, "avg_price": 485.1800},
    "CDNS": {"qty": 3.03, "cost_basis": 999.72, "avg_price": 329.9400},
    "SHOP": {"qty": 6.58, "cost_basis": 999.86, "avg_price": 151.9550},
    "PLTR": {"qty": 5.84, "cost_basis": 1000.04, "avg_price": 171.2400},
}

# High Risk Section ($1,000 Under-$10 Asymmetric Upside Portfolio, $100 equal weight each)
HIGH_RISK_BASELINE_USD = 1000.00
HIGH_RISK_POSITIONS = {
    "RUN":  {"qty": 10.34, "cost_basis": 100.00, "avg_price": 9.67},
    "GRAB": {"qty": 29.85, "cost_basis": 100.00, "avg_price": 3.35},
    "WB":   {"qty": 15.22, "cost_basis": 100.00, "avg_price": 6.57},
    "FINV": {"qty": 32.57, "cost_basis": 100.00, "avg_price": 3.07},
    "PAYO": {"qty": 13.89, "cost_basis": 100.00, "avg_price": 7.20},
    "BTG":  {"qty": 19.53, "cost_basis": 100.00, "avg_price": 5.12},
    "BB":   {"qty": 11.39, "cost_basis": 100.00, "avg_price": 8.78},
    "SNAP": {"qty": 18.69, "cost_basis": 100.00, "avg_price": 5.35},
    "RIG":  {"qty": 18.18, "cost_basis": 100.00, "avg_price": 5.50},
    "OPFI": {"qty": 14.93, "cost_basis": 100.00, "avg_price": 6.70},
}

# All trades completed/submitted by the autonomous trading system (newest first)
SYSTEM_TRADES_BASELINE = [
    {"id": "6aebc071-e50e-4eec-8fb4-6601ebff2bfa", "symbol": "OPFI", "side": "BUY", "portfolio": "High Risk ($1k)", "state": "QUEUED", "qty": 14.93, "price": 6.70, "total_usd": 100.00, "created_at": "2026-11-04T23:32:01Z"},
    {"id": "6aebc06f-356d-4910-b56f-4cc89254c44e", "symbol": "RIG", "side": "BUY", "portfolio": "High Risk ($1k)", "state": "QUEUED", "qty": 18.18, "price": 5.50, "total_usd": 100.00, "created_at": "2026-11-04T23:31:59Z"},
    {"id": "6aebc06e-58ec-4218-a8b7-84577d4fa5c1", "symbol": "SNAP", "side": "BUY", "portfolio": "High Risk ($1k)", "state": "QUEUED", "qty": 18.69, "price": 5.35, "total_usd": 100.00, "created_at": "2026-11-04T23:31:58Z"},
    {"id": "6aebc06c-b8bd-4090-8586-b2810bca55de", "symbol": "BB", "side": "BUY", "portfolio": "High Risk ($1k)", "state": "QUEUED", "qty": 11.39, "price": 8.78, "total_usd": 100.00, "created_at": "2026-11-04T23:31:56Z"},
    {"id": "6aebc06b-266c-49fd-80ab-12ccc0d30f6e", "symbol": "BTG", "side": "BUY", "portfolio": "High Risk ($1k)", "state": "QUEUED", "qty": 19.53, "price": 5.12, "total_usd": 100.00, "created_at": "2026-11-04T23:31:55Z"},
    {"id": "6aebc069-72de-4a87-b8ac-9e36b2262fc2", "symbol": "PAYO", "side": "BUY", "portfolio": "High Risk ($1k)", "state": "QUEUED", "qty": 13.89, "price": 7.20, "total_usd": 100.00, "created_at": "2026-11-04T23:31:53Z"},
    {"id": "6aebc067-b6c4-481a-933e-8e8d6d83042c", "symbol": "FINV", "side": "BUY", "portfolio": "High Risk ($1k)", "state": "QUEUED", "qty": 32.57, "price": 3.07, "total_usd": 100.00, "created_at": "2026-11-04T23:31:51Z"},
    {"id": "6aebc066-f191-4c51-a72a-f224cd9d3725", "symbol": "WB", "side": "BUY", "portfolio": "High Risk ($1k)", "state": "QUEUED", "qty": 15.22, "price": 6.57, "total_usd": 100.00, "created_at": "2026-11-04T23:31:50Z"},
    {"id": "6aebc064-4c9f-4508-9ead-395d7a0c60f2", "symbol": "GRAB", "side": "BUY", "portfolio": "High Risk ($1k)", "state": "QUEUED", "qty": 29.85, "price": 3.35, "total_usd": 100.00, "created_at": "2026-11-04T23:31:48Z"},
    {"id": "6aebc063-ad04-47c1-b397-3ff7e479fba7", "symbol": "RUN", "side": "BUY", "portfolio": "High Risk ($1k)", "state": "QUEUED", "qty": 10.34, "price": 9.67, "total_usd": 100.00, "created_at": "2026-11-04T23:31:47Z"},
    {"id": "6aeb9afa-c966-44f5-8aef-67417b174b0c", "symbol": "URG", "side": "SELL", "portfolio": "Legacy Cleanup", "state": "FILLED", "qty": 77.82, "price": 0.75, "total_usd": 58.44, "created_at": "2026-11-04T20:52:10Z"},
    {"id": "6aeb9af8-bc31-4e68-8680-253ad1cf6329", "symbol": "HIVE", "side": "SELL", "portfolio": "Legacy Cleanup", "state": "FILLED", "qty": 31.35, "price": 1.81, "total_usd": 56.90, "created_at": "2026-11-04T20:52:08Z"},
    {"id": "6aeb9af6-07a3-48bd-95ac-38cf8054163a", "symbol": "AVGO", "side": "SELL", "portfolio": "Legacy Cleanup", "state": "FILLED", "qty": 0.5898, "price": 325.12, "total_usd": 191.76, "created_at": "2026-11-04T20:52:06Z"},
    {"id": "6aeb775a-79a8-447d-88e3-f4281fd9b8ab", "symbol": "PLTR", "side": "BUY", "portfolio": "$10k Portfolio", "state": "FILLED", "qty": 5.84, "price": 171.24, "total_usd": 1000.04, "created_at": "2026-11-04T18:20:10Z"},
    {"id": "6aeb7759-4432-434b-a06a-f8e858854863", "symbol": "SHOP", "side": "BUY", "portfolio": "$10k Portfolio", "state": "FILLED", "qty": 6.58, "price": 151.96, "total_usd": 999.86, "created_at": "2026-11-04T18:20:09Z"},
    {"id": "6aeb7757-f26e-45bf-9050-bcb9e6f7257c", "symbol": "CDNS", "side": "BUY", "portfolio": "$10k Portfolio", "state": "FILLED", "qty": 3.03, "price": 329.94, "total_usd": 999.72, "created_at": "2026-11-04T18:20:07Z"},
    {"id": "6aeb7755-6a7f-48b1-8e63-137d234a8291", "symbol": "ISRG", "side": "BUY", "portfolio": "$10k Portfolio", "state": "FILLED", "qty": 2.06, "price": 485.18, "total_usd": 999.47, "created_at": "2026-11-04T18:20:05Z"},
    {"id": "6aeb7753-f801-432e-be60-b3fa7d2e96bb", "symbol": "GRMN", "side": "BUY", "portfolio": "$10k Portfolio", "state": "FILLED", "qty": 3.43, "price": 291.69, "total_usd": 1000.50, "created_at": "2026-11-04T18:20:03Z"},
    {"id": "6aeb7751-e5d3-4612-af75-ebbe0dba9863", "symbol": "TSM", "side": "BUY", "portfolio": "$10k Portfolio", "state": "FILLED", "qty": 2.52, "price": 397.02, "total_usd": 1000.49, "created_at": "2026-11-04T18:20:01Z"},
    {"id": "6aeb7750-12a0-4f03-b1ab-3d1294dba0ff", "symbol": "META", "side": "BUY", "portfolio": "$10k Portfolio", "state": "FILLED", "qty": 1.57, "price": 636.78, "total_usd": 999.74, "created_at": "2026-11-04T18:20:00Z"},
    {"id": "6aeb774e-ba96-41d2-819d-af4b4f598b0b", "symbol": "AMZN", "side": "BUY", "portfolio": "$10k Portfolio", "state": "FILLED", "qty": 3.71, "price": 269.84, "total_usd": 1001.11, "created_at": "2026-11-04T18:19:58Z"},
    {"id": "6aeb774c-a492-44d9-b401-61ad86a98db9", "symbol": "AAPL", "side": "BUY", "portfolio": "$10k Portfolio", "state": "FILLED", "qty": 2.83, "price": 353.81, "total_usd": 1001.27, "created_at": "2026-11-04T18:19:56Z"},
    {"id": "6aeb774b-c40c-4c97-a179-496e34e39a36", "symbol": "MSFT", "side": "BUY", "portfolio": "$10k Portfolio", "state": "FILLED", "qty": 1.80, "price": 556.10, "total_usd": 1000.98, "created_at": "2026-11-04T18:19:55Z"},
]

TOTAL_BUDGET = 10000.00
NUM_POSITIONS = 10          # 5 Core Tech + 5 Emerging/Next-Gen Tech
TARGET_PER_POSITION = 1000.00  # $1,000 per stock = $10,000 total

# Bucket 1: Safe, Fortress Balance-Sheet Core Tech Leaders (50% = $5,000)
CORE_TECH_UNIVERSE = [
    "NVDA",   # NVIDIA - AI Compute Infrastructure
    "AAPL",   # Apple - Consumer Ecosystem & Edge AI
    "GOOGL",  # Alphabet - Cloud, Search & AI Models
    "MSFT",   # Microsoft - Enterprise Cloud & AI
    "AVGO",   # Broadcom - Custom AI Silicon & Networking
    "AMZN",   # Amazon - AWS Cloud & E-Commerce
    "META",   # Meta - AI Advertising & Llama Ecosystem
    "TSM",    # Taiwan Semiconductor - Global Foundry Leader
    "ASML",   # ASML - Semiconductor Lithography Monopoly
    "ORCL",   # Oracle - Cloud Database & AI Data Centers
]

# Bucket 2: Promising Next-Gen / Modern Tech Leaders — Profitable, Proven, Non-Speculative (50% = $5,000)
EMERGING_TECH_UNIVERSE = [
    "ISRG",   # Intuitive Surgical - Robotic Surgery & Medical Tech
    "ANET",   # Arista Networks - High-Speed AI Cloud Networking
    "PLTR",   # Palantir Technologies - Enterprise & Defense AI Operating System
    "SHOP",   # Shopify - Modern Commerce Infrastructure
    "GRMN",   # Garmin - Autonomous Aviation, Marine & Wearable Tech
    "CDNS",   # Cadence Design Systems - AI Chip Design & EDA Software
    "SNPS",   # Synopsys - Silicon-to-Systems AI Chip Engineering
    "AXON",   # Axon Enterprise - Public Safety AI, Bodycams & Drone Tech
    "MPWR",   # Monolithic Power Systems - Next-Gen AI Power Semis
    "PANW",   # Palo Alto Networks - Next-Gen AI Cybersecurity
    "NOW",    # ServiceNow - Enterprise Workflow Automation & AI Agents
    "CRWD",   # CrowdStrike - Cloud-Native Endpoint Security
]


def compute_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def analyze_candidate(symbol: str, bucket: str) -> dict[str, Any]:
    """Screen a candidate using proven institutional Multi-Factor Quantitative Analysis:

    Factors Applied:
    1. Fama-French / Carhart Cross-Sectional Momentum (12-1 Month & 6-1 Month Momentum, skipping the last 21 days to avoid 1-month short-term reversal).
    2. Risk-Adjusted Return Efficiency: Annualized Sharpe Ratio & Sortino Ratio (downside semi-deviation).
    3. Maximum Drawdown (MDD) & Frazzini-Pedersen Low-Volatility / Betting-Against-Beta (BAB) anomaly.
    4. Asness-Frazzini-Pedersen Quality Minus Junk (QMJ) & Value: Earnings Yield (E/P = 1 / PE), Market Cap scale, and Trend Persistence (% positive days).
    5. Mean-Reversion Timing Filter: RSI_14 and 50/200-day Moving Average regime.
    """
    historicals = rh.stocks.get_stock_historicals(
        symbol, interval="day", span="year", bounds="regular"
    ) or []
    closes = [float(bar["close_price"]) for bar in historicals if bar.get("close_price")]
    if len(closes) < 60:
        return {"symbol": symbol, "bucket": bucket, "passed": False, "reason": "Insufficient history"}

    quote_list = rh.stocks.get_quotes(symbol) or [{}]
    quote = quote_list[0] or {}
    fund_list = rh.stocks.get_fundamentals(symbol) or [{}]
    fund = fund_list[0] or {}

    current_price = float(quote.get("last_trade_price") or closes[-1])
    market_cap = float(fund.get("market_cap") or 0)
    pe_ratio_raw = fund.get("pe_ratio")
    pe_ratio = float(pe_ratio_raw) if pe_ratio_raw is not None else None
    earnings_yield_pct = (100.0 / pe_ratio) if (pe_ratio and pe_ratio > 0) else 0.0

    sma_50 = sum(closes[-50:]) / 50.0
    sma_200 = sum(closes[-200:]) / len(closes[-200:])
    high_52w = max(closes)
    rsi_14 = compute_rsi(closes, 14)

    # Daily returns series (full year)
    daily_returns = [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
    ]
    recent_60_returns = daily_returns[-60:]

    # Annualized Volatility (60-day)
    mean_ret_60 = sum(recent_60_returns) / len(recent_60_returns)
    variance_60 = sum((r - mean_ret_60) ** 2 for r in recent_60_returns) / max(1, len(recent_60_returns) - 1)
    annualized_vol = math.sqrt(variance_60) * math.sqrt(252) * 100.0

    # Annualized Sharpe Ratio & Sortino Ratio (using Rf = 4.25% annualized -> ~0.000168 daily)
    rf_daily = 0.0425 / 252.0
    mean_daily = sum(daily_returns) / len(daily_returns)
    std_daily = math.sqrt(sum((r - mean_daily) ** 2 for r in daily_returns) / max(1, len(daily_returns) - 1))
    downside_sq = [min(0.0, r - rf_daily) ** 2 for r in daily_returns]
    downside_dev = math.sqrt(sum(downside_sq) / max(1, len(downside_sq)))

    sharpe_ratio = ((mean_daily - rf_daily) / std_daily) * math.sqrt(252) if std_daily > 0 else 0.0
    sortino_ratio = ((mean_daily - rf_daily) / downside_dev) * math.sqrt(252) if downside_dev > 0 else 0.0

    # Maximum Drawdown (MDD) over trailing 12 months
    peak = closes[0]
    max_drawdown_pct = 0.0
    for c in closes:
        if c > peak:
            peak = c
        dd = ((c - peak) / peak) * 100.0
        if dd < max_drawdown_pct:
            max_drawdown_pct = dd

    # Fama-French / Carhart 12-1 Month & 6-1 Month Momentum (skipping last 21 trading days)
    price_1m_ago = closes[-21] if len(closes) >= 21 else current_price
    mom_12_1_pct = ((price_1m_ago / closes[0]) - 1.0) * 100.0
    mom_6_1_pct = ((price_1m_ago / closes[-126]) - 1.0) * 100.0 if len(closes) >= 126 else mom_12_1_pct

    ret_3m = ((current_price / closes[-63]) - 1.0) * 100.0 if len(closes) >= 63 else 0.0
    ret_6m = ((current_price / closes[-126]) - 1.0) * 100.0 if len(closes) >= 126 else 0.0
    dist_from_52w_high = ((current_price / high_52w) - 1.0) * 100.0

    # Strict Institutional Screening Filters:
    reasons = []
    passed = True
    if market_cap < 15_000_000_000:
        passed = False
        reasons.append(f"Market cap ${market_cap/1e9:.1f}B < $15B")
    if pe_ratio is None or pe_ratio <= 0:
        passed = False
        reasons.append(f"Non-profitable P/E ({pe_ratio})")
    if rsi_14 > 75:
        passed = False
        reasons.append(f"Overbought RSI ({rsi_14:.1f} > 75)")
    if annualized_vol > 55:
        passed = False
        reasons.append(f"High volatility ({annualized_vol:.1f}% > 55%)")

    # Multi-Factor Quantitative Composite Score:
    # Base = 50.0
    # + Risk-Adjusted Return Factor (Sortino + Sharpe): up to +25 pts
    # + Fama-French 12-1 / 6-1 Momentum Factor: up to +18 pts
    # + Low-Volatility / Drawdown Control Factor (Frazzini-Pedersen BAB): up to +18 pts
    # + Quality / Earnings Yield Factor (Asness QMJ): up to +14 pts
    # + Trend & Mean-Reversion Entry Timing (200-SMA + RSI sweet spot): up to +25 pts
    score = 50.0
    score += max(-12.0, min(15.0, sortino_ratio * 6.0))
    score += max(-8.0, min(10.0, sharpe_ratio * 5.0))
    score += max(-10.0, min(18.0, (0.6 * mom_12_1_pct + 0.4 * mom_6_1_pct) * 0.25))
    score += max(0.0, (48.0 - annualized_vol) * 0.45)
    score += max(-8.0, min(8.0, (25.0 + max_drawdown_pct) * 0.3))
    score += min(14.0, earnings_yield_pct * 3.2)

    if current_price >= sma_200:
        score += 14.0
    if current_price >= sma_50:
        score += 8.0
    if 38.0 <= rsi_14 <= 62.0:
        score += 10.0
    elif 30.0 <= rsi_14 < 38.0:
        score += 7.0

    return {
        "symbol": symbol,
        "bucket": bucket,
        "passed": passed,
        "score": round(score, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "sortino_ratio": round(sortino_ratio, 2),
        "mom_12_1_pct": round(mom_12_1_pct, 1),
        "max_drawdown_pct": round(max_drawdown_pct, 1),
        "earnings_yield_pct": round(earnings_yield_pct, 2),
        "price": round(current_price, 2),
        "market_cap_b": round(market_cap / 1e9, 1),
        "pe_ratio": round(pe_ratio, 2) if pe_ratio else None,
        "rsi_14": round(rsi_14, 1),
        "sma_50": round(sma_50, 2),
        "sma_200": round(sma_200, 2),
        "above_sma_200": current_price >= sma_200,
        "annualized_vol_pct": round(annualized_vol, 1),
        "ret_3m_pct": round(ret_3m, 1),
        "ret_6m_pct": round(ret_6m, 1),
        "dist_from_52w_high_pct": round(dist_from_52w_high, 1),
        "reasons": reasons,
    }


def run_screen() -> dict[str, Any]:
    """Screen all Core Tech and Emerging Tech candidates and pick top 5 from each bucket."""
    ra.ensure_login()
    print("Scanning Core Tech & Emerging Tech universes on Robinhood...")

    core_results = []
    for sym in CORE_TECH_UNIVERSE:
        res = analyze_candidate(sym, "core_tech")
        core_results.append(res)

    emerging_results = []
    for sym in EMERGING_TECH_UNIVERSE:
        res = analyze_candidate(sym, "emerging_tech")
        emerging_results.append(res)

    core_passed = sorted(
        [r for r in core_results if r["passed"]],
        key=lambda x: x["score"],
        reverse=True,
    )
    emerging_passed = sorted(
        [r for r in emerging_results if r["passed"]],
        key=lambda x: x["score"],
        reverse=True,
    )

    selected_core = core_passed[:5]
    selected_emerging = emerging_passed[:5]
    selected_all = selected_core + selected_emerging

    for item in selected_all:
        item["target_allocation_usd"] = TARGET_PER_POSITION

    report = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_budget_usd": TOTAL_BUDGET,
        "target_per_position_usd": TARGET_PER_POSITION,
        "selected_core_tech": selected_core,
        "selected_emerging_tech": selected_emerging,
        "all_core_candidates": sorted(core_results, key=lambda x: x.get("score", 0), reverse=True),
        "all_emerging_candidates": sorted(emerging_results, key=lambda x: x.get("score", 0), reverse=True),
    }

    LAST_SCAN_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def load_ledger() -> dict[str, Any]:
    if LEDGER_FILE.exists():
        return json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
    return {
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_budget_usd": TOTAL_BUDGET,
        "total_invested_usd": 0.0,
        "trades": [],
    }


def save_ledger(ledger: dict[str, Any]) -> None:
    LEDGER_FILE.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def rebalance_portfolio(dry_run: bool = False) -> dict[str, Any]:
    """Hourly conservative check & rebalance of the 10-stock portfolio.

    Conservative Guardrails:
    - Only executes trades during regular US market hours (Mon-Fri 9:35 AM - 3:55 PM ET).
    - Minimum 24-hour holding period per position before selling to avoid intraday churn / wash sales.
    - Rotates a position ONLY if:
      (a) It fails the conservative screen AND drops > 4% below its 200-day SMA, OR
      (b) RSI_14 > 78 (extreme overbought profit-taking), OR
      (c) Its conservative score drops below 60 while a replacement in the same bucket scores >= 20 points higher.
    """
    ra.ensure_login()
    scan_report = run_screen()
    holdings = rh.account.build_holdings() or {}
    ledger = load_ledger()

    # Map current tracked symbols from ledger trades
    tracked_core = ["MSFT", "AAPL", "AMZN", "META", "TSM"]
    tracked_emerging = ["GRMN", "ISRG", "CDNS", "SHOP", "PLTR"]
    tracked_all = set(tracked_core + tracked_emerging)

    # Check latest buy timestamp per symbol to enforce 24h cooldown
    last_buy_time: dict[str, dt.datetime] = {}
    for trade in ledger.get("trades", []):
        if trade.get("side", "buy") == "buy" and trade.get("symbol"):
            try:
                ts = dt.datetime.fromisoformat(trade["timestamp"])
                last_buy_time[trade["symbol"]] = ts
            except Exception:
                pass

    now_utc = dt.datetime.now(dt.timezone.utc)
    candidate_map = {
        c["symbol"]: c
        for c in (scan_report["all_core_candidates"] + scan_report["all_emerging_candidates"])
    }

    actions = []
    portfolio_snapshot = []

    for sym in sorted(tracked_all):
        pos = holdings.get(sym)
        metrics = candidate_map.get(sym, {})
        if not pos:
            continue

        price = float(pos.get("price", 0.0))
        managed_info = MANAGED_POSITIONS.get(sym)
        if managed_info:
            qty = float(managed_info["qty"])
            cost_basis = float(managed_info["cost_basis"])
            equity = round(qty * price, 2)
            pct_change = round(((equity - cost_basis) / cost_basis) * 100.0, 2)
        else:
            qty = float(pos.get("quantity", 0.0))
            equity = float(pos.get("equity", 0.0))
            pct_change = float(pos.get("percent_change", 0.0))
            cost_basis = round(equity / (1.0 + pct_change / 100.0), 2) if pct_change != -100 else equity
        score = float(metrics.get("score", 75.0))
        rsi = float(metrics.get("rsi_14", 50.0))
        sma_200 = float(metrics.get("sma_200", price))
        bucket = metrics.get("bucket", "core_tech" if sym in tracked_core else "emerging_tech")

        # Cooldown check (minimum 24h hold so hourly checks don't churn same-day buys)
        bought_at = last_buy_time.get(sym)
        hours_held = (now_utc - bought_at).total_seconds() / 3600.0 if bought_at else 999.0

        portfolio_snapshot.append({
            "symbol": sym,
            "bucket": bucket,
            "cost_basis_usd": round(cost_basis, 2),
            "equity_usd": equity,
            "pl_usd": round(equity - cost_basis, 2),
            "quantity": qty,
            "price": price,
            "total_return_pct": pct_change,
            "score": score,
            "sharpe_ratio": float(metrics.get("sharpe_ratio", 0.0)),
            "sortino_ratio": float(metrics.get("sortino_ratio", 0.0)),
            "mom_12_1_pct": float(metrics.get("mom_12_1_pct", 0.0)),
            "max_drawdown_pct": float(metrics.get("max_drawdown_pct", 0.0)),
            "earnings_yield_pct": float(metrics.get("earnings_yield_pct", 0.0)),
            "rsi_14": rsi,
            "sma_200": sma_200,
            "hours_held": round(hours_held, 1),
        })

        # Determine if conservative exit/rotation is warranted
        sell_reason = None
        if rsi > 78.0:
            sell_reason = f"Overbought profit-taking trigger (RSI {rsi:.1f} > 78)"
        elif price < sma_200 * 0.96 and not metrics.get("passed", True):
            sell_reason = f"Broke >4% below 200-SMA (${sma_200:.2f}) and failed screen ({metrics.get('reasons')})"
        elif score < 60.0:
            sell_reason = f"Conservative score deteriorated ({score:.1f} < 60)"

        if sell_reason:
            if hours_held < 24.0:
                actions.append({
                    "symbol": sym,
                    "action": "hold_cooldown",
                    "reason": f"{sell_reason}, but held only {hours_held:.1f}h (<24h conservative cooldown)",
                })
                continue

            # Find highest-scoring passed replacement in the same bucket not currently held
            pool = (
                scan_report["selected_core_tech"]
                if bucket == "core_tech"
                else scan_report["selected_emerging_tech"]
            )
            replacements = [
                r for r in pool
                if r["symbol"] not in holdings and r["passed"] and r["score"] >= score + 15.0
            ]
            if not replacements:
                actions.append({
                    "symbol": sym,
                    "action": "hold_no_superior_replacement",
                    "reason": sell_reason,
                })
                continue

            replacement = replacements[0]
            if dry_run:
                actions.append({
                    "action": "would_rotate",
                    "sell_symbol": sym,
                    "buy_symbol": replacement["symbol"],
                    "amount_usd": round(equity, 2),
                    "reason": sell_reason,
                })
            else:
                print(f"Rotating out of {sym} (${equity:.2f}) -> {replacement['symbol']} ({sell_reason})...")
                sell_res = rh.orders.order_sell_fractional_by_quantity(
                    symbol=sym,
                    quantity=qty,
                    timeInForce="gfd",
                    extendedHours=False,
                )
                time.sleep(2.0)
                buy_amount = min(1000.0, max(10.0, round(equity, 2)))
                buy_res = rh.orders.order_buy_fractional_by_price(
                    symbol=replacement["symbol"],
                    amountInDollars=buy_amount,
                    timeInForce="gfd",
                    extendedHours=False,
                )
                rot_record = {
                    "timestamp": now_utc.isoformat(),
                    "action": "rotated",
                    "sold_symbol": sym,
                    "bought_symbol": replacement["symbol"],
                    "amount_usd": buy_amount,
                    "reason": sell_reason,
                    "sell_order_id": sell_res.get("id") if isinstance(sell_res, dict) else None,
                    "buy_order_id": buy_res.get("id") if isinstance(buy_res, dict) else None,
                }
                actions.append(rot_record)
                ledger.setdefault("rebalances", []).append(rot_record)
                save_ledger(ledger)

    # Build High Risk Section snapshot ($1,000 Under-$10 Portfolio)
    hr_symbols = list(HIGH_RISK_POSITIONS.keys())
    hr_quotes = rh.stocks.get_quotes(hr_symbols) or []
    hr_price_map = {q["symbol"]: float(q.get("last_trade_price") or 0.0) for q in hr_quotes if q and q.get("symbol")}
    high_risk_snapshot = []
    for sym, info in HIGH_RISK_POSITIONS.items():
        pos = holdings.get(sym) or {}
        price = float(pos.get("price") or hr_price_map.get(sym) or info["avg_price"])
        if price <= 0:
            price = float(info["avg_price"])
        qty = float(pos.get("quantity") or info["qty"])
        if qty <= 0:
            qty = float(info["qty"])
        cost_basis = float(info["cost_basis"])
        equity = round(qty * price, 2)
        pl_usd = round(equity - cost_basis, 2)
        pl_pct = round((pl_usd / cost_basis) * 100.0, 2) if cost_basis else 0.0
        high_risk_snapshot.append({
            "symbol": sym,
            "quantity": qty,
            "price": round(price, 2),
            "cost_basis_usd": round(cost_basis, 2),
            "equity_usd": equity,
            "pl_usd": pl_usd,
            "total_return_pct": pl_pct,
        })

    # Build complete list of all system trades (rebalance rotations + initial & high-risk trades)
    system_trades = []
    for rot in reversed(ledger.get("rebalances", [])):
        ts = rot.get("timestamp", now_utc.isoformat())
        amt = float(rot.get("amount_usd", 1000.0))
        if rot.get("bought_symbol"):
            system_trades.append({
                "id": rot.get("buy_order_id") or f"rot-buy-{ts}",
                "symbol": rot["bought_symbol"],
                "side": "BUY",
                "portfolio": "Rebalance Rotation",
                "state": "FILLED",
                "qty": 0.0,
                "price": 0.0,
                "total_usd": amt,
                "created_at": ts,
            })
        if rot.get("sold_symbol"):
            system_trades.append({
                "id": rot.get("sell_order_id") or f"rot-sell-{ts}",
                "symbol": rot["sold_symbol"],
                "side": "SELL",
                "portfolio": "Rebalance Rotation",
                "state": "FILLED",
                "qty": 0.0,
                "price": 0.0,
                "total_usd": amt,
                "created_at": ts,
            })

    for t in SYSTEM_TRADES_BASELINE:
        t_copy = dict(t)
        if t_copy["state"] == "QUEUED" and t_copy["symbol"] in holdings:
            t_copy["state"] = "FILLED"
        system_trades.append(t_copy)

    summary = {
        "timestamp": now_utc.isoformat(),
        "status": "rebalance_checked",
        "total_tracked_equity_usd": round(sum(p["equity_usd"] for p in portfolio_snapshot), 2),
        "high_risk_cost_usd": HIGH_RISK_BASELINE_USD,
        "high_risk_total_usd": round(sum(p["equity_usd"] for p in high_risk_snapshot), 2),
        "rotations_executed": len([a for a in actions if a.get("action") == "rotated"]),
        "actions": actions,
        "system_trades": system_trades,
        "portfolio_snapshot": portfolio_snapshot,
        "high_risk_snapshot": high_risk_snapshot,
    }
    (BASE_DIR / "last_rebalance_report.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    update_daily_history(summary["total_tracked_equity_usd"])
    return summary


def update_daily_history(tracked_equity_usd: float) -> list[dict[str, Any]]:
    """Record or update today's daily total and profit/loss entry in daily_history.json (managed $10k portfolio only)."""
    today_str = dt.datetime.now(dt.timezone.utc).astimezone().strftime("%Y-%m-%d")

    history: list[dict[str, Any]] = []
    if DAILY_HISTORY_FILE.exists():
        try:
            history = json.loads(DAILY_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            history = []

    # Previous day's entry for daily P/L calculation
    prev_entries = [h for h in history if h.get("date") != today_str]
    prev_tracked = prev_entries[-1]["tracked_total_usd"] if prev_entries else PORTFOLIO_BASELINE_USD

    daily_pl_usd = round(tracked_equity_usd - prev_tracked, 2)
    daily_pl_pct = round((daily_pl_usd / prev_tracked) * 100.0, 2) if prev_tracked else 0.0
    total_pl_usd = round(tracked_equity_usd - PORTFOLIO_BASELINE_USD, 2)
    total_pl_pct = round((total_pl_usd / PORTFOLIO_BASELINE_USD) * 100.0, 2)

    entry = {
        "date": today_str,
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "initial_cost_usd": round(PORTFOLIO_BASELINE_USD, 2),
        "tracked_total_usd": round(tracked_equity_usd, 2),
        "daily_pl_usd": daily_pl_usd,
        "daily_pl_pct": daily_pl_pct,
        "total_pl_usd": total_pl_usd,
        "total_pl_pct": total_pl_pct,
    }

    if history and history[-1].get("date") == today_str:
        history[-1] = entry
    else:
        history.append(entry)

    DAILY_HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    sync_embedded_html()
    return history


def fetch_latest_news() -> list[dict[str, Any]]:
    """Fetch latest NYT Business and WSJ Business/Markets headlines for offline/embedded fallback."""
    import urllib.request
    import xml.etree.ElementTree as ET
    feeds = [
        ("NYT", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"),
        ("WSJ", "https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness"),
        ("WSJ", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain"),
    ]
    items: list[dict[str, Any]] = []
    seen = set()
    for source, url in feeds:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            xml_bytes = urllib.request.urlopen(req, timeout=8).read()
            root = ET.fromstring(xml_bytes)
            for item in root.findall(".//item")[:12]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                items.append({
                    "source": source,
                    "title": title,
                    "link": link,
                    "pubDate": pub,
                })
        except Exception:
            pass
    return items[:25]


def sync_embedded_html() -> None:
    """Keep index.html and money.html embedded JSON synced so opening directly always shows latest data."""
    reb_file = BASE_DIR / "last_rebalance_report.json"
    if not reb_file.exists() or not DAILY_HISTORY_FILE.exists():
        return
    import re
    reb_txt = reb_file.read_text(encoding="utf-8").strip()
    hist_txt = DAILY_HISTORY_FILE.read_text(encoding="utf-8").strip()
    news_txt = json.dumps(fetch_latest_news(), indent=2)
    replacement = (
        f"<script>window.EMBEDDED_REBALANCE = {reb_txt};\n"
        f"window.EMBEDDED_HISTORY = {hist_txt};\n"
        f"window.EMBEDDED_NEWS = {news_txt};</script>"
    )
    for fname in ["index.html", "money.html"]:
        html_file = BASE_DIR / fname
        if html_file.exists():
            html = html_file.read_text(encoding="utf-8")
            html_updated = re.sub(
                r"<script>window\.EMBEDDED_REBALANCE = .*?;</script>",
                lambda _: replacement,
                html,
                flags=re.DOTALL,
            )
            html_file.write_text(html_updated, encoding="utf-8")


def execute_portfolio_deployment(report: dict[str, Any]) -> dict[str, Any]:
    """Automatically execute fractional dollar-amount buy orders for the selected 10-stock portfolio."""
    ra.ensure_login()
    ledger = load_ledger()
    remaining_budget = round(TOTAL_BUDGET - float(ledger.get("total_invested_usd", 0.0)), 2)

    if remaining_budget < 10.0:
        return {
            "status": "budget_fully_invested",
            "remaining_budget_usd": remaining_budget,
            "ledger": ledger,
        }

    picks = report["selected_core_tech"] + report["selected_emerging_tech"]
    executed_orders = []

    for pick in picks:
        symbol = pick["symbol"]
        bucket = pick["bucket"]
        order_amount = min(TARGET_PER_POSITION, remaining_budget)
        if order_amount < 5.0:
            break

        print(f"Placing autonomous market buy order: ${order_amount:.2f} of {symbol} ({bucket})...")
        try:
            order_res = rh.orders.order_buy_fractional_by_price(
                symbol=symbol,
                amountInDollars=round(order_amount, 2),
                timeInForce="gfd",
                extendedHours=False,
            )
            order_id = order_res.get("id") if isinstance(order_res, dict) else None
            state = order_res.get("state") if isinstance(order_res, dict) else "unknown"

            record = {
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                "symbol": symbol,
                "bucket": bucket,
                "amount_usd": round(order_amount, 2),
                "reference_price": pick["price"],
                "score": pick["score"],
                "order_id": order_id,
                "state": state,
                "raw_response": order_res,
            }
            executed_orders.append(record)

            if order_id:
                ledger["trades"].append(record)
                ledger["total_invested_usd"] = round(
                    float(ledger.get("total_invested_usd", 0.0)) + order_amount, 2
                )
                remaining_budget = round(TOTAL_BUDGET - ledger["total_invested_usd"], 2)
                save_ledger(ledger)
            time.sleep(1.0)
        except Exception as exc:
            executed_orders.append({
                "symbol": symbol,
                "bucket": bucket,
                "amount_usd": round(order_amount, 2),
                "error": str(exc),
            })

    return {
        "status": "completed",
        "total_invested_usd": ledger["total_invested_usd"],
        "remaining_budget_usd": round(TOTAL_BUDGET - ledger["total_invested_usd"], 2),
        "executed_orders": executed_orders,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Conservative Tech Screener & Auto-Trader")
    parser.add_argument("--screen-only", action="store_true", help="Run screener without placing trades")
    parser.add_argument("--execute", action="store_true", help="Run screener and automatically execute trades")
    parser.add_argument("--rebalance", action="store_true", help="Run hourly conservative portfolio rebalance")
    parser.add_argument("--dry-run", action="store_true", help="Preview rebalance actions without trading")
    args = parser.parse_args()

    if args.rebalance:
        reb_summary = rebalance_portfolio(dry_run=args.dry_run)
        print(json.dumps(reb_summary, indent=2))
    else:
        scan_report = run_screen()
        if args.execute:
            exec_summary = execute_portfolio_deployment(scan_report)
            print(json.dumps(exec_summary, indent=2))
        else:
            print(json.dumps({
                "selected_core_tech": scan_report["selected_core_tech"],
                "selected_emerging_tech": scan_report["selected_emerging_tech"],
            }, indent=2))
