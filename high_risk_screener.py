import json
import math
from pathlib import Path
from typing import Any

import robin_stocks.robinhood as rh
import robinhood_agent as ra
import screener_trader as st

UNDER_10_UNIVERSE = [
    "ACHR", "JOBY", "BBAI", "SOUN", "SERV", "EVGO", "NIO", "XPEV",
    "OPFI", "RPAY", "PAYO", "PSFE", "UWMC", "CLOV", "TDOC", "IOVA",
    "RXRX", "ENVX", "QS", "SLDP", "FLNC", "EOSE", "ARRY", "SHLS",
    "RUN", "SGML", "UUUU", "DNN", "UEC", "NXE", "BTG", "EXK",
    "FSM", "SVM", "RIG", "BORR", "KOS", "SPIR", "RDW", "LUNR",
    "GOGO", "KOPN", "AEVA", "NVTS", "BB", "NOK", "YEXT", "FUBO",
    "CURI", "SNAP", "BMBL", "ANGI", "GRAB", "JMIA", "WB", "FINV",
    "QFIN", "MARA", "CLSK", "CIFR", "BTDR",
]


def screen_under_10() -> list[dict[str, Any]]:
    ra.ensure_login()
    quotes = rh.stocks.get_quotes(UNDER_10_UNIVERSE) or []
    funds = rh.stocks.get_fundamentals(UNDER_10_UNIVERSE) or []
    q_map = {q["symbol"]: q for q in quotes if q and q.get("symbol")}
    f_map = {UNDER_10_UNIVERSE[i]: f for i, f in enumerate(funds) if f}

    results = []
    for sym in UNDER_10_UNIVERSE:
        q = q_map.get(sym, {})
        f = f_map.get(sym, {})
        price = float(q.get("last_trade_price") or 0)
        if not (1.50 <= price <= 10.00):
            continue

        mcap = float(f.get("market_cap") or 0)
        if mcap < 500_000_000:  # Require >= $500M market cap to limit downside/bankruptcy risk
            continue

        pe_raw = f.get("pe_ratio")
        pe = float(pe_raw) if pe_raw is not None else None
        div_raw = f.get("dividend_yield")
        div_yield = float(div_raw) if div_raw is not None else 0.0

        hist = rh.stocks.get_stock_historicals(sym, interval="day", span="year", bounds="regular") or []
        closes = [float(b["close_price"]) for b in hist if b.get("close_price")]
        if len(closes) < 60:
            continue

        high_52w = max(closes)
        low_52w = min(closes)
        sma_50 = sum(closes[-50:]) / 50.0
        sma_200 = sum(closes[-200:]) / len(closes[-200:])
        rsi_14 = st.compute_rsi(closes, 14)

        # Upside potential to 52-week high (%)
        upside_to_high_pct = ((high_52w / price) - 1.0) * 100.0
        # Cushion above 52-week low (%)
        above_low_pct = ((price / low_52w) - 1.0) * 100.0
        ret_3m = ((price / closes[-63]) - 1.0) * 100.0 if len(closes) >= 63 else 0.0

        # Daily returns series for institutional quantitative factor analysis
        daily_returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes))
        ]
        rets = daily_returns[-60:]
        mean_r = sum(rets) / len(rets)
        var_r = sum((r - mean_r) ** 2 for r in rets) / max(1, len(rets) - 1)
        vol = math.sqrt(var_r) * math.sqrt(252) * 100.0

        # Annualized Sharpe Ratio & Sortino Ratio (downside semi-deviation, Rf = 4.25%)
        rf_daily = 0.0425 / 252.0
        mean_daily = sum(daily_returns) / len(daily_returns)
        std_daily = math.sqrt(sum((r - mean_daily) ** 2 for r in daily_returns) / max(1, len(daily_returns) - 1))
        downside_sq = [min(0.0, r - rf_daily) ** 2 for r in daily_returns]
        downside_dev = math.sqrt(sum(downside_sq) / max(1, len(downside_sq)))

        sharpe_ratio = ((mean_daily - rf_daily) / std_daily) * math.sqrt(252) if std_daily > 0 else 0.0
        sortino_ratio = ((mean_daily - rf_daily) / downside_dev) * math.sqrt(252) if downside_dev > 0 else 0.0

        # Maximum Drawdown (MDD) & Fama-French 6-1 Month Momentum (skipping 21-day reversal window)
        peak = closes[0]
        max_drawdown_pct = 0.0
        for c in closes:
            if c > peak:
                peak = c
            dd = ((c - peak) / peak) * 100.0
            if dd < max_drawdown_pct:
                max_drawdown_pct = dd

        price_1m_ago = closes[-21] if len(closes) >= 21 else price
        mom_6_1_pct = ((price_1m_ago / closes[-126]) - 1.0) * 100.0 if len(closes) >= 126 else 0.0
        earnings_yield_pct = (100.0 / pe) if (pe and pe > 0) else 0.0
        asymmetric_ratio = upside_to_high_pct / max(10.0, abs(max_drawdown_pct))

        # Institutional Multi-Factor Asymmetric Quant Score:
        # 1. Quality / Earnings Yield (Asness QMJ: profitable companies 0 < P/E <= 35)
        # 2. Sortino & Sharpe Risk-Adjusted Return Efficiency
        # 3. Fama-French 6-1 Cross-Sectional Momentum + Asymmetric Upside-to-Drawdown Ratio
        # 4. Trend Regime (50-SMA & 200-SMA) + Mean-Reversion RSI Filter (35-65)
        # 5. Low-Volatility / Drawdown Control (Frazzini-Pedersen BAB)
        score = 30.0
        if pe and 0 < pe <= 35:
            score += 26.0 + min(12.0, earnings_yield_pct * 1.2)
        elif pe and pe > 35:
            score += 12.0

        score += max(-10.0, min(16.0, sortino_ratio * 5.0))
        score += max(-6.0, min(10.0, sharpe_ratio * 4.0))
        score += max(-8.0, min(14.0, mom_6_1_pct * 0.20))
        score += min(30.0, upside_to_high_pct * 0.25 + asymmetric_ratio * 4.0)
        if price >= sma_200:
            score += 14.0
        if price >= sma_50:
            score += 10.0
        if 35.0 <= rsi_14 <= 65.0:
            score += 10.0
        if mcap >= 2_000_000_000:
            score += 10.0  # Multi-billion market cap downside cushion
        if vol < 65.0:
            score += (65.0 - vol) * 0.3

        results.append({
            "symbol": sym,
            "price": round(price, 2),
            "market_cap_b": round(mcap / 1e9, 2),
            "pe_ratio": round(pe, 2) if pe else None,
            "earnings_yield_pct": round(earnings_yield_pct, 2),
            "div_yield": round(div_yield, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "sortino_ratio": round(sortino_ratio, 2),
            "mom_6_1_pct": round(mom_6_1_pct, 1),
            "max_drawdown_pct": round(max_drawdown_pct, 1),
            "asymmetric_ratio": round(asymmetric_ratio, 2),
            "rsi_14": round(rsi_14, 1),
            "sma_50": round(sma_50, 2),
            "sma_200": round(sma_200, 2),
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "upside_to_52w_high_pct": round(upside_to_high_pct, 1),
            "vol_60d_pct": round(vol, 1),
            "ret_3m_pct": round(ret_3m, 1),
            "score": round(score, 2),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


if __name__ == "__main__":
    ranked = screen_under_10()
    print(json.dumps(ranked[:15], indent=2))
