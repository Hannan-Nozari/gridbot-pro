"""
Deep Strategy Analysis
-----------------------
Runs all strategies on fresh data and computes:
  - Win rate, avg profit per trade, max drawdown
  - Sharpe ratio, Sortino ratio, Calmar ratio
  - Max consecutive wins/losses
  - Profit factor
  - Optimal parameters via grid search
  - Live trading readiness assessment

Usage:
  python deep_analysis.py          # 90 days
  python deep_analysis.py 30       # 30 days
  python deep_analysis.py 365      # 1 year
"""

import json
import sys
import math
from pathlib import Path
from collections import deque
from datetime import datetime

import ccxt
import pandas as pd
import numpy as np

from strategies import (
    GridStrategy, DCAStrategy, MeanReversionStrategy,
    MomentumStrategy, CombinedStrategy
)


# ─────────────────────────────────────────
#  Config
# ─────────────────────────────────────────

PAIRS = [
    {
        "symbol": "ETH/USDT",
        "investment": 80,
        "grid": {"lower_price": 1500, "upper_price": 2500, "num_grids": 10},
    },
    {
        "symbol": "SOL/USDT",
        "investment": 60,
        "grid": {"lower_price": 50, "upper_price": 200, "num_grids": 10},
    },
    {
        "symbol": "BNB/USDT",
        "investment": 60,
        "grid": {"lower_price": 400, "upper_price": 750, "num_grids": 10},
    },
]

TOTAL_INV = sum(p["investment"] for p in PAIRS)


def fetch_data(symbol, days):
    print(f"  Fetching {symbol}...", end=" ", flush=True)
    ex = ccxt.binance({"enableRateLimit": True})
    since = ex.milliseconds() - days * 86400000
    candles = []
    while since < ex.milliseconds():
        batch = ex.fetch_ohlcv(symbol, "1h", since=since, limit=1000)
        if not batch:
            break
        candles.extend(batch)
        since = batch[-1][0] + 1
    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    print(f"{len(candles)} candles ({(df['timestamp'].iloc[-1] - df['timestamp'].iloc[0]).days}d)")
    return df


def run_strategy(strategy, df):
    """Run strategy, return trades list and final value."""
    equity_curve = []
    for _, row in df.iterrows():
        strategy.update(row["timestamp"], row["high"], row["low"], row["close"], row["volume"])
        equity_curve.append(strategy.value(row["close"]))
    final = df["close"].iloc[-1]
    return {
        "total_value": strategy.value(final),
        "total_profit": strategy.total_profit,
        "total_fees": strategy.total_fees,
        "num_trades": strategy.num_trades,
        "trades": strategy.trades,
        "equity_curve": equity_curve,
    }


def compute_metrics(result, investment, days, hourly_prices):
    """Compute deep metrics from strategy results."""
    equity = np.array(result["equity_curve"])
    trades = result["trades"]
    months = max(days / 30, 1)

    # Basic P&L
    final_value = result["total_value"]
    pnl = final_value - investment
    pnl_pct = (pnl / investment) * 100
    monthly_roi = pnl_pct / months

    # Trade analysis
    sell_trades = [t for t in trades if t.get("profit") is not None]
    buy_trades = [t for t in trades if t["side"] == "buy"]
    profits = [t["profit"] for t in sell_trades]

    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p <= 0]
    win_rate = (len(wins) / len(profits) * 100) if profits else 0
    avg_win = np.mean(wins) if wins else 0
    avg_loss = abs(np.mean(losses)) if losses else 0
    profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float('inf')
    avg_profit = np.mean(profits) if profits else 0
    max_single_profit = max(profits) if profits else 0
    max_single_loss = min(profits) if profits else 0

    # Consecutive wins/losses
    max_consec_wins = 0
    max_consec_losses = 0
    curr_wins = 0
    curr_losses = 0
    for p in profits:
        if p > 0:
            curr_wins += 1
            curr_losses = 0
            max_consec_wins = max(max_consec_wins, curr_wins)
        else:
            curr_losses += 1
            curr_wins = 0
            max_consec_losses = max(max_consec_losses, curr_losses)

    # Drawdown analysis
    peak = equity[0]
    max_dd = 0
    max_dd_pct = 0
    dd_start = 0
    max_dd_duration = 0
    curr_dd_start = 0
    in_dd = False

    for i, val in enumerate(equity):
        if val > peak:
            peak = val
            if in_dd:
                dd_duration = i - curr_dd_start
                max_dd_duration = max(max_dd_duration, dd_duration)
                in_dd = False
        dd = peak - val
        dd_pct = (dd / peak) * 100 if peak > 0 else 0
        if dd > 0 and not in_dd:
            in_dd = True
            curr_dd_start = i
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd = dd

    # Hourly returns for Sharpe/Sortino
    returns = np.diff(equity) / equity[:-1]
    returns = returns[~np.isnan(returns) & ~np.isinf(returns)]

    if len(returns) > 1 and np.std(returns) > 0:
        # Annualized (8760 hours/year)
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(8760)
        downside = returns[returns < 0]
        downside_std = np.std(downside) if len(downside) > 0 else 1e-10
        sortino = (np.mean(returns) / downside_std) * np.sqrt(8760)
    else:
        sharpe = 0
        sortino = 0

    # Calmar ratio (annualized return / max drawdown)
    annual_return = pnl_pct * (365 / days) if days > 0 else 0
    calmar = annual_return / max_dd_pct if max_dd_pct > 0 else float('inf')

    # HODL comparison
    hodl_return = ((hourly_prices[-1] - hourly_prices[0]) / hourly_prices[0]) * 100
    alpha = pnl_pct - hodl_return

    return {
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "monthly_roi": monthly_roi,
        "annual_roi_est": monthly_roi * 12,
        "num_trades": result["num_trades"],
        "num_sells": len(sell_trades),
        "num_buys": len(buy_trades),
        "win_rate": win_rate,
        "avg_profit_per_trade": avg_profit,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "max_single_profit": max_single_profit,
        "max_single_loss": max_single_loss,
        "max_consec_wins": max_consec_wins,
        "max_consec_losses": max_consec_losses,
        "max_drawdown_pct": max_dd_pct,
        "max_drawdown_usd": max_dd,
        "max_dd_duration_hours": max_dd_duration,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "total_fees": result["total_fees"],
        "fee_pct_of_profit": (result["total_fees"] / max(sum(wins), 0.01)) * 100,
        "hodl_return": hodl_return,
        "alpha_vs_hodl": alpha,
    }


def param_optimize(df, investment, pair_cfg):
    """Grid search for optimal parameters per strategy."""
    sym = pair_cfg["symbol"]
    best = {}

    # Grid optimization
    print(f"\n  Optimizing Grid for {sym}...")
    grid_results = []
    prices = df["close"].values
    price_min = prices.min()
    price_max = prices.max()
    price_mean = prices.mean()

    # Generate ranges around actual price movement
    for lower_pct in [0.85, 0.90, 0.95]:
        for upper_pct in [1.05, 1.10, 1.15]:
            for num_grids in [8, 10, 15, 20, 25]:
                lower = round(price_mean * lower_pct, 2)
                upper = round(price_mean * upper_pct, 2)
                if upper <= lower:
                    continue
                s = GridStrategy(lower, upper, num_grids, investment)
                r = run_strategy(s, df)
                val = r["total_value"]
                pnl_pct = (val - investment) / investment * 100
                grid_results.append({
                    "lower": lower, "upper": upper, "grids": num_grids,
                    "pnl_pct": pnl_pct, "trades": r["num_trades"],
                    "value": val,
                })

    if grid_results:
        best_grid = max(grid_results, key=lambda x: x["pnl_pct"])
        best["Grid"] = best_grid
        print(f"    Best: ${best_grid['lower']:.0f}-${best_grid['upper']:.0f}, "
              f"{best_grid['grids']} grids → {best_grid['pnl_pct']:+.2f}%")

    # DCA optimization
    print(f"  Optimizing DCA for {sym}...")
    dca_results = []
    for interval in [2, 4, 6, 8, 12]:
        for tp in [2.0, 3.0, 4.0, 5.0]:
            for chunk in [1.0, 1.5, 2.0, 3.0]:
                s = DCAStrategy(investment, buy_interval_hours=interval,
                                take_profit_pct=tp, chunk_pct=chunk)
                r = run_strategy(s, df)
                val = r["total_value"]
                pnl_pct = (val - investment) / investment * 100
                dca_results.append({
                    "interval": interval, "tp": tp, "chunk": chunk,
                    "pnl_pct": pnl_pct, "trades": r["num_trades"],
                })

    if dca_results:
        best_dca = max(dca_results, key=lambda x: x["pnl_pct"])
        best["DCA"] = best_dca
        print(f"    Best: interval={best_dca['interval']}h, TP={best_dca['tp']}%, "
              f"chunk={best_dca['chunk']}% → {best_dca['pnl_pct']:+.2f}%")

    # Mean Reversion optimization
    print(f"  Optimizing Mean Rev for {sym}...")
    mr_results = []
    for period in [14, 20, 30]:
        for z_entry in [1.5, 2.0, 2.5]:
            for z_exit in [0.3, 0.5, 0.8]:
                for pos_pct in [8, 10, 15, 20]:
                    s = MeanReversionStrategy(investment, bb_period=period,
                                               z_entry=z_entry, z_exit=z_exit, position_pct=pos_pct)
                    r = run_strategy(s, df)
                    val = r["total_value"]
                    pnl_pct = (val - investment) / investment * 100
                    mr_results.append({
                        "period": period, "z_entry": z_entry, "z_exit": z_exit,
                        "pos_pct": pos_pct, "pnl_pct": pnl_pct, "trades": r["num_trades"],
                    })

    if mr_results:
        best_mr = max(mr_results, key=lambda x: x["pnl_pct"])
        best["Mean Rev"] = best_mr
        print(f"    Best: period={best_mr['period']}, z_entry={best_mr['z_entry']}, "
              f"z_exit={best_mr['z_exit']}, pos={best_mr['pos_pct']}% → {best_mr['pnl_pct']:+.2f}%")

    # Momentum optimization
    print(f"  Optimizing Momentum for {sym}...")
    mom_results = []
    for fast in [8, 12, 16]:
        for slow in [21, 26, 34]:
            if fast >= slow:
                continue
            for pos_pct in [20, 30, 40, 50]:
                s = MomentumStrategy(investment, fast_ema=fast, slow_ema=slow, position_pct=pos_pct)
                r = run_strategy(s, df)
                val = r["total_value"]
                pnl_pct = (val - investment) / investment * 100
                mom_results.append({
                    "fast": fast, "slow": slow, "pos_pct": pos_pct,
                    "pnl_pct": pnl_pct, "trades": r["num_trades"],
                })

    if mom_results:
        best_mom = max(mom_results, key=lambda x: x["pnl_pct"])
        best["Momentum"] = best_mom
        print(f"    Best: fast={best_mom['fast']}, slow={best_mom['slow']}, "
              f"pos={best_mom['pos_pct']}% → {best_mom['pnl_pct']:+.2f}%")

    return best


def print_deep_report(sym, metrics, days):
    """Print detailed metrics for one strategy on one pair."""
    m = metrics
    print(f"\n  {'─'*60}")
    print(f"  {sym} — {days} days")
    print(f"  {'─'*60}")
    print(f"  {'Strategy':<16} | {'P&L':>10} | {'Mo.ROI':>7} | {'WinRate':>7} | {'Sharpe':>6} | {'MaxDD':>7} | {'PF':>5} | {'Alpha':>7}")
    print(f"  {'-'*85}")

    for name, m in metrics.items():
        pf_str = f"{m['profit_factor']:.2f}" if m['profit_factor'] != float('inf') else "∞"
        print(
            f"  {name:<16} | ${m['pnl']:>7.2f} ({m['pnl_pct']:>+5.1f}%) | "
            f"{m['monthly_roi']:>+5.2f}% | {m['win_rate']:>5.1f}% | "
            f"{m['sharpe_ratio']:>5.2f} | {m['max_drawdown_pct']:>5.2f}% | "
            f"{pf_str:>5} | {m['alpha_vs_hodl']:>+5.1f}%"
        )

    print(f"\n  HODL return: {list(metrics.values())[0]['hodl_return']:+.1f}%")


def print_detailed_breakdown(metrics_all):
    """Print per-strategy deep dive."""
    print(f"\n{'='*95}")
    print(f"  DETAILED METRICS BREAKDOWN")
    print(f"{'='*95}")

    for sym, strats in metrics_all.items():
        for name, m in strats.items():
            print(f"\n  {sym} — {name}")
            print(f"  {'─'*40}")
            print(f"  P&L:              ${m['pnl']:.2f} ({m['pnl_pct']:+.2f}%)")
            print(f"  Monthly ROI:      {m['monthly_roi']:+.3f}%")
            print(f"  Annual ROI (est): {m['annual_roi_est']:+.2f}%")
            print(f"  Total trades:     {m['num_trades']} ({m['num_buys']} buys, {m['num_sells']} sells)")
            print(f"  Win rate:         {m['win_rate']:.1f}%")
            print(f"  Avg profit/trade: ${m['avg_profit_per_trade']:.4f}")
            print(f"  Avg win:          ${m['avg_win']:.4f}")
            print(f"  Avg loss:         ${m['avg_loss']:.4f}")
            print(f"  Profit factor:    {m['profit_factor']:.2f}" if m['profit_factor'] != float('inf') else f"  Profit factor:    ∞")
            print(f"  Best trade:       ${m['max_single_profit']:.4f}")
            print(f"  Worst trade:      ${m['max_single_loss']:.4f}")
            print(f"  Max consec wins:  {m['max_consec_wins']}")
            print(f"  Max consec losses:{m['max_consec_losses']}")
            print(f"  Max drawdown:     {m['max_drawdown_pct']:.2f}% (${m['max_drawdown_usd']:.2f})")
            print(f"  DD duration:      {m['max_dd_duration_hours']} hours")
            print(f"  Sharpe ratio:     {m['sharpe_ratio']:.3f}")
            print(f"  Sortino ratio:    {m['sortino_ratio']:.3f}")
            print(f"  Calmar ratio:     {m['calmar_ratio']:.3f}")
            print(f"  Total fees:       ${m['total_fees']:.4f} ({m['fee_pct_of_profit']:.1f}% of gross profit)")
            print(f"  Alpha vs HODL:    {m['alpha_vs_hodl']:+.2f}%")


def print_live_readiness(metrics_all, opt_results):
    """Print live trading readiness assessment."""
    print(f"\n{'='*95}")
    print(f"  LIVE TRADING READINESS ASSESSMENT")
    print(f"{'='*95}")

    # Score each strategy
    scores = {}
    for sym, strats in metrics_all.items():
        for name, m in strats.items():
            key = f"{sym}|{name}"
            score = 0
            reasons = []

            # Profitability (0-25 pts)
            if m["pnl_pct"] > 5:
                score += 25
                reasons.append("Strong profit ✓")
            elif m["pnl_pct"] > 0:
                score += 15
                reasons.append("Profitable ✓")
            else:
                reasons.append("Not profitable ✗")

            # Win rate (0-20 pts)
            if m["win_rate"] > 60:
                score += 20
                reasons.append("High win rate ✓")
            elif m["win_rate"] > 45:
                score += 10
                reasons.append("Decent win rate ~")

            # Drawdown (0-20 pts)
            if m["max_drawdown_pct"] < 5:
                score += 20
                reasons.append("Low drawdown ✓")
            elif m["max_drawdown_pct"] < 10:
                score += 10
                reasons.append("Moderate drawdown ~")
            else:
                reasons.append("High drawdown ✗")

            # Sharpe (0-20 pts)
            if m["sharpe_ratio"] > 2:
                score += 20
                reasons.append("Excellent risk-adj return ✓")
            elif m["sharpe_ratio"] > 1:
                score += 10
                reasons.append("Good risk-adj return ~")
            else:
                reasons.append("Poor risk-adj return ✗")

            # Profit factor (0-15 pts)
            if m["profit_factor"] > 2:
                score += 15
                reasons.append("Strong profit factor ✓")
            elif m["profit_factor"] > 1.2:
                score += 8
                reasons.append("Decent profit factor ~")

            scores[key] = (score, reasons, m)

    # Rank and print
    ranked = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)

    print(f"\n  {'Rank':>4} | {'Strategy':>30} | {'Score':>5} | {'Grade':>5} | Assessment")
    print(f"  {'-'*95}")

    for i, (key, (score, reasons, m)) in enumerate(ranked):
        sym, name = key.split("|")
        if score >= 80:
            grade = "A"
        elif score >= 60:
            grade = "B"
        elif score >= 40:
            grade = "C"
        elif score >= 20:
            grade = "D"
        else:
            grade = "F"

        status = "READY" if score >= 60 else "CAUTION" if score >= 40 else "NOT READY"
        print(f"  {i+1:>4} | {sym + ' ' + name:>30} | {score:>5} | {grade:>5} | {status}")

    # Top recommendation
    top_key, (top_score, top_reasons, top_m) = ranked[0]
    top_sym, top_name = top_key.split("|")
    print(f"\n  TOP RECOMMENDATION: {top_sym} with {top_name} strategy (Score: {top_score}/100)")
    for r in top_reasons:
        print(f"    • {r}")

    # Optimized params recommendation
    print(f"\n  OPTIMIZED PARAMETERS:")
    for sym, params in opt_results.items():
        print(f"\n  {sym}:")
        for strat_name, p in params.items():
            print(f"    {strat_name}: {p}")


# ─────────────────────────────────────────
#  Main
# ─────────────────────────────────────────

if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 90

    print(f"\n{'='*95}")
    print(f"  DEEP STRATEGY ANALYSIS — {days} DAYS — {len(PAIRS)} PAIRS")
    print(f"  Total investment: ${TOTAL_INV}")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*95}")

    # Fetch data
    print(f"\n  Fetching fresh data...")
    pair_data = {}
    for p in PAIRS:
        pair_data[p["symbol"]] = fetch_data(p["symbol"], days)

    # Run all strategies and compute metrics
    metrics_all = {}
    opt_results = {}

    for p in PAIRS:
        sym = p["symbol"]
        inv = p["investment"]
        df = pair_data[sym]
        g = p["grid"]
        hourly_prices = df["close"].values

        strat_metrics = {}

        # Run strategies
        strategies = {
            "Grid": GridStrategy(g["lower_price"], g["upper_price"], g["num_grids"], inv),
            "DCA": DCAStrategy(inv, buy_interval_hours=4, take_profit_pct=3.0, chunk_pct=2.0),
            "DCA Conserv": DCAStrategy(inv, buy_interval_hours=8, take_profit_pct=5.0, chunk_pct=1.5),
            "Mean Rev": MeanReversionStrategy(inv, bb_period=20, z_entry=2.0, z_exit=0.5, position_pct=10),
            "Mean Rev Agg": MeanReversionStrategy(inv, bb_period=14, z_entry=1.5, z_exit=0.3, position_pct=15),
            "Momentum": MomentumStrategy(inv, fast_ema=12, slow_ema=26, position_pct=30),
            "Momentum Fast": MomentumStrategy(inv, fast_ema=8, slow_ema=21, position_pct=40),
            "COMBINED": CombinedStrategy(inv, g["lower_price"], g["upper_price"], g["num_grids"]),
        }

        for name, strat in strategies.items():
            r = run_strategy(strat, df)
            m = compute_metrics(r, inv, days, hourly_prices)
            strat_metrics[name] = m

        metrics_all[sym] = strat_metrics
        print_deep_report(sym, strat_metrics, days)

        # Parameter optimization
        opt_results[sym] = param_optimize(df, inv, p)

    # Detailed breakdown
    print_detailed_breakdown(metrics_all)

    # Portfolio combined view
    print(f"\n{'='*95}")
    print(f"  PORTFOLIO SUMMARY — ALL PAIRS COMBINED")
    print(f"{'='*95}")

    strat_names = list(list(metrics_all.values())[0].keys())
    print(f"\n  {'Strategy':<16} | {'Total P&L':>12} | {'Avg MoROI':>9} | {'Avg WR':>7} | {'Avg Sharpe':>10} | {'Worst DD':>8}")
    print(f"  {'-'*80}")

    for sname in strat_names:
        total_pnl = sum(metrics_all[sym][sname]["pnl"] for sym in metrics_all)
        avg_mo = np.mean([metrics_all[sym][sname]["monthly_roi"] for sym in metrics_all])
        avg_wr = np.mean([metrics_all[sym][sname]["win_rate"] for sym in metrics_all])
        avg_sharpe = np.mean([metrics_all[sym][sname]["sharpe_ratio"] for sym in metrics_all])
        worst_dd = max(metrics_all[sym][sname]["max_drawdown_pct"] for sym in metrics_all)
        total_inv = sum(p["investment"] for p in PAIRS)
        total_pct = (total_pnl / total_inv) * 100

        print(
            f"  {sname:<16} | ${total_pnl:>7.2f} ({total_pct:>+5.1f}%) | "
            f"{avg_mo:>+6.3f}% | {avg_wr:>5.1f}% | "
            f"{avg_sharpe:>9.3f} | {worst_dd:>6.2f}%"
        )

    # Live readiness
    print_live_readiness(metrics_all, opt_results)

    print(f"\n{'='*95}")
    print(f"  Analysis complete.")
    print(f"{'='*95}\n")
