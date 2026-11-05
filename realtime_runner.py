import datetime as dt
import json
from pathlib import Path
import subprocess
import time

import robin_stocks.robinhood as rh
import robinhood_agent as ra
import screener_trader as st

BASE_DIR = Path(__file__).resolve().parent
GH = r"C:\Program Files\GitHub CLI\gh.exe"


def fast_quote_refresh() -> dict:
    """Refresh live prices for all 10 Core/Emerging positions + 10 High-Risk positions in ~0.8s."""
    ra.ensure_login()
    core_syms = list(st.MANAGED_POSITIONS.keys())
    hr_syms = list(st.HIGH_RISK_POSITIONS.keys())
    all_syms = core_syms + hr_syms

    quotes = rh.stocks.get_quotes(all_syms) or []
    q_map = {}
    for q in quotes:
        if not q or not q.get("symbol"):
            continue
        p = float(q.get("last_extended_hours_trade_price") or q.get("last_trade_price") or 0.0)
        if p > 0:
            q_map[q["symbol"]] = p

    reb_file = BASE_DIR / "last_rebalance_report.json"
    reb = json.loads(reb_file.read_text(encoding="utf-8")) if reb_file.exists() else {}

    # Update $10k Managed Portfolio prices & P/L
    portfolio_snapshot = reb.get("portfolio_snapshot", [])
    for item in portfolio_snapshot:
        sym = item["symbol"]
        info = st.MANAGED_POSITIONS.get(sym, {})
        price = q_map.get(sym, float(item.get("price", info.get("avg_price", 0.0))))
        qty = float(info.get("qty", item.get("quantity", 0.0)))
        cost = float(info.get("cost_basis", item.get("cost_basis_usd", 1000.0)))
        equity = round(qty * price, 2)
        pl_usd = round(equity - cost, 2)
        pl_pct = round((pl_usd / cost) * 100.0, 2) if cost else 0.0
        item["price"] = round(price, 2)
        item["quantity"] = qty
        item["cost_basis_usd"] = round(cost, 2)
        item["equity_usd"] = equity
        item["pl_usd"] = pl_usd
        item["total_return_pct"] = pl_pct

    # Update $1k High Risk Portfolio prices & P/L
    high_risk_snapshot = []
    for sym, info in st.HIGH_RISK_POSITIONS.items():
        price = q_map.get(sym, float(info["avg_price"]))
        qty = float(info["qty"])
        cost = float(info["cost_basis"])
        equity = round(qty * price, 2)
        pl_usd = round(equity - cost, 2)
        pl_pct = round((pl_usd / cost) * 100.0, 2) if cost else 0.0
        high_risk_snapshot.append({
            "symbol": sym,
            "quantity": qty,
            "price": round(price, 2),
            "cost_basis_usd": round(cost, 2),
            "equity_usd": equity,
            "pl_usd": pl_usd,
            "total_return_pct": pl_pct,
        })

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    reb["timestamp"] = now_iso
    reb["total_tracked_equity_usd"] = round(sum(x["equity_usd"] for x in portfolio_snapshot), 2)
    reb["high_risk_cost_usd"] = st.HIGH_RISK_BASELINE_USD
    reb["high_risk_total_usd"] = round(sum(x["equity_usd"] for x in high_risk_snapshot), 2)
    reb["portfolio_snapshot"] = portfolio_snapshot
    reb["high_risk_snapshot"] = high_risk_snapshot

    reb_file.write_text(json.dumps(reb, indent=2), encoding="utf-8")
    st.update_daily_history(reb["total_tracked_equity_usd"])
    return reb


def main() -> None:
    print("Starting 10-second continuous Screener & Live Quote Engine...")
    cycle = 0
    while True:
        t0 = time.time()
        try:
            if cycle % 6 == 0:
                # Full screener + rebalance check every 60 seconds (every 6th 10s cycle)
                reb = st.rebalance_portfolio(dry_run=False)
                print(
                    f"[{reb['timestamp']}] FULL SCREEN & REBALANCE | "
                    f"$10k: ${reb['total_tracked_equity_usd']:.2f} | "
                    f"$1k High-Risk: ${reb['high_risk_total_usd']:.2f}"
                )
            else:
                # Fast 10-second live quote & P/L screen across all 20 positions
                reb = fast_quote_refresh()
                print(
                    f"[{reb['timestamp']}] 10s TICK | "
                    f"$10k: ${reb['total_tracked_equity_usd']:.2f} | "
                    f"$1k High-Risk: ${reb['high_risk_total_usd']:.2f}"
                )
        except Exception as exc:
            print(f"Loop error: {exc}")

        cycle += 1
        elapsed = time.time() - t0
        sleep_s = max(1.0, 10.0 - elapsed)
        time.sleep(sleep_s)


if __name__ == "__main__":
    main()
