"""
Hybrid Bot Backtester
---------------------
Tests the full hybrid strategy:
  - Grid trading on multiple pairs
  - RSI filter (pause buying when overbought, pause selling when oversold)
  - Trailing stop loss (sell everything if price drops X% from peak)

Usage:
  python hybrid_backtester.py          # 90 days
  python hybrid_backtester.py 180      # 180 days
"""

import json
import sys
from pathlib import Path
from collections import deque
from datetime import datetime

import ccxt
import pandas as pd


def load_config(path="hybrid_config.json"):
    with open(Path(__file__).parent / path) as f:
        return json.load(f)


def calc_rsi(prices, period=14):
    """Calculate RSI from a list of prices."""
    if len(prices) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def fetch_data(exchange_id, symbol, days):
    print(f"  Fetching {symbol} ({days} days)...", end=" ")
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
    print(f"{len(all_candles)} candles")
    return df


def backtest_pair(df, symbol, grid_cfg, rsi_cfg, stop_cfg):
    """Backtest one pair with all layers."""
    lower = grid_cfg["lower_price"]
    upper = grid_cfg["upper_price"]
    num_grids = grid_cfg["num_grids"]
    investment = grid_cfg["investment_usdt"]
    fee_rate = 0.001

    step = (upper - lower) / num_grids
    grid_levels = [round(lower + i * step, 2) for i in range(num_grids + 1)]
    order_size = investment / num_grids / ((lower + upper) / 2)

    # State
    balance_usdt = investment
    balance_coin = 0.0
    buy_orders = {}
    sell_orders = {}
    total_profit = 0.0
    total_fees = 0.0
    num_buys = 0
    num_sells = 0
    trades = []

    # RSI
    rsi_prices = deque(maxlen=rsi_cfg["period"] + 1)
    rsi_enabled = rsi_cfg["enabled"]

    # Trailing stop
    stop_enabled = stop_cfg["enabled"]
    stop_pct = stop_cfg["drop_percent"] / 100
    highest_price = 0
    stopped = False
    stop_events = 0

    # Place initial orders
    first_price = df["close"].iloc[0]
    highest_price = first_price
    for level in grid_levels:
        if level < first_price:
            buy_orders[level] = True
        elif level > first_price:
            sell_orders[level] = True

    for _, row in df.iterrows():
        price_close = row["close"]
        price_low = row["low"]
        price_high = row["high"]

        rsi_prices.append(price_close)
        rsi_val = calc_rsi(list(rsi_prices), rsi_cfg["period"])

        # ── Trailing stop check ──
        if stop_enabled and not stopped:
            if price_close > highest_price:
                highest_price = price_close
            drop = (highest_price - price_low) / highest_price
            if drop >= stop_pct:
                # Emergency sell all coin
                if balance_coin > 0:
                    sell_revenue = balance_coin * price_low * 0.999
                    balance_usdt += sell_revenue
                    total_fees += balance_coin * price_low * 0.001
                    trades.append({
                        "time": row["timestamp"], "side": "stop_sell",
                        "price": price_low, "amount": balance_coin,
                    })
                    balance_coin = 0
                buy_orders.clear()
                sell_orders.clear()
                stopped = True
                stop_events += 1
                continue

        # ── Recovery after stop ──
        if stopped:
            if price_close > lower:
                stopped = False
                highest_price = price_close
                for level in grid_levels:
                    if level < price_close:
                        buy_orders[level] = True
                    elif level > price_close:
                        sell_orders[level] = True
            else:
                continue

        # ── RSI filter ──
        buy_ok = (not rsi_enabled) or (rsi_val < rsi_cfg["overbought"])
        sell_ok = (not rsi_enabled) or (rsi_val > rsi_cfg["oversold"])

        # ── Check buy fills ──
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
                        "time": row["timestamp"], "side": "buy",
                        "price": level, "amount": order_size, "fee": fee, "rsi": rsi_val,
                    })
                    if sell_ok:
                        sell_orders[round(level + step, 2)] = True
        for level in filled_buys:
            del buy_orders[level]

        # ── Check sell fills ──
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
                        "time": row["timestamp"], "side": "sell",
                        "price": level, "amount": order_size, "fee": fee,
                        "profit": profit, "rsi": rsi_val,
                    })
                    if buy_ok:
                        buy_orders[round(level - step, 2)] = True
        for level in filled_sells:
            del sell_orders[level]

    final_price = df["close"].iloc[-1]
    coin_value = balance_coin * final_price
    total_value = balance_usdt + coin_value
    pnl = total_value - investment
    pnl_pct = (pnl / investment) * 100
    hodl_return = ((final_price - df["close"].iloc[0]) / df["close"].iloc[0]) * 100

    return {
        "symbol": symbol,
        "investment": investment,
        "trades": num_buys + num_sells,
        "buys": num_buys,
        "sells": num_sells,
        "grid_profit": total_profit,
        "fees": total_fees,
        "balance_usdt": balance_usdt,
        "balance_coin": balance_coin,
        "coin_value": coin_value,
        "total_value": total_value,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "hodl_return": hodl_return,
        "stop_events": stop_events,
        "all_trades": trades,
    }


def run_comparison(df, symbol, grid_cfg, rsi_cfg, stop_cfg):
    """Run the same pair with different layer combos for comparison."""
    results = {}

    # Grid only
    no_rsi = {"enabled": False, "period": 14, "overbought": 75, "oversold": 25}
    no_stop = {"enabled": False, "drop_percent": 10}
    results["grid_only"] = backtest_pair(df, symbol, grid_cfg, no_rsi, no_stop)

    # Grid + RSI
    results["grid_rsi"] = backtest_pair(df, symbol, grid_cfg, rsi_cfg, no_stop)

    # Grid + Stop
    results["grid_stop"] = backtest_pair(df, symbol, grid_cfg, no_rsi, stop_cfg)

    # Full hybrid
    results["hybrid"] = backtest_pair(df, symbol, grid_cfg, rsi_cfg, stop_cfg)

    return results


if __name__ == "__main__":
    cfg = load_config()
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 90

    print(f"\n{'='*70}")
    print(f"  HYBRID BOT BACKTEST — {days} DAYS")
    print(f"{'='*70}\n")

    # Fetch data for all pairs
    pair_data = {}
    for pair_cfg in cfg["pairs"]:
        sym = pair_cfg["symbol"]
        pair_data[sym] = fetch_data(cfg["exchange"], sym, days)

    # ─────────────────────────────────
    #  Per-pair comparison
    # ─────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  LAYER COMPARISON (each pair)")
    print(f"{'='*70}\n")

    all_hybrid_results = []

    for pair_cfg in cfg["pairs"]:
        sym = pair_cfg["symbol"]
        df = pair_data[sym]
        comp = run_comparison(df, sym, pair_cfg["grid"], cfg["rsi"], cfg["trailing_stop"])

        print(f"  {sym}")
        print(f"  {'Strategy':<20} | {'Trades':>6} | {'Grid Profit':>11} | {'Total Value':>11} | {'P&L':>14} | {'Stops':>5}")
        print(f"  {'-'*80}")
        for name, r in comp.items():
            label = {
                "grid_only": "Grid only",
                "grid_rsi": "Grid + RSI",
                "grid_stop": "Grid + Stop",
                "hybrid": "FULL HYBRID",
            }[name]
            print(
                f"  {label:<20} | {r['trades']:>6} | ${r['grid_profit']:>9.2f} | ${r['total_value']:>9.2f} | "
                f"${r['pnl']:>7.2f} ({r['pnl_pct']:>+6.1f}%) | {r['stop_events']:>5}"
            )
        print(f"  HODL return: {comp['grid_only']['hodl_return']:+.1f}%")
        print()

        all_hybrid_results.append(comp["hybrid"])

    # ─────────────────────────────────
    #  Combined portfolio result
    # ─────────────────────────────────
    total_investment = sum(r["investment"] for r in all_hybrid_results)
    total_value = sum(r["total_value"] for r in all_hybrid_results)
    total_pnl = sum(r["pnl"] for r in all_hybrid_results)
    total_pnl_pct = (total_pnl / total_investment) * 100
    total_trades = sum(r["trades"] for r in all_hybrid_results)
    total_grid_profit = sum(r["grid_profit"] for r in all_hybrid_results)
    total_fees = sum(r["fees"] for r in all_hybrid_results)
    months = days / 30

    print(f"{'='*70}")
    print(f"  COMBINED PORTFOLIO (FULL HYBRID)")
    print(f"{'='*70}")
    print(f"  Total investment:   ${total_investment:.2f}")
    print(f"  Total value:        ${total_value:.2f}")
    print(f"  Total P&L:          ${total_pnl:.2f} ({total_pnl_pct:+.2f}%)")
    print(f"  Grid profit:        ${total_grid_profit:.2f}")
    print(f"  Fees paid:          ${total_fees:.2f}")
    print(f"  Total trades:       {total_trades}")
    print()
    if total_pnl > 0:
        monthly = total_pnl / months
        monthly_roi = (monthly / total_investment) * 100
        daily = total_pnl / days
        print(f"  Monthly profit:     ${monthly:.2f}")
        print(f"  Monthly ROI:        {monthly_roi:.2f}%")
        print(f"  Daily profit:       ${daily:.2f}")
        yearly_est = monthly * 12
        print(f"  Yearly estimate:    ${yearly_est:.2f} ({(yearly_est/total_investment)*100:.1f}%)")
    else:
        print(f"  Portfolio LOST money over this period.")
    print(f"{'='*70}")

    # Per-pair breakdown
    print(f"\n  Per-pair breakdown:")
    for r in all_hybrid_results:
        print(f"    {r['symbol']:<12} ${r['investment']:>6.0f} invested → ${r['total_value']:>8.2f} | {r['pnl_pct']:>+6.1f}% | {r['trades']} trades")

    # Save all trades
    all_trades = []
    for r in all_hybrid_results:
        for t in r["all_trades"]:
            t["symbol"] = r["symbol"]
            all_trades.append(t)
    if all_trades:
        trades_df = pd.DataFrame(all_trades)
        output = Path(__file__).parent / "hybrid_backtest_results.csv"
        trades_df.to_csv(output, index=False)
        print(f"\n  Trade log saved to {output}")
