"""
Grid Optimizer
--------------
Tests multiple grid configurations to find the best one.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

import ccxt
import pandas as pd


def fetch_data(exchange_id, symbol, days=90):
    print(f"Fetching {days} days of {symbol} data...")
    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    since = exchange.milliseconds() - days * 24 * 60 * 60 * 1000
    all_candles = []
    while since < exchange.milliseconds():
        candles = exchange.fetch_ohlcv(symbol, "1h", since=since, limit=1000)
        if not candles:
            break
        all_candles.extend(candles)
        since = candles[-1][0] + 1
    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    print(f"Got {len(all_candles)} candles\n")
    return df


def run_backtest(df, lower, upper, num_grids, investment):
    fee_rate = 0.001
    step = (upper - lower) / num_grids
    grid_levels = [round(lower + i * step, 2) for i in range(num_grids + 1)]
    order_size = investment / num_grids / ((lower + upper) / 2)

    balance_usdt = investment
    balance_coin = 0.0
    buy_orders = {}
    sell_orders = {}
    total_profit = 0.0
    total_fees = 0.0
    num_buys = 0
    num_sells = 0

    first_price = df["close"].iloc[0]
    for level in grid_levels:
        if level < first_price:
            buy_orders[level] = True
        elif level > first_price:
            sell_orders[level] = True

    for _, row in df.iterrows():
        price_low = row["low"]
        price_high = row["high"]

        filled_buys = []
        for level in list(buy_orders.keys()):
            if price_low <= level:
                cost = order_size * level
                fee = cost * fee_rate
                if balance_usdt >= cost + fee:
                    balance_usdt -= cost + fee
                    balance_coin += order_size
                    total_fees += fee
                    num_buys += 1
                    filled_buys.append(level)
                    sell_orders[round(level + step, 2)] = True
        for level in filled_buys:
            del buy_orders[level]

        filled_sells = []
        for level in list(sell_orders.keys()):
            if price_high >= level:
                revenue = order_size * level
                fee = revenue * fee_rate
                if balance_coin >= order_size:
                    balance_usdt += revenue - fee
                    balance_coin -= order_size
                    total_fees += fee
                    profit = order_size * step - (order_size * level * fee_rate * 2)
                    total_profit += profit
                    num_sells += 1
                    filled_sells.append(level)
                    buy_orders[round(level - step, 2)] = True
        for level in filled_sells:
            del sell_orders[level]

    final_price = df["close"].iloc[-1]
    total_value = balance_usdt + balance_coin * final_price
    pnl = total_value - investment
    pnl_pct = (pnl / investment) * 100

    return {
        "lower": lower,
        "upper": upper,
        "grids": num_grids,
        "step": step,
        "trades": num_buys + num_sells,
        "buys": num_buys,
        "sells": num_sells,
        "grid_profit": total_profit,
        "fees": total_fees,
        "total_value": total_value,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "monthly_roi": pnl_pct / 3,  # 90 days = 3 months
    }


if __name__ == "__main__":
    with open(Path(__file__).parent / "config.json") as f:
        cfg = json.load(f)

    df = fetch_data(cfg["exchange"], cfg["symbol"], days=90)

    # Test configurations
    configs = [
        # (lower, upper, grids)
        (1800, 2400, 10),   # original wide
        (1800, 2400, 20),   # wide, more grids
        (1800, 2400, 30),   # wide, even more grids
        (1900, 2300, 10),   # tighter range
        (1900, 2300, 20),   # tighter, more grids
        (1900, 2300, 30),   # tighter, most grids
        (1850, 2350, 15),   # medium
        (1850, 2350, 25),   # medium, more grids
        (2000, 2300, 15),   # tight around current price
        (2000, 2300, 20),   # tight, more grids
    ]

    investment = cfg["grid"]["total_investment_usdt"]
    results = []

    print(f"Testing {len(configs)} configurations with ${investment} investment...\n")
    print(f"{'Range':>14} | {'Grids':>5} | {'Step':>6} | {'Trades':>6} | {'Profit':>8} | {'P&L':>10} | {'Mo.ROI':>7}")
    print("-" * 80)

    for lower, upper, grids in configs:
        r = run_backtest(df, lower, upper, grids, investment)
        results.append(r)
        print(
            f"${r['lower']}-${r['upper']:>4} | "
            f"{r['grids']:>5} | "
            f"${r['step']:>5.1f} | "
            f"{r['trades']:>6} | "
            f"${r['grid_profit']:>7.2f} | "
            f"${r['pnl']:>7.2f} ({r['pnl_pct']:+.1f}%) | "
            f"{r['monthly_roi']:>5.2f}%"
        )

    # Find best
    best = max(results, key=lambda x: x["pnl_pct"])
    print(f"\n{'='*80}")
    print(f"  BEST CONFIG: ${best['lower']}-${best['upper']}, {best['grids']} grids, ${best['step']:.1f} step")
    print(f"  P&L: ${best['pnl']:.2f} ({best['pnl_pct']:+.2f}%)")
    print(f"  Monthly ROI: {best['monthly_roi']:.2f}%")
    print(f"  Trades: {best['trades']} ({best['buys']} buys, {best['sells']} sells)")
    print(f"{'='*80}")
