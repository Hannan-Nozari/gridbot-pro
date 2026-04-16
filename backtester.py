"""
Grid Bot Backtester
-------------------
Tests the grid strategy against real historical data.
Run this BEFORE risking real money.

Usage: python backtester.py
"""

import json
import sys
from pathlib import Path
from datetime import datetime

import ccxt
import pandas as pd


def load_config(path="config.json"):
    with open(Path(__file__).parent / path) as f:
        return json.load(f)


def fetch_historical_data(exchange_id, symbol, days=30):
    """Fetch OHLCV candles from exchange."""
    print(f"Fetching {days} days of {symbol} data from {exchange_id}...")
    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})

    since = exchange.milliseconds() - days * 24 * 60 * 60 * 1000
    all_candles = []
    timeframe = "1h"

    while since < exchange.milliseconds():
        candles = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not candles:
            break
        all_candles.extend(candles)
        since = candles[-1][0] + 1
        print(f"  Fetched {len(all_candles)} candles...", end="\r")

    print(f"\n  Got {len(all_candles)} hourly candles")

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def backtest(df, config):
    """Run grid strategy on historical data."""
    grid_cfg = config["grid"]
    lower = grid_cfg["lower_price"]
    upper = grid_cfg["upper_price"]
    num_grids = grid_cfg["num_grids"]
    investment = grid_cfg["total_investment_usdt"]
    fee_rate = 0.001  # 0.1%

    step = (upper - lower) / num_grids
    grid_levels = [round(lower + i * step, 2) for i in range(num_grids + 1)]
    order_size = investment / num_grids / ((lower + upper) / 2)

    print(f"\n{'='*50}")
    print(f"  BACKTEST: {config['symbol']}")
    print(f"  Grid: ${lower} - ${upper}, {num_grids} levels")
    print(f"  Step: ${step:.2f}")
    print(f"  Order size: {order_size:.6f}")
    print(f"  Investment: ${investment}")
    print(f"  Period: {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
    print(f"{'='*50}\n")

    # Track state
    balance_usdt = investment
    balance_coin = 0.0
    buy_orders = {}   # level -> True if active
    sell_orders = {}
    total_profit = 0.0
    total_fees = 0.0
    trades = []
    num_buys = 0
    num_sells = 0

    # Place initial orders based on first price
    first_price = df["close"].iloc[0]
    for level in grid_levels:
        if level < first_price:
            buy_orders[level] = True
        elif level > first_price:
            sell_orders[level] = True

    # Simulate
    for _, row in df.iterrows():
        price_low = row["low"]
        price_high = row["high"]

        # Check buy fills (price went down to level)
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
                    trades.append({
                        "time": row["timestamp"],
                        "side": "buy",
                        "price": level,
                        "amount": order_size,
                        "fee": fee,
                    })
                    # Place sell one level up
                    sell_level = level + step
                    sell_orders[round(sell_level, 2)] = True

        for level in filled_buys:
            del buy_orders[level]

        # Check sell fills (price went up to level)
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
                    trades.append({
                        "time": row["timestamp"],
                        "side": "sell",
                        "price": level,
                        "amount": order_size,
                        "fee": fee,
                        "profit": profit,
                    })
                    # Place buy one level down
                    buy_level = level - step
                    buy_orders[round(buy_level, 2)] = True

        for level in filled_sells:
            del sell_orders[level]

    # Final summary
    final_price = df["close"].iloc[-1]
    coin_value = balance_coin * final_price
    total_value = balance_usdt + coin_value
    pnl = total_value - investment
    pnl_pct = (pnl / investment) * 100
    hodl_return = ((final_price - df["close"].iloc[0]) / df["close"].iloc[0]) * 100

    print(f"{'='*50}")
    print(f"  RESULTS")
    print(f"{'='*50}")
    print(f"  Total trades:     {num_buys + num_sells} ({num_buys} buys, {num_sells} sells)")
    print(f"  Grid profit:      ${total_profit:.4f}")
    print(f"  Total fees:       ${total_fees:.4f}")
    print(f"  ")
    print(f"  Final USDT:       ${balance_usdt:.2f}")
    print(f"  Final coin:       {balance_coin:.6f} (${coin_value:.2f})")
    print(f"  Total value:      ${total_value:.2f}")
    print(f"  ")
    print(f"  P&L:              ${pnl:.2f} ({pnl_pct:+.2f}%)")
    print(f"  vs HODL:          {hodl_return:+.2f}%")
    print(f"  Bot vs HODL:      {pnl_pct - hodl_return:+.2f}%")
    print(f"{'='*50}")

    if pnl > 0:
        daily = pnl / max(len(df) / 24, 1)
        monthly = daily * 30
        print(f"\n  Estimated daily:   ${daily:.2f}")
        print(f"  Estimated monthly: ${monthly:.2f}")
        print(f"  Monthly ROI:       {(monthly/investment)*100:.2f}%")
    else:
        print(f"\n  Strategy LOST money in this period.")
        print(f"  Consider adjusting grid range or choosing a different pair.")

    return trades


if __name__ == "__main__":
    cfg = load_config()

    days = 30
    if len(sys.argv) > 1:
        days = int(sys.argv[1])

    df = fetch_historical_data(cfg["exchange"], cfg["symbol"], days=days)
    trades = backtest(df, cfg)

    # Save trades to CSV
    if trades:
        trades_df = pd.DataFrame(trades)
        output = Path(__file__).parent / "backtest_results.csv"
        trades_df.to_csv(output, index=False)
        print(f"\n  Trade log saved to {output}")
