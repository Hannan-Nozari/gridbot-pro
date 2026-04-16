"""
Smart Bot Backtester
--------------------
Tests all 4 layers individually and combined:
  1. Volatility-adaptive grid
  2. Multi-timeframe trend filter
  3. Volume spike filter
  4. Dynamic take-profit

Usage:
  python smart_backtester.py          # 90 days
  python smart_backtester.py 30       # 30 days
"""

import json
import sys
from pathlib import Path
from collections import deque

import ccxt
import pandas as pd


def load_config(path="smart_config.json"):
    with open(Path(__file__).parent / path) as f:
        return json.load(f)


# ──────────────────────────────────────────────
#  Indicators (same as smart_bot.py)
# ──────────────────────────────────────────────

def calc_atr(highs, lows, closes, period=14):
    if len(highs) < period + 1:
        return None
    trs = []
    for i in range(1, len(highs)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        trs.append(tr)
    return sum(trs[-period:]) / period


def calc_ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return ema


def detect_trend(closes_daily):
    if len(closes_daily) < 21:
        return "neutral"
    ema_fast = calc_ema(closes_daily, 7)
    ema_slow = calc_ema(closes_daily, 21)
    if ema_fast is None or ema_slow is None:
        return "neutral"
    diff_pct = (ema_fast - ema_slow) / ema_slow * 100
    if diff_pct > 1.0:
        return "up"
    elif diff_pct < -1.0:
        return "down"
    return "neutral"


def calc_momentum(closes, period=10):
    if len(closes) < period + 1:
        return 0
    return (closes[-1] - closes[-period-1]) / closes[-period-1] * 100


# ──────────────────────────────────────────────
#  Data fetching
# ──────────────────────────────────────────────

def fetch_data(exchange_id, symbol, days):
    print(f"  Fetching {symbol} ({days}d)...", end=" ")
    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})

    # 1h candles
    since = exchange.milliseconds() - days * 24 * 60 * 60 * 1000
    candles_1h = []
    while since < exchange.milliseconds():
        batch = exchange.fetch_ohlcv(symbol, "1h", since=since, limit=1000)
        if not batch:
            break
        candles_1h.extend(batch)
        since = batch[-1][0] + 1

    df_1h = pd.DataFrame(candles_1h, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df_1h["timestamp"] = pd.to_datetime(df_1h["timestamp"], unit="ms")

    # 1d candles (for trend)
    since_d = exchange.milliseconds() - (days + 30) * 24 * 60 * 60 * 1000
    candles_1d = exchange.fetch_ohlcv(symbol, "1d", since=since_d, limit=1000)
    df_1d = pd.DataFrame(candles_1d, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df_1d["timestamp"] = pd.to_datetime(df_1d["timestamp"], unit="ms")

    print(f"{len(candles_1h)} 1h + {len(candles_1d)} 1d candles")
    return df_1h, df_1d


# ──────────────────────────────────────────────
#  Backtest engine
# ──────────────────────────────────────────────

def backtest_pair(df_1h, df_1d, symbol, grid_cfg, vol_cfg, trend_cfg, volume_cfg, tp_cfg):
    """Full backtest for one pair with all configurable layers."""

    base_lower = grid_cfg["lower_price"]
    base_upper = grid_cfg["upper_price"]
    num_grids = grid_cfg["num_grids"]
    investment = grid_cfg["investment_usdt"]
    fee_rate = 0.001

    # Current grid state
    lower = base_lower
    upper = base_upper
    step = (upper - lower) / num_grids

    def grid_levels():
        return [round(lower + i * step, 2) for i in range(num_grids + 1)]

    def order_size():
        return investment / num_grids / ((lower + upper) / 2)

    # State
    balance_usdt = investment
    balance_coin = 0.0
    buy_orders = {}     # level -> amount
    sell_orders = {}    # level -> amount
    total_profit = 0.0
    total_fees = 0.0
    num_buys = 0
    num_sells = 0
    trades = []
    grid_updates = 0
    volume_pauses = 0
    trend_adjustments = 0

    # Indicator history
    hourly_highs = deque(maxlen=100)
    hourly_lows = deque(maxlen=100)
    hourly_closes = deque(maxlen=100)
    hourly_volumes = deque(maxlen=100)

    # Build daily close lookup
    daily_closes_list = list(df_1d["close"])
    daily_dates = list(df_1d["timestamp"].dt.date)

    # Place initial orders
    first_price = df_1h["close"].iloc[0]
    amt = order_size()
    for lvl in grid_levels():
        if lvl < first_price:
            buy_orders[lvl] = amt
        elif lvl > first_price:
            sell_orders[lvl] = amt

    last_grid_rebuild_idx = 0

    for idx, row in df_1h.iterrows():
        price_close = row["close"]
        price_low = row["low"]
        price_high = row["high"]

        hourly_highs.append(row["high"])
        hourly_lows.append(row["low"])
        hourly_closes.append(row["close"])
        hourly_volumes.append(row["volume"])

        # ── Layer 3: Volume spike filter ──
        if volume_cfg["enabled"] and len(hourly_volumes) >= volume_cfg["lookback"]:
            vols = list(hourly_volumes)
            avg_vol = sum(vols[:-1]) / max(len(vols) - 1, 1)
            if avg_vol > 0 and vols[-1] / avg_vol > volume_cfg["spike_threshold"]:
                volume_pauses += 1
                continue  # skip this candle entirely

        # ── Layer 2: Trend bias ──
        buy_mult = 1.0
        sell_mult = 1.0
        if trend_cfg["enabled"]:
            current_date = row["timestamp"].date()
            # Get daily closes up to current date
            dc = [daily_closes_list[i] for i, d in enumerate(daily_dates) if d <= current_date]
            if len(dc) >= 21:
                trend = detect_trend(dc)
                if trend == "up":
                    buy_mult = trend_cfg["uptrend_buy_mult"]
                    sell_mult = trend_cfg["uptrend_sell_mult"]
                    trend_adjustments += 1
                elif trend == "down":
                    buy_mult = trend_cfg["downtrend_buy_mult"]
                    sell_mult = trend_cfg["downtrend_sell_mult"]
                    trend_adjustments += 1

        # ── Layer 1: Volatility-adaptive grid ──
        if vol_cfg["enabled"] and len(hourly_highs) >= vol_cfg["atr_period"] + 1:
            rebuild_interval = vol_cfg["update_every_hours"]
            if idx - last_grid_rebuild_idx >= rebuild_interval:
                atr = calc_atr(list(hourly_highs), list(hourly_lows), list(hourly_closes), vol_cfg["atr_period"])
                if atr is not None:
                    atr_pct = atr / price_close
                    base_range = base_upper - base_lower
                    vol_mult = max(0.5, min(2.0, atr_pct * vol_cfg["sensitivity"]))
                    half_range = (base_range * vol_mult) / 2
                    new_lower = round(price_close - half_range, 2)
                    new_upper = round(price_close + half_range, 2)

                    if abs(new_lower - lower) / max(lower, 1) > 0.02:
                        lower = new_lower
                        upper = new_upper
                        step = (upper - lower) / num_grids
                        grid_updates += 1

                        # Rebuild orders
                        buy_orders.clear()
                        sell_orders.clear()
                        amt = order_size()
                        for lvl in grid_levels():
                            if lvl < price_close:
                                buy_orders[lvl] = round(amt * buy_mult, 6)
                            elif lvl > price_close:
                                sell_orders[lvl] = round(amt * sell_mult, 6)
                        last_grid_rebuild_idx = idx

        # ── Layer 4: Dynamic take-profit ──
        tp_levels = 1
        if tp_cfg["enabled"] and len(hourly_closes) > tp_cfg["momentum_period"]:
            mom = calc_momentum(list(hourly_closes), tp_cfg["momentum_period"])
            if abs(mom) > tp_cfg["strong_momentum_pct"]:
                tp_levels = tp_cfg["strong_skip_levels"]
            elif abs(mom) > tp_cfg["mild_momentum_pct"]:
                tp_levels = tp_cfg["mild_skip_levels"]

        # ── Check buy fills ──
        filled_buys = []
        for level, amt in list(buy_orders.items()):
            if price_low <= level:
                cost = amt * level
                fee = cost * fee_rate
                if balance_usdt >= cost + fee:
                    balance_usdt -= cost + fee
                    balance_coin += amt
                    total_fees += fee
                    num_buys += 1
                    filled_buys.append(level)
                    trades.append({
                        "time": row["timestamp"], "side": "buy", "price": level,
                        "amount": amt, "fee": fee,
                    })
                    # Place sell tp_levels steps above
                    sell_price = round(level + step * tp_levels, 2)
                    sell_amt = round(amt * sell_mult, 6)
                    if sell_amt > 0:
                        sell_orders[sell_price] = sell_amt
        for level in filled_buys:
            del buy_orders[level]

        # ── Check sell fills ──
        filled_sells = []
        for level, amt in list(sell_orders.items()):
            if price_high >= level:
                if balance_coin >= amt:
                    revenue = amt * level
                    fee = revenue * fee_rate
                    balance_usdt += revenue - fee
                    balance_coin -= amt
                    total_fees += fee
                    profit = amt * step * tp_levels * 0.998
                    total_profit += profit
                    num_sells += 1
                    filled_sells.append(level)
                    trades.append({
                        "time": row["timestamp"], "side": "sell", "price": level,
                        "amount": amt, "fee": fee, "profit": profit,
                    })
                    buy_price = round(level - step, 2)
                    buy_amt = round(order_size() * buy_mult, 6)
                    if buy_amt > 0:
                        buy_orders[buy_price] = buy_amt
        for level in filled_sells:
            del sell_orders[level]

    # Final
    final_price = df_1h["close"].iloc[-1]
    coin_value = balance_coin * final_price
    total_value = balance_usdt + coin_value
    pnl = total_value - investment
    pnl_pct = (pnl / investment) * 100
    hodl_return = ((final_price - df_1h["close"].iloc[0]) / df_1h["close"].iloc[0]) * 100

    return {
        "symbol": symbol,
        "investment": investment,
        "trades": num_buys + num_sells,
        "buys": num_buys,
        "sells": num_sells,
        "grid_profit": total_profit,
        "fees": total_fees,
        "total_value": total_value,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "hodl_return": hodl_return,
        "grid_updates": grid_updates,
        "volume_pauses": volume_pauses,
        "trend_adjustments": trend_adjustments,
        "all_trades": trades,
    }


def run_all_combos(df_1h, df_1d, symbol, grid_cfg, vol_cfg, trend_cfg, volume_cfg, tp_cfg):
    """Test every layer combination."""
    OFF_VOL = {"enabled": False, "atr_period": 14, "sensitivity": 50, "update_every_hours": 4}
    OFF_TREND = {"enabled": False, "uptrend_buy_mult": 1, "uptrend_sell_mult": 1, "downtrend_buy_mult": 1, "downtrend_sell_mult": 1}
    OFF_VOLUME = {"enabled": False, "lookback": 24, "spike_threshold": 3.0}
    OFF_TP = {"enabled": False, "momentum_period": 10, "mild_momentum_pct": 3, "mild_skip_levels": 2, "strong_momentum_pct": 6, "strong_skip_levels": 3}

    combos = {
        "Grid only":              (OFF_VOL, OFF_TREND, OFF_VOLUME, OFF_TP),
        "Grid + VolAdapt":        (vol_cfg, OFF_TREND, OFF_VOLUME, OFF_TP),
        "Grid + Trend":           (OFF_VOL, trend_cfg, OFF_VOLUME, OFF_TP),
        "Grid + VolFilter":       (OFF_VOL, OFF_TREND, volume_cfg, OFF_TP),
        "Grid + DynTP":           (OFF_VOL, OFF_TREND, OFF_VOLUME, tp_cfg),
        "Grid + VolAdapt+Trend":  (vol_cfg, trend_cfg, OFF_VOLUME, OFF_TP),
        "Grid + VolAdapt+DynTP":  (vol_cfg, OFF_TREND, OFF_VOLUME, tp_cfg),
        "ALL LAYERS":             (vol_cfg, trend_cfg, volume_cfg, tp_cfg),
    }

    results = {}
    for name, (v, t, vf, tp) in combos.items():
        r = backtest_pair(df_1h, df_1d, symbol, grid_cfg, v, t, vf, tp)
        results[name] = r
    return results


if __name__ == "__main__":
    cfg = load_config()
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 90

    print(f"\n{'='*80}")
    print(f"  SMART BOT BACKTEST — {days} DAYS")
    print(f"{'='*80}\n")

    # Fetch all data
    pair_data = {}
    for pair_cfg in cfg["pairs"]:
        sym = pair_cfg["symbol"]
        pair_data[sym] = fetch_data(cfg["exchange"], sym, days)

    # ─────────────────────────────────
    #  Per-pair layer comparison
    # ─────────────────────────────────
    all_best = []

    for pair_cfg in cfg["pairs"]:
        sym = pair_cfg["symbol"]
        df_1h, df_1d = pair_data[sym]

        results = run_all_combos(
            df_1h, df_1d, sym, pair_cfg["grid"],
            cfg["volatility"], cfg["trend"], cfg["volume_filter"], cfg["dynamic_tp"]
        )

        print(f"\n  {sym}")
        print(f"  {'Strategy':<24} | {'Trades':>6} | {'Grid$':>7} | {'Value':>8} | {'P&L':>14} | {'GridUpd':>7} | {'VolPause':>8}")
        print(f"  {'-'*95}")

        best_name = ""
        best_pnl = -999999
        for name, r in results.items():
            marker = ""
            if r["pnl_pct"] > best_pnl:
                best_pnl = r["pnl_pct"]
                best_name = name
            print(
                f"  {name:<24} | {r['trades']:>6} | ${r['grid_profit']:>5.2f} | ${r['total_value']:>6.2f} | "
                f"${r['pnl']:>7.2f} ({r['pnl_pct']:>+6.1f}%) | {r['grid_updates']:>7} | {r['volume_pauses']:>8}"
            )

        print(f"  HODL: {results['Grid only']['hodl_return']:+.1f}%")
        print(f"  >>> BEST: {best_name} ({best_pnl:+.1f}%)")

        all_best.append(results[best_name])

    # ─────────────────────────────────
    #  Combined "ALL LAYERS" portfolio
    # ─────────────────────────────────
    all_layers = []
    for pair_cfg in cfg["pairs"]:
        sym = pair_cfg["symbol"]
        df_1h, df_1d = pair_data[sym]
        r = backtest_pair(
            df_1h, df_1d, sym, pair_cfg["grid"],
            cfg["volatility"], cfg["trend"], cfg["volume_filter"], cfg["dynamic_tp"]
        )
        all_layers.append(r)

    # Also get grid-only for comparison
    OFF_VOL = {"enabled": False, "atr_period": 14, "sensitivity": 50, "update_every_hours": 4}
    OFF_TREND = {"enabled": False, "uptrend_buy_mult": 1, "uptrend_sell_mult": 1, "downtrend_buy_mult": 1, "downtrend_sell_mult": 1}
    OFF_VOLUME = {"enabled": False, "lookback": 24, "spike_threshold": 3.0}
    OFF_TP = {"enabled": False, "momentum_period": 10, "mild_momentum_pct": 3, "mild_skip_levels": 2, "strong_momentum_pct": 6, "strong_skip_levels": 3}

    all_grid_only = []
    for pair_cfg in cfg["pairs"]:
        sym = pair_cfg["symbol"]
        df_1h, df_1d = pair_data[sym]
        r = backtest_pair(df_1h, df_1d, sym, pair_cfg["grid"], OFF_VOL, OFF_TREND, OFF_VOLUME, OFF_TP)
        all_grid_only.append(r)

    months = max(days / 30, 1)

    print(f"\n{'='*80}")
    print(f"  COMBINED PORTFOLIO — {days} DAYS")
    print(f"{'='*80}")

    for label, results_list in [("GRID ONLY", all_grid_only), ("ALL SMART LAYERS", all_layers)]:
        total_inv = sum(r["investment"] for r in results_list)
        total_val = sum(r["total_value"] for r in results_list)
        total_pnl = sum(r["pnl"] for r in results_list)
        total_pnl_pct = (total_pnl / total_inv) * 100
        total_trades = sum(r["trades"] for r in results_list)
        total_gp = sum(r["grid_profit"] for r in results_list)
        total_fees = sum(r["fees"] for r in results_list)

        print(f"\n  {label}")
        print(f"    Investment:    ${total_inv:.2f}")
        print(f"    Final value:   ${total_val:.2f}")
        print(f"    P&L:           ${total_pnl:.2f} ({total_pnl_pct:+.2f}%)")
        print(f"    Grid profit:   ${total_gp:.2f}")
        print(f"    Fees:          ${total_fees:.2f}")
        print(f"    Trades:        {total_trades}")
        if total_pnl > 0:
            monthly = total_pnl / months
            print(f"    Monthly:       ${monthly:.2f} ({(monthly/total_inv)*100:.2f}%)")
            print(f"    Yearly est:    ${monthly*12:.2f} ({(monthly*12/total_inv)*100:.1f}%)")

    # Per pair detail
    print(f"\n  Per-pair (ALL LAYERS):")
    for r in all_layers:
        print(
            f"    {r['symbol']:<12} ${r['investment']:>4.0f} → ${r['total_value']:>7.2f} | "
            f"{r['pnl_pct']:>+6.1f}% | {r['trades']} trades | "
            f"{r['grid_updates']} grid updates | {r['volume_pauses']} vol pauses"
        )

    print(f"\n  Per-pair (GRID ONLY):")
    for r in all_grid_only:
        print(
            f"    {r['symbol']:<12} ${r['investment']:>4.0f} → ${r['total_value']:>7.2f} | "
            f"{r['pnl_pct']:>+6.1f}% | {r['trades']} trades"
        )

    print(f"{'='*80}")

    # Save trades
    all_trades = []
    for r in all_layers:
        for t in r["all_trades"]:
            t["symbol"] = r["symbol"]
            all_trades.append(t)
    if all_trades:
        output = Path(__file__).parent / "smart_backtest_results.csv"
        pd.DataFrame(all_trades).to_csv(output, index=False)
        print(f"\n  Trade log saved to {output}")
