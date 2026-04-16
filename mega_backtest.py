"""
Mega Backtest — All Strategies × All Pairs × 365 Days
------------------------------------------------------
Pairs: BTC, ETH, SOL, BNB, XRP, DOGE
Strategies: Grid, DCA, Mean Reversion, Momentum, Combined

Usage:
  python mega_backtest.py
"""

import json
import sys
from pathlib import Path
from collections import deque

import ccxt
import pandas as pd

from strategies import (
    GridStrategy, DCAStrategy, MeanReversionStrategy,
    MomentumStrategy, CombinedStrategy
)


# ──────────────────────────────────────────────
#  Pair configs — grid ranges tuned per coin
# ──────────────────────────────────────────────

PAIRS = [
    {
        "symbol": "BTC/USDT",
        "investment": 50,
        "grid": {"lower_price": 50000, "upper_price": 110000, "num_grids": 12}
    },
    {
        "symbol": "ETH/USDT",
        "investment": 40,
        "grid": {"lower_price": 1500, "upper_price": 4500, "num_grids": 12}
    },
    {
        "symbol": "SOL/USDT",
        "investment": 30,
        "grid": {"lower_price": 50, "upper_price": 300, "num_grids": 10}
    },
    {
        "symbol": "BNB/USDT",
        "investment": 30,
        "grid": {"lower_price": 400, "upper_price": 800, "num_grids": 10}
    },
    {
        "symbol": "XRP/USDT",
        "investment": 25,
        "grid": {"lower_price": 0.40, "upper_price": 3.50, "num_grids": 10}
    },
    {
        "symbol": "DOGE/USDT",
        "investment": 25,
        "grid": {"lower_price": 0.05, "upper_price": 0.50, "num_grids": 10}
    },
]

TOTAL_INVESTMENT = sum(p["investment"] for p in PAIRS)


def fetch_data(exchange_id, symbol, days):
    print(f"  {symbol}...", end=" ", flush=True)
    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    since = exchange.milliseconds() - days * 24 * 60 * 60 * 1000
    candles = []
    while since < exchange.milliseconds():
        batch = exchange.fetch_ohlcv(symbol, "1h", since=since, limit=1000)
        if not batch:
            break
        candles.extend(batch)
        since = batch[-1][0] + 1
    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    actual_days = (df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]).days
    print(f"{len(candles)} candles ({actual_days} days)")
    return df


def run_strategy(strategy, df):
    for _, row in df.iterrows():
        strategy.update(row["timestamp"], row["high"], row["low"], row["close"], row["volume"])
    final_price = df["close"].iloc[-1]
    return {
        "total_value": strategy.value(final_price),
        "total_profit": strategy.total_profit,
        "total_fees": strategy.total_fees,
        "num_trades": strategy.num_trades,
    }


def backtest_pair(df, pair_cfg):
    """Run all strategies on one pair."""
    sym = pair_cfg["symbol"]
    inv = pair_cfg["investment"]
    g = pair_cfg["grid"]
    first_price = df["close"].iloc[0]
    final_price = df["close"].iloc[-1]
    hodl_ret = ((final_price - first_price) / first_price) * 100

    results = {}

    # Grid
    s = GridStrategy(g["lower_price"], g["upper_price"], g["num_grids"], inv)
    results["Grid"] = run_strategy(s, df)

    # DCA
    s = DCAStrategy(inv, buy_interval_hours=6, take_profit_pct=4.0, chunk_pct=1.0)
    results["DCA"] = run_strategy(s, df)

    # Mean Reversion
    s = MeanReversionStrategy(inv, bb_period=20, z_entry=2.0, z_exit=0.5, position_pct=10)
    results["Mean Rev"] = run_strategy(s, df)

    # Momentum
    s = MomentumStrategy(inv, fast_ema=12, slow_ema=26, position_pct=30)
    results["Momentum"] = run_strategy(s, df)

    # Combined
    s = CombinedStrategy(inv, g["lower_price"], g["upper_price"], g["num_grids"])
    results["Combined"] = run_strategy(s, df)

    return results, hodl_ret, first_price, final_price


if __name__ == "__main__":
    days = 365
    print(f"\n{'='*95}")
    print(f"  MEGA BACKTEST — {days} DAYS — 6 PAIRS — 5 STRATEGIES")
    print(f"  Total investment: ${TOTAL_INVESTMENT}")
    print(f"{'='*95}")

    print(f"\n  Fetching 1 year of data...")
    pair_data = {}
    for p in PAIRS:
        pair_data[p["symbol"]] = fetch_data("binance", p["symbol"], days)

    # ─────────────────────────────────
    #  Per pair results
    # ─────────────────────────────────
    all_results = {}
    pair_hodl = {}
    pair_prices = {}
    strategy_names = ["Grid", "DCA", "Mean Rev", "Momentum", "Combined"]

    for p in PAIRS:
        sym = p["symbol"]
        inv = p["investment"]
        df = pair_data[sym]
        results, hodl_ret, first_p, final_p = backtest_pair(df, p)
        all_results[sym] = results
        pair_hodl[sym] = hodl_ret
        pair_prices[sym] = (first_p, final_p)

        print(f"\n  {sym}  (${first_p:.4f} → ${final_p:.4f} | HODL: {hodl_ret:+.1f}%)")
        print(f"  {'Strategy':<14} | {'Trades':>6} | {'Fees':>7} | {'Value':>9} | {'P&L':>16} | {'Mo.ROI':>8}")
        print(f"  {'-'*75}")

        best_name = ""
        best_pnl = -999999
        for name in strategy_names:
            r = results[name]
            pnl = r["total_value"] - inv
            pnl_pct = (pnl / inv) * 100
            mo_roi = pnl_pct / 12

            if pnl_pct > best_pnl:
                best_pnl = pnl_pct
                best_name = name

            print(
                f"  {name:<14} | {r['num_trades']:>6} | ${r['total_fees']:>5.2f} | "
                f"${r['total_value']:>7.2f} | ${pnl:>7.2f} ({pnl_pct:>+6.1f}%) | {mo_roi:>+6.2f}%"
            )
        print(f"  >>> BEST: {best_name} ({best_pnl:+.1f}%)")

    # ─────────────────────────────────
    #  Portfolio totals per strategy
    # ─────────────────────────────────
    print(f"\n{'='*95}")
    print(f"  COMBINED PORTFOLIO — ALL 6 PAIRS — 365 DAYS")
    print(f"  Investment: ${TOTAL_INVESTMENT}")
    print(f"{'='*95}")

    print(f"\n  {'Strategy':<14} | {'Value':>9} | {'P&L':>16} | {'Monthly':>12} | {'Yearly':>12}")
    print(f"  {'-'*75}")

    best_strat = ""
    best_total_pnl_pct = -999999

    for name in strategy_names:
        total_val = sum(all_results[p["symbol"]][name]["total_value"] for p in PAIRS)
        total_trades = sum(all_results[p["symbol"]][name]["num_trades"] for p in PAIRS)
        total_fees = sum(all_results[p["symbol"]][name]["total_fees"] for p in PAIRS)
        pnl = total_val - TOTAL_INVESTMENT
        pnl_pct = (pnl / TOTAL_INVESTMENT) * 100
        monthly = pnl / 12
        monthly_pct = pnl_pct / 12

        if pnl_pct > best_total_pnl_pct:
            best_total_pnl_pct = pnl_pct
            best_strat = name

        print(
            f"  {name:<14} | ${total_val:>7.2f} | ${pnl:>7.2f} ({pnl_pct:>+6.1f}%) | "
            f"${monthly:>6.2f} ({monthly_pct:>+.1f}%) | ${pnl:>7.2f} ({pnl_pct:>+.1f}%)"
        )

    # HODL
    hodl_val = sum(p["investment"] * (1 + pair_hodl[p["symbol"]] / 100) for p in PAIRS)
    hodl_pnl = hodl_val - TOTAL_INVESTMENT
    print(
        f"  {'HODL':<14} | ${hodl_val:>7.2f} | ${hodl_pnl:>7.2f} ({(hodl_pnl/TOTAL_INVESTMENT)*100:>+6.1f}%) |"
    )

    print(f"\n  >>> BEST STRATEGY: {best_strat} ({best_total_pnl_pct:+.1f}%)")

    # ─────────────────────────────────
    #  Best per pair (cherry picked)
    # ─────────────────────────────────
    print(f"\n  BEST STRATEGY PER PAIR:")
    print(f"  {'Pair':<14} | {'Best Strategy':<14} | {'Value':>9} | {'P&L':>14} | {'Mo.ROI':>8}")
    print(f"  {'-'*70}")

    cherry_val = 0
    cherry_inv = 0
    for p in PAIRS:
        sym = p["symbol"]
        inv = p["investment"]
        best_name = ""
        best_pnl_pct = -999999
        best_val = 0
        for name in strategy_names:
            v = all_results[sym][name]["total_value"]
            pnl_pct = (v - inv) / inv * 100
            if pnl_pct > best_pnl_pct:
                best_pnl_pct = pnl_pct
                best_name = name
                best_val = v
        cherry_val += best_val
        cherry_inv += inv
        mo_roi = best_pnl_pct / 12
        print(
            f"  {sym:<14} | {best_name:<14} | ${best_val:>7.2f} | "
            f"${best_val - inv:>6.2f} ({best_pnl_pct:>+6.1f}%) | {mo_roi:>+6.2f}%"
        )

    cherry_pnl = cherry_val - cherry_inv
    cherry_pct = (cherry_pnl / cherry_inv) * 100
    cherry_monthly = cherry_pnl / 12
    print(f"  {'-'*70}")
    print(
        f"  {'TOTAL':<14} | {'cherry-pick':<14} | ${cherry_val:>7.2f} | "
        f"${cherry_pnl:>6.2f} ({cherry_pct:>+6.1f}%) | {cherry_pct/12:>+6.2f}%"
    )
    print(f"  Monthly profit: ${cherry_monthly:.2f} | Yearly: ${cherry_pnl:.2f}")

    # ─────────────────────────────────
    #  Per pair price summary
    # ─────────────────────────────────
    print(f"\n  PRICE CHANGES (365 days):")
    for p in PAIRS:
        sym = p["symbol"]
        fp, lp = pair_prices[sym]
        ch = pair_hodl[sym]
        print(f"    {sym:<14} ${fp:>10.4f} → ${lp:>10.4f}  ({ch:>+7.1f}%)")

    print(f"\n{'='*95}")

    # ─────────────────────────────────
    #  Scaling projections
    # ─────────────────────────────────
    if best_total_pnl_pct > 0:
        print(f"\n  SCALING PROJECTIONS (using {best_strat} strategy):")
        print(f"  {'Capital':>10} | {'Monthly':>10} | {'Yearly':>10}")
        print(f"  {'-'*40}")
        for capital in [200, 500, 1000, 2000, 5000]:
            monthly = capital * (best_total_pnl_pct / 100) / 12
            yearly = capital * (best_total_pnl_pct / 100)
            print(f"  ${capital:>9} | ${monthly:>8.2f} | ${yearly:>8.2f}")
        print(f"\n  Note: returns don't scale linearly forever — liquidity")
        print(f"  becomes an issue above ~$10k on small-cap pairs.")

    print(f"\n{'='*95}")
