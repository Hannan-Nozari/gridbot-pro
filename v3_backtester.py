"""
V3 Bot Backtester
-----------------
Tests all 10 layers individually and combined.

Usage:
  python v3_backtester.py          # 90 days
  python v3_backtester.py 30       # 30 days
"""

import json
import sys
import copy
from pathlib import Path
from collections import deque

import ccxt
import pandas as pd


def load_config(path="v3_config.json"):
    with open(Path(__file__).parent / path) as f:
        return json.load(f)


# ──────────────────────────────────────────────
#  Indicators (same as v3_bot.py)
# ──────���───────────────────────────────────────

def calc_ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return ema

def calc_sma(prices, period):
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period

def calc_std(prices, period):
    if len(prices) < period:
        return None
    mean = sum(prices[-period:]) / period
    variance = sum((p - mean) ** 2 for p in prices[-period:]) / period
    return variance ** 0.5

def calc_bollinger(prices, period=20, num_std=2.0):
    sma = calc_sma(prices, period)
    std = calc_std(prices, period)
    if sma is None or std is None:
        return None
    return (sma - num_std * std, sma, sma + num_std * std)

def calc_vwap(highs, lows, closes, volumes, period=20):
    if len(closes) < period:
        return None
    total_vp = 0
    total_vol = 0
    for i in range(-period, 0):
        typical = (highs[i] + lows[i] + closes[i]) / 3
        total_vp += typical * volumes[i]
        total_vol += volumes[i]
    if total_vol == 0:
        return None
    return total_vp / total_vol

def calc_momentum(closes, period=10):
    if len(closes) < period + 1:
        return 0
    return (closes[-1] - closes[-period - 1]) / closes[-period - 1] * 100

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

def calc_fear_greed(closes, volumes, period=14):
    if len(closes) < period + 1:
        return 50
    price_change = (closes[-1] - closes[-period - 1]) / closes[-period - 1]
    price_score = max(0, min(50, 25 + price_change * 500))
    recent_vol = [abs(closes[i] - closes[i-1]) / closes[i-1] for i in range(-period, 0)]
    avg_vol = sum(recent_vol) / len(recent_vol)
    vol_score = max(0, min(25, 25 - avg_vol * 1000))
    if len(volumes) >= period:
        vf = sum(list(volumes)[-period:-period//2]) / max(period//2, 1)
        vs = sum(list(volumes)[-period//2:]) / max(period//2, 1)
        vol_trend = max(0, min(25, 12.5 + (vs/max(vf,1) - 1) * 50))
    else:
        vol_trend = 12.5
    return price_score + vol_score + vol_trend


# ──────���───────────────────────────────────────
#  Data fetching
# ──────────────────────────────────────────────

def fetch_data(exchange_id, symbol, days):
    print(f"  {symbol}...", end=" ", flush=True)
    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})

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

    since_d = exchange.milliseconds() - (days + 30) * 24 * 60 * 60 * 1000
    candles_1d = exchange.fetch_ohlcv(symbol, "1d", since=since_d, limit=1000)
    df_1d = pd.DataFrame(candles_1d, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df_1d["timestamp"] = pd.to_datetime(df_1d["timestamp"], unit="ms")

    print(f"{len(candles_1h)} 1h + {len(candles_1d)} 1d")
    return df_1h, df_1d


# ──────────────────────────────────────────────
#  Backtest engine
# ─────���────────────────────────────────────────

def backtest_pair(df_1h, df_1d, btc_1h, symbol, grid_cfg, layers):
    """Full backtest for one pair with all layers."""

    base_lower = grid_cfg["lower_price"]
    base_upper = grid_cfg["upper_price"]
    num_grids = grid_cfg["num_grids"]
    investment = grid_cfg["investment_usdt"]
    fee_rate = 0.001
    fee_discount = layers["fee_optimization"]["size_boost"] if layers["fee_optimization"]["enabled"] else 1.0
    if layers["fee_optimization"]["enabled"]:
        fee_rate = 0.00075  # BNB discount

    # Grid state
    lower = base_lower
    upper = base_upper
    step = (upper - lower) / num_grids

    def grid_levels():
        return [round(lower + i * step, 2) for i in range(num_grids + 1)]

    def order_size():
        return investment / num_grids / ((lower + upper) / 2)

    # Balances
    balance_usdt = investment
    balance_coin = 0.0
    buy_orders = {}
    sell_orders = {}

    # Stats
    total_profit = 0.0
    total_fees = 0.0
    num_buys = 0
    num_sells = 0
    trades = []

    # Layer stats
    bb_updates = 0
    vwap_adj = 0
    fg_adj = 0
    btc_pauses = 0
    dd_pauses = 0
    profit_locks = 0
    sizing_adj = 0

    # History
    h_highs = deque(maxlen=200)
    h_lows = deque(maxlen=200)
    h_closes = deque(maxlen=200)
    h_volumes = deque(maxlen=200)

    # Profit lock state
    peak_value = investment
    profit_floor = 0

    # Dynamic sizing
    consec_wins = 0
    consec_losses = 0

    # BTC history for correlation
    btc_closes = deque(maxlen=50)

    # Daily close lookup
    daily_dates = list(df_1d["timestamp"].dt.date)
    daily_closes_list = list(df_1d["close"])

    # BTC lookup
    btc_timestamps = set()
    btc_map = {}
    if btc_1h is not None:
        for _, br in btc_1h.iterrows():
            btc_map[br["timestamp"]] = br["close"]

    # Place initial orders
    first_price = df_1h["close"].iloc[0]
    amt = order_size() * fee_discount
    for lvl in grid_levels():
        if lvl < first_price:
            buy_orders[lvl] = amt
        elif lvl > first_price:
            sell_orders[lvl] = amt

    last_bb_idx = 0

    for idx, row in df_1h.iterrows():
        price_close = row["close"]
        price_low = row["low"]
        price_high = row["high"]

        h_highs.append(row["high"])
        h_lows.append(row["low"])
        h_closes.append(row["close"])
        h_volumes.append(row["volume"])

        # BTC price
        if row["timestamp"] in btc_map:
            btc_closes.append(btc_map[row["timestamp"]])

        # ── Layer 6: BTC correlation filter ──
        btc_cfg = layers["btc_correlation"]
        btc_paused = False
        if btc_cfg["enabled"] and len(btc_closes) >= btc_cfg["lookback"]:
            btc_list = list(btc_closes)
            btc_change = (btc_list[-1] - btc_list[-btc_cfg["lookback"]]) / btc_list[-btc_cfg["lookback"]] * 100
            if btc_change < -btc_cfg["crash_threshold_pct"]:
                btc_paused = True
                btc_pauses += 1

        # ── Layer 7: Drawdown circuit breaker ──
        dd_cfg = layers["drawdown_breaker"]
        dd_paused = False
        if dd_cfg["enabled"]:
            current_value = balance_usdt + balance_coin * price_close
            if current_value > peak_value:
                peak_value = current_value
            dd = (peak_value - current_value) / peak_value * 100
            if dd >= dd_cfg["max_drawdown_pct"]:
                dd_paused = True
                dd_pauses += 1

        # ── Layer 8: Profit lock ──
        pl_cfg = layers["profit_lock"]
        locked = False
        if pl_cfg["enabled"]:
            current_value = balance_usdt + balance_coin * price_close
            profit_pct = (current_value - investment) / investment * 100
            if current_value > peak_value:
                peak_value = current_value
            if profit_pct >= pl_cfg["lock_after_pct"]:
                floor_pct = profit_pct * pl_cfg["lock_ratio"]
                new_floor = investment * (1 + floor_pct / 100)
                if new_floor > profit_floor:
                    profit_floor = new_floor
            if profit_floor > 0 and current_value <= profit_floor:
                locked = True
                profit_locks += 1

        # Skip if any safety triggered
        if btc_paused or dd_paused or locked:
            continue

        # ── Layer 2: Bollinger Band grid ──
        bb_cfg = layers["bollinger"]
        if bb_cfg["enabled"] and len(h_closes) >= bb_cfg["period"]:
            update_interval = bb_cfg["update_every_hours"]
            if idx - last_bb_idx >= update_interval:
                bb = calc_bollinger(list(h_closes), bb_cfg["period"], bb_cfg["num_std"])
                if bb:
                    bb_l, bb_m, bb_u = bb
                    padding = (bb_u - bb_l) * bb_cfg["padding_pct"]
                    new_lower = round(bb_l - padding, 2)
                    new_upper = round(bb_u + padding, 2)
                    min_range = price_close * 0.02
                    if new_upper - new_lower < min_range:
                        new_lower = round(price_close - min_range, 2)
                        new_upper = round(price_close + min_range, 2)
                    if abs(new_lower - lower) / max(lower, 1) > 0.02:
                        lower = new_lower
                        upper = new_upper
                        step = (upper - lower) / num_grids
                        bb_updates += 1
                        buy_orders.clear()
                        sell_orders.clear()
                        amt = order_size() * fee_discount
                        for lvl in grid_levels():
                            if lvl < price_close:
                                buy_orders[lvl] = amt
                            elif lvl > price_close:
                                sell_orders[lvl] = amt
                        last_bb_idx = idx

        # ── Layer 4: VWAP bias ──
        buy_mult = 1.0
        sell_mult = 1.0
        vwap_cfg = layers["vwap"]
        if vwap_cfg["enabled"] and len(h_closes) >= vwap_cfg["period"]:
            vwap = calc_vwap(list(h_highs), list(h_lows), list(h_closes), list(h_volumes), vwap_cfg["period"])
            if vwap:
                diff = (price_close - vwap) / vwap * 100
                if diff > vwap_cfg["threshold_pct"]:
                    sell_mult *= vwap_cfg["above_vwap_sell_mult"]
                    vwap_adj += 1
                elif diff < -vwap_cfg["threshold_pct"]:
                    buy_mult *= vwap_cfg["below_vwap_buy_mult"]
                    vwap_adj += 1

        # ── Layer 9: Fear & Greed ──
        fg_cfg = layers["fear_greed"]
        if fg_cfg["enabled"] and len(h_closes) > fg_cfg["period"]:
            fg = calc_fear_greed(list(h_closes), list(h_volumes), fg_cfg["period"])
            if fg <= fg_cfg["extreme_fear"]:
                buy_mult *= fg_cfg["fear_buy_mult"]
                sell_mult *= fg_cfg["fear_sell_mult"]
                fg_adj += 1
            elif fg >= fg_cfg["extreme_greed"]:
                buy_mult *= fg_cfg["greed_buy_mult"]
                sell_mult *= fg_cfg["greed_sell_mult"]
                fg_adj += 1

        # ── Layer 5: Dynamic sizing ──
        ds_cfg = layers["dynamic_sizing"]
        if ds_cfg["enabled"]:
            if consec_wins >= ds_cfg["win_streak_threshold"]:
                buy_mult *= ds_cfg["win_streak_mult"]
                sell_mult *= ds_cfg["win_streak_mult"]
                sizing_adj += 1
            elif consec_losses >= ds_cfg["loss_streak_threshold"]:
                buy_mult *= ds_cfg["loss_streak_mult"]
                sell_mult *= ds_cfg["loss_streak_mult"]
                sizing_adj += 1

        # ── Layer 3: Dynamic TP ──
        tp_levels = 1
        tp_cfg = layers["dynamic_tp"]
        if tp_cfg["enabled"] and len(h_closes) > tp_cfg["momentum_period"]:
            mom = calc_momentum(list(h_closes), tp_cfg["momentum_period"])
            if abs(mom) > tp_cfg["strong_momentum_pct"]:
                tp_levels = tp_cfg["strong_skip_levels"]
            elif abs(mom) > tp_cfg["mild_momentum_pct"]:
                tp_levels = tp_cfg["mild_skip_levels"]

        # ── Check buy fills ──
        filled_buys = []
        for level, base_amt in list(buy_orders.items()):
            if price_low <= level:
                amt = round(base_amt * buy_mult, 6)
                cost = amt * level
                fee = cost * fee_rate
                if balance_usdt >= cost + fee:
                    balance_usdt -= cost + fee
                    balance_coin += amt
                    total_fees += fee
                    num_buys += 1
                    filled_buys.append(level)
                    trades.append({"time": row["timestamp"], "side": "buy", "price": level, "amount": amt, "fee": fee})
                    sell_price = round(level + step * tp_levels, 2)
                    sell_orders[sell_price] = round(amt * sell_mult, 6)
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
                    profit = amt * step * tp_levels * (1 - fee_rate * 2)
                    total_profit += profit
                    num_sells += 1
                    filled_sells.append(level)
                    trades.append({"time": row["timestamp"], "side": "sell", "price": level, "amount": amt, "fee": fee, "profit": profit})
                    if profit > 0:
                        consec_wins += 1
                        consec_losses = 0
                    else:
                        consec_losses += 1
                        consec_wins = 0
                    buy_price = round(level - step, 2)
                    buy_orders[buy_price] = round(order_size() * buy_mult * fee_discount, 6)
        for level in filled_sells:
            del sell_orders[level]

    final_price = df_1h["close"].iloc[-1]
    coin_value = balance_coin * final_price
    total_value = balance_usdt + coin_value
    pnl = total_value - investment
    pnl_pct = (pnl / investment) * 100
    hodl_ret = ((final_price - df_1h["close"].iloc[0]) / df_1h["close"].iloc[0]) * 100

    return {
        "symbol": symbol, "investment": investment,
        "trades": num_buys + num_sells, "buys": num_buys, "sells": num_sells,
        "grid_profit": total_profit, "fees": total_fees,
        "total_value": total_value, "pnl": pnl, "pnl_pct": pnl_pct,
        "hodl_return": hodl_ret,
        "bb_updates": bb_updates, "vwap_adj": vwap_adj, "fg_adj": fg_adj,
        "btc_pauses": btc_pauses, "dd_pauses": dd_pauses,
        "profit_locks": profit_locks, "sizing_adj": sizing_adj,
        "all_trades": trades,
    }


# ──────────────────────────────────────────────
#  Layer toggle helper
# ───��──────────────────────────────────────────

def all_off(layers):
    """Return layers config with everything disabled."""
    off = copy.deepcopy(layers)
    for key in off:
        if isinstance(off[key], dict) and "enabled" in off[key]:
            off[key]["enabled"] = False
    return off


def with_layers(base_off, layers_full, *layer_names):
    """Enable specific layers on top of all-off base."""
    cfg = copy.deepcopy(base_off)
    for name in layer_names:
        if name in cfg and name in layers_full:
            cfg[name] = copy.deepcopy(layers_full[name])
    return cfg


# ───────────────────────────��──────────────────
#  Main
# ─────────────────────────────���────────────────

if __name__ == "__main__":
    cfg = load_config()
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 90

    print(f"\n{'='*90}")
    print(f"  V3 FULL STACK BACKTEST — {days} DAYS")
    print(f"{'='*90}")
    print(f"  Fetching data...")

    # Fetch all data including BTC
    pair_data = {}
    for pc in cfg["pairs"]:
        pair_data[pc["symbol"]] = fetch_data(cfg["exchange"], pc["symbol"], days)

    btc_1h, btc_1d = fetch_data(cfg["exchange"], "BTC/USDT", days)

    layers_full = cfg["layers"]
    off = all_off(layers_full)

    # Define test combos
    combos = [
        ("Grid only",           all_off(layers_full)),
        ("+ Bollinger",         with_layers(off, layers_full, "bollinger")),
        ("+ DynTP",             with_layers(off, layers_full, "dynamic_tp")),
        ("+ VWAP",              with_layers(off, layers_full, "vwap")),
        ("+ DynSize",           with_layers(off, layers_full, "dynamic_sizing")),
        ("+ BTC Filter",        with_layers(off, layers_full, "btc_correlation")),
        ("+ Drawdown",          with_layers(off, layers_full, "drawdown_breaker")),
        ("+ ProfitLock",        with_layers(off, layers_full, "profit_lock")),
        ("+ Fear&Greed",        with_layers(off, layers_full, "fear_greed")),
        ("+ FeeOpt",            with_layers(off, layers_full, "fee_optimization")),
        ("BB+DynTP+VWAP",       with_layers(off, layers_full, "bollinger", "dynamic_tp", "vwap")),
        ("BB+BTC+DD+PL",        with_layers(off, layers_full, "bollinger", "btc_correlation", "drawdown_breaker", "profit_lock")),
        ("Adapt(BB+TP+VWAP+FG)", with_layers(off, layers_full, "bollinger", "dynamic_tp", "vwap", "fear_greed", "fee_optimization")),
        ("Safety(BTC+DD+PL)",   with_layers(off, layers_full, "btc_correlation", "drawdown_breaker", "profit_lock")),
        ("ALL LAYERS",          copy.deepcopy(layers_full)),
    ]

    # ─────────────────────────────────
    #  Per pair
    # ───────────��─────────────────────
    pair_best = {}

    for pc in cfg["pairs"]:
        sym = pc["symbol"]
        df_1h, df_1d = pair_data[sym]

        print(f"\n  {sym}")
        print(f"  {'Strategy':<25} | {'Trd':>4} | {'Grid$':>7} | {'Value':>8} | {'P&L':>14} | {'BB':>3} {'VW':>3} {'FG':>3} {'BTC':>4} {'DD':>3} {'PL':>3}")
        print(f"  {'-'*100}")

        best_name = ""
        best_pnl = -999999
        pair_results = {}

        for name, layer_cfg in combos:
            r = backtest_pair(df_1h, df_1d, btc_1h, sym, pc["grid"], layer_cfg)
            pair_results[name] = r
            if r["pnl_pct"] > best_pnl:
                best_pnl = r["pnl_pct"]
                best_name = name
            print(
                f"  {name:<25} | {r['trades']:>4} | ${r['grid_profit']:>5.2f} | ${r['total_value']:>6.2f} | "
                f"${r['pnl']:>7.2f} ({r['pnl_pct']:>+6.1f}%) | "
                f"{r['bb_updates']:>3} {r['vwap_adj']:>3} {r['fg_adj']:>3} {r['btc_pauses']:>4} {r['dd_pauses']:>3} {r['profit_locks']:>3}"
            )

        print(f"  HODL: {pair_results['Grid only']['hodl_return']:+.1f}%")
        print(f"  >>> BEST: {best_name} ({best_pnl:+.1f}%)")
        pair_best[sym] = (best_name, pair_results[best_name])

    # ─────────────────────────────────
    #  Portfolio summaries
    # ─────────────────────────────────
    months = max(days / 30, 1)

    summary_combos = [
        ("Grid only", all_off(layers_full)),
        ("Adaptive only", with_layers(off, layers_full, "bollinger", "dynamic_tp", "vwap", "fear_greed", "fee_optimization")),
        ("Safety only", with_layers(off, layers_full, "btc_correlation", "drawdown_breaker", "profit_lock")),
        ("ALL LAYERS", copy.deepcopy(layers_full)),
    ]

    print(f"\n{'='*90}")
    print(f"  COMBINED PORTFOLIO — {days} DAYS")
    print(f"{'='*90}")

    for label, layer_cfg in summary_combos:
        results = []
        for pc in cfg["pairs"]:
            sym = pc["symbol"]
            df_1h, df_1d = pair_data[sym]
            r = backtest_pair(df_1h, df_1d, btc_1h, sym, pc["grid"], layer_cfg)
            results.append(r)

        total_inv = sum(r["investment"] for r in results)
        total_val = sum(r["total_value"] for r in results)
        total_pnl = sum(r["pnl"] for r in results)
        total_pnl_pct = (total_pnl / total_inv) * 100
        total_trades = sum(r["trades"] for r in results)
        total_gp = sum(r["grid_profit"] for r in results)
        total_fees = sum(r["fees"] for r in results)

        print(f"\n  {label}")
        print(f"    Invested: ${total_inv:.0f} → ${total_val:.2f} | P&L: ${total_pnl:.2f} ({total_pnl_pct:+.2f}%) | Trades: {total_trades} | Fees: ${total_fees:.2f}")
        if total_pnl > 0:
            monthly = total_pnl / months
            print(f"    Monthly: ${monthly:.2f} ({(monthly/total_inv)*100:.2f}%) | Yearly est: ${monthly*12:.2f} ({(monthly*12/total_inv)*100:.1f}%)")
        for r in results:
            print(f"      {r['symbol']:<10} ${r['total_value']:>7.2f} ({r['pnl_pct']:>+6.1f}%) | {r['trades']} trades")

    # Best per pair
    print(f"\n  BEST PER PAIR:")
    total_best_val = 0
    total_best_inv = 0
    for sym, (name, r) in pair_best.items():
        print(f"    {sym:<10} {name:<25} | ${r['total_value']:>7.2f} ({r['pnl_pct']:>+6.1f}%)")
        total_best_val += r["total_value"]
        total_best_inv += r["investment"]
    best_pnl = total_best_val - total_best_inv
    print(f"    {'TOTAL':<10} {'(cherry-picked best)':<25} | ${total_best_val:>7.2f} ({(best_pnl/total_best_inv)*100:+.1f}%)")
    if best_pnl > 0:
        monthly = best_pnl / months
        print(f"    Monthly: ${monthly:.2f} ({(monthly/total_best_inv)*100:.2f}%) | Yearly: ${monthly*12:.2f}")

    print(f"\n{'='*90}")

    # Save
    all_trades = []
    for pc in cfg["pairs"]:
        sym = pc["symbol"]
        df_1h, df_1d = pair_data[sym]
        r = backtest_pair(df_1h, df_1d, btc_1h, sym, pc["grid"], layers_full)
        for t in r["all_trades"]:
            t["symbol"] = sym
            all_trades.append(t)
    if all_trades:
        output = Path(__file__).parent / "v3_backtest_results.csv"
        pd.DataFrame(all_trades).to_csv(output, index=False)
        print(f"  Trade log saved to {output}")
