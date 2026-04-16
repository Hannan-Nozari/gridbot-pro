"""
All Strategies Backtester
--------------------------
Compares: Grid, DCA, Mean Reversion, Momentum, Combined
Side by side on all pairs for 30 and 90 days.

Usage:
  python all_strategies_backtest.py          # 90 days
  python all_strategies_backtest.py 30       # 30 days
  python all_strategies_backtest.py all      # both 30 and 90
"""

import json
import sys
from pathlib import Path

import ccxt
import pandas as pd

from strategies import (
    GridStrategy, DCAStrategy, MeanReversionStrategy,
    MomentumStrategy, CombinedStrategy
)


def load_config(path="v3_config.json"):
    with open(Path(__file__).parent / path) as f:
        return json.load(f)


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
    print(f"{len(candles)} candles")
    return df


def run_strategy(strategy, df):
    """Run any strategy against hourly data."""
    for _, row in df.iterrows():
        strategy.update(row["timestamp"], row["high"], row["low"], row["close"], row["volume"])
    final_price = df["close"].iloc[-1]
    return {
        "total_value": strategy.value(final_price),
        "total_profit": strategy.total_profit,
        "total_fees": strategy.total_fees,
        "num_trades": strategy.num_trades,
        "trades": strategy.trades,
    }


def backtest_all(df, symbol, grid_cfg, investment):
    """Run all 5 strategies on one pair."""
    first_price = df["close"].iloc[0]
    final_price = df["close"].iloc[-1]
    hodl_ret = ((final_price - first_price) / first_price) * 100

    results = {}

    # 1. Grid
    s = GridStrategy(grid_cfg["lower_price"], grid_cfg["upper_price"],
                     grid_cfg["num_grids"], investment)
    r = run_strategy(s, df)
    results["Grid"] = r

    # 2. DCA (buy every 4 hours, take profit at 3%)
    s = DCAStrategy(investment, buy_interval_hours=4, take_profit_pct=3.0, chunk_pct=2.0)
    r = run_strategy(s, df)
    results["DCA"] = r

    # 3. DCA Conservative (buy every 8h, take profit at 5%)
    s = DCAStrategy(investment, buy_interval_hours=8, take_profit_pct=5.0, chunk_pct=1.5)
    r = run_strategy(s, df)
    results["DCA Conserv"] = r

    # 4. Mean Reversion (standard)
    s = MeanReversionStrategy(investment, bb_period=20, z_entry=2.0, z_exit=0.5, position_pct=10)
    r = run_strategy(s, df)
    results["Mean Rev"] = r

    # 5. Mean Reversion (aggressive)
    s = MeanReversionStrategy(investment, bb_period=14, z_entry=1.5, z_exit=0.3, position_pct=15)
    r = run_strategy(s, df)
    results["Mean Rev Agg"] = r

    # 6. Momentum (standard)
    s = MomentumStrategy(investment, fast_ema=12, slow_ema=26, position_pct=30)
    r = run_strategy(s, df)
    results["Momentum"] = r

    # 7. Momentum (fast)
    s = MomentumStrategy(investment, fast_ema=8, slow_ema=21, position_pct=40)
    r = run_strategy(s, df)
    results["Momentum Fast"] = r

    # 8. Combined (auto-switch)
    s = CombinedStrategy(investment, grid_cfg["lower_price"], grid_cfg["upper_price"],
                         grid_cfg["num_grids"])
    r = run_strategy(s, df)
    results["COMBINED"] = r

    return results, hodl_ret


def print_results(symbol, results, hodl_ret, investment, days):
    """Pretty print results for one pair."""
    months = max(days / 30, 1)

    print(f"\n  {symbol} ({days} days)")
    print(f"  {'Strategy':<18} | {'Trades':>6} | {'Fees':>7} | {'Value':>9} | {'P&L':>16} | {'Mo.ROI':>7}")
    print(f"  {'-'*75}")

    best_name = ""
    best_pnl = -999999

    for name, r in results.items():
        pnl = r["total_value"] - investment
        pnl_pct = (pnl / investment) * 100
        monthly_roi = pnl_pct / months

        if pnl_pct > best_pnl:
            best_pnl = pnl_pct
            best_name = name

        print(
            f"  {name:<18} | {r['num_trades']:>6} | ${r['total_fees']:>5.2f} | "
            f"${r['total_value']:>7.2f} | ${pnl:>7.2f} ({pnl_pct:>+6.1f}%) | {monthly_roi:>+5.2f}%"
        )

    print(f"  {'HODL':<18} | {'—':>6} | {'—':>7} | {'—':>9} | {'':>8}({hodl_ret:>+6.1f}%) |")
    print(f"  >>> BEST: {best_name} ({best_pnl:+.1f}%)")

    return best_name, best_pnl


def run_full_backtest(days, cfg, pair_data):
    """Run complete backtest for a given number of days."""

    print(f"\n{'='*85}")
    print(f"  ALL STRATEGIES COMPARISON — {days} DAYS")
    print(f"{'='*85}")

    pair_bests = {}
    all_results = {}
    months = max(days / 30, 1)

    for pc in cfg["pairs"]:
        sym = pc["symbol"]
        inv = pc["grid"]["investment_usdt"]
        df = pair_data[sym][days]

        results, hodl_ret = backtest_all(df, sym, pc["grid"], inv)
        all_results[sym] = (results, hodl_ret, inv)
        best_name, best_pnl = print_results(sym, results, hodl_ret, inv, days)
        pair_bests[sym] = (best_name, best_pnl)

    # ── Portfolio summary ──
    strategy_names = list(list(all_results.values())[0][0].keys())

    print(f"\n{'='*85}")
    print(f"  COMBINED PORTFOLIO — {days} DAYS ($200 total)")
    print(f"{'='*85}")
    print(f"  {'Strategy':<18} | {'Value':>9} | {'P&L':>16} | {'Monthly':>10} | {'Yearly Est':>12}")
    print(f"  {'-'*75}")

    best_strat = ""
    best_total_pnl = -999999

    for strat_name in strategy_names:
        total_val = 0
        total_inv = 0
        for sym, (results, hodl_ret, inv) in all_results.items():
            total_val += results[strat_name]["total_value"]
            total_inv += inv

        pnl = total_val - total_inv
        pnl_pct = (pnl / total_inv) * 100
        monthly = pnl / months
        monthly_pct = pnl_pct / months
        yearly = monthly * 12

        if pnl_pct > best_total_pnl:
            best_total_pnl = pnl_pct
            best_strat = strat_name

        print(
            f"  {strat_name:<18} | ${total_val:>7.2f} | ${pnl:>7.2f} ({pnl_pct:>+6.1f}%) | "
            f"${monthly:>5.2f} ({monthly_pct:>+.1f}%) | ${yearly:>7.2f} ({monthly_pct*12:>+.1f}%)"
        )

    # HODL
    total_hodl_val = 0
    total_inv = 0
    for sym, (results, hodl_ret, inv) in all_results.items():
        total_hodl_val += inv * (1 + hodl_ret / 100)
        total_inv += inv
    hodl_pnl = total_hodl_val - total_inv
    print(
        f"  {'HODL':<18} | ${total_hodl_val:>7.2f} | ${hodl_pnl:>7.2f} ({(hodl_pnl/total_inv)*100:>+6.1f}%) |"
    )

    print(f"\n  >>> BEST OVERALL: {best_strat} ({best_total_pnl:+.1f}%)")

    # Best per pair
    print(f"\n  BEST PER PAIR:")
    cherry_val = 0
    cherry_inv = 0
    for sym, (best_name, best_pnl) in pair_bests.items():
        inv = [pc["grid"]["investment_usdt"] for pc in cfg["pairs"] if pc["symbol"] == sym][0]
        val = inv * (1 + best_pnl / 100)
        cherry_val += val
        cherry_inv += inv
        print(f"    {sym:<12} → {best_name:<18} ({best_pnl:+.1f}%)")
    cherry_pnl = cherry_val - cherry_inv
    cherry_monthly = cherry_pnl / months
    print(f"    {'TOTAL':<12} → ${cherry_val:.2f} ({(cherry_pnl/cherry_inv)*100:+.1f}%) | Monthly: ${cherry_monthly:.2f}")

    return all_results


if __name__ == "__main__":
    cfg = load_config()

    run_both = len(sys.argv) > 1 and sys.argv[1] == "all"
    if run_both:
        days_list = [30, 90]
    else:
        days_list = [int(sys.argv[1]) if len(sys.argv) > 1 else 90]

    max_days = max(days_list)

    print(f"\n  Fetching data ({max_days} days)...")
    pair_data = {}
    for pc in cfg["pairs"]:
        sym = pc["symbol"]
        df = fetch_data(cfg["exchange"], sym, max_days)
        pair_data[sym] = {}
        for d in days_list:
            # Take last N days of data
            cutoff = df["timestamp"].max() - pd.Timedelta(days=d)
            pair_data[sym][d] = df[df["timestamp"] >= cutoff].reset_index(drop=True)

    for days in days_list:
        run_full_backtest(days, cfg, pair_data)

    print(f"\n{'='*85}")
