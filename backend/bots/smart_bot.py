"""
Smart Grid Trading Bot
-----------------------
Layer 1: Volatility-adaptive grid (auto-adjusts every N hours)
Layer 2: Multi-timeframe trend filter (daily trend sets buy/sell bias)
Layer 3: Volume spike filter (pause during abnormal volume)
Layer 4: Dynamic take-profit (ride strong moves, skip grid levels)
Layer 5: Multi-pair support

Default: PAPER TRADING (no real money).
"""

import json
import time
import logging
import sys
from datetime import datetime
from pathlib import Path
from collections import deque

import ccxt


def load_config(path="smart_config.json"):
    with open(Path(__file__).parent / path) as f:
        return json.load(f)


# ──────────────────────────────────────────────
#  Indicators
# ──────────────────────────────────────────────

def calc_atr(highs, lows, closes, period=14):
    """Average True Range — measures volatility."""
    if len(highs) < period + 1:
        return None
    trs = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    return sum(trs[-period:]) / period


def calc_ema(prices, period):
    """Exponential Moving Average."""
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return ema


def calc_sma(prices, period):
    """Simple Moving Average."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def detect_trend(closes_daily):
    """Detect trend from daily closes using EMA crossover.
    Returns: 'up', 'down', or 'neutral'
    """
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
    """Simple momentum — rate of change over N periods."""
    if len(closes) < period + 1:
        return 0
    return (closes[-1] - closes[-period - 1]) / closes[-period - 1] * 100


# ──────────────────────────────────────────────
#  Paper Exchange
# ──────────────────────────────────────────────

class PaperExchange:
    def __init__(self, balance_usdt, real_exchange):
        self.balance = {"USDT": balance_usdt}
        self.real_exchange = real_exchange
        self.open_orders = []
        self.order_id = 0

    def fetch_ticker(self, symbol):
        return self.real_exchange.fetch_ticker(symbol)

    def fetch_ohlcv(self, symbol, timeframe, limit=None, since=None):
        return self.real_exchange.fetch_ohlcv(symbol, timeframe, limit=limit, since=since)

    def _coin(self, symbol):
        return symbol.split("/")[0]

    def create_limit_buy_order(self, symbol, amount, price):
        self.order_id += 1
        order = {
            "id": str(self.order_id), "symbol": symbol, "side": "buy",
            "price": price, "amount": amount, "status": "open",
        }
        self.open_orders.append(order)
        return order

    def create_limit_sell_order(self, symbol, amount, price):
        self.order_id += 1
        order = {
            "id": str(self.order_id), "symbol": symbol, "side": "sell",
            "price": price, "amount": amount, "status": "open",
        }
        self.open_orders.append(order)
        return order

    def cancel_all_orders(self, symbol):
        self.open_orders = [o for o in self.open_orders if o["symbol"] != symbol]

    def check_and_fill(self, symbol, current_price):
        coin = self._coin(symbol)
        if coin not in self.balance:
            self.balance[coin] = 0.0

        still_open = []
        newly_filled = []
        for order in self.open_orders:
            if order["symbol"] != symbol:
                still_open.append(order)
                continue
            filled = False
            if order["side"] == "buy" and current_price <= order["price"]:
                cost = order["amount"] * order["price"]
                fee = cost * 0.001
                if self.balance["USDT"] >= cost + fee:
                    self.balance["USDT"] -= cost + fee
                    self.balance[coin] += order["amount"]
                    order["status"] = "closed"
                    order["fee"] = fee
                    newly_filled.append(order)
                    filled = True
            elif order["side"] == "sell" and current_price >= order["price"]:
                if self.balance.get(coin, 0) >= order["amount"]:
                    revenue = order["amount"] * order["price"]
                    fee = revenue * 0.001
                    self.balance["USDT"] += revenue - fee
                    self.balance[coin] -= order["amount"]
                    order["status"] = "closed"
                    order["fee"] = fee
                    newly_filled.append(order)
                    filled = True
            if not filled:
                still_open.append(order)
        self.open_orders = still_open
        return newly_filled


# ──────────────────────────────────────────────
#  Smart Pair Grid
# ──────────────────────────────────────────────

class SmartPairGrid:
    def __init__(self, symbol, pair_cfg, vol_cfg, trend_cfg, volume_cfg, tp_cfg, exchange, log):
        self.symbol = symbol
        self.coin = symbol.split("/")[0]
        self.exchange = exchange
        self.log = log

        # Base grid config
        self.base_lower = pair_cfg["grid"]["lower_price"]
        self.base_upper = pair_cfg["grid"]["upper_price"]
        self.num_grids = pair_cfg["grid"]["num_grids"]
        self.investment = pair_cfg["grid"]["investment_usdt"]

        # Current adaptive grid
        self.lower = self.base_lower
        self.upper = self.base_upper
        self.step = (self.upper - self.lower) / self.num_grids

        # Layer configs
        self.vol_cfg = vol_cfg
        self.trend_cfg = trend_cfg
        self.volume_cfg = volume_cfg
        self.tp_cfg = tp_cfg

        # Price history for indicators
        self.hourly_highs = deque(maxlen=100)
        self.hourly_lows = deque(maxlen=100)
        self.hourly_closes = deque(maxlen=100)
        self.hourly_volumes = deque(maxlen=100)
        self.daily_closes = deque(maxlen=30)

        # State
        self.active_orders = {}
        self.total_profit = 0.0
        self.total_fees = 0.0
        self.trades_count = 0
        self.buy_count = 0
        self.sell_count = 0
        self.volume_paused = False
        self.current_trend = "neutral"
        self.current_atr = None
        self.last_grid_update = 0
        self.initialized = False

    def _calc_order_amount(self):
        return round(self.investment / self.num_grids / ((self.lower + self.upper) / 2), 6)

    def update_volatility_grid(self):
        """Adapt grid spacing based on ATR (volatility)."""
        if not self.vol_cfg["enabled"]:
            return False

        atr = calc_atr(
            list(self.hourly_highs), list(self.hourly_lows),
            list(self.hourly_closes), self.vol_cfg["atr_period"]
        )
        if atr is None:
            return False

        self.current_atr = atr
        current_price = self.hourly_closes[-1]

        # ATR as % of price
        atr_pct = atr / current_price

        # Scale grid range based on volatility
        # Higher ATR → wider grid, lower ATR → tighter grid
        base_range = self.base_upper - self.base_lower
        mid = current_price

        # Multiplier: 0.5x to 2x based on ATR
        vol_multiplier = max(0.5, min(2.0, atr_pct * self.vol_cfg["sensitivity"]))
        half_range = (base_range * vol_multiplier) / 2

        new_lower = round(mid - half_range, 2)
        new_upper = round(mid + half_range, 2)

        # Only update if change is significant (>2%)
        if abs(new_lower - self.lower) / self.lower > 0.02:
            self.lower = new_lower
            self.upper = new_upper
            self.step = (self.upper - self.lower) / self.num_grids
            return True
        return False

    def check_volume_spike(self):
        """Detect abnormal volume and pause trading."""
        if not self.volume_cfg["enabled"]:
            return False

        if len(self.hourly_volumes) < self.volume_cfg["lookback"]:
            return False

        vols = list(self.hourly_volumes)
        avg_vol = sum(vols[:-1]) / len(vols[:-1])
        current_vol = vols[-1]

        if avg_vol == 0:
            return False

        spike_ratio = current_vol / avg_vol
        return spike_ratio > self.volume_cfg["spike_threshold"]

    def get_trend_bias(self):
        """Returns buy_multiplier, sell_multiplier based on daily trend."""
        if not self.trend_cfg["enabled"]:
            return 1.0, 1.0

        self.current_trend = detect_trend(list(self.daily_closes))

        if self.current_trend == "up":
            return self.trend_cfg["uptrend_buy_mult"], self.trend_cfg["uptrend_sell_mult"]
        elif self.current_trend == "down":
            return self.trend_cfg["downtrend_buy_mult"], self.trend_cfg["downtrend_sell_mult"]
        return 1.0, 1.0

    def get_take_profit_levels(self):
        """Dynamic take profit — skip levels when momentum is strong."""
        if not self.tp_cfg["enabled"]:
            return 1  # normal: sell 1 step above buy

        momentum = calc_momentum(list(self.hourly_closes), self.tp_cfg["momentum_period"])

        if abs(momentum) > self.tp_cfg["strong_momentum_pct"]:
            return self.tp_cfg["strong_skip_levels"]  # skip levels on strong moves
        elif abs(momentum) > self.tp_cfg["mild_momentum_pct"]:
            return self.tp_cfg["mild_skip_levels"]
        return 1

    def rebuild_grid(self, current_price):
        """Cancel all orders and rebuild grid at new levels."""
        self.exchange.cancel_all_orders(self.symbol)
        self.active_orders.clear()

        grid_levels = [round(self.lower + i * self.step, 2) for i in range(self.num_grids + 1)]
        order_amount = self._calc_order_amount()
        buy_mult, sell_mult = self.get_trend_bias()

        for level in grid_levels:
            if level < current_price:
                amt = round(order_amount * buy_mult, 6)
                if amt > 0:
                    order = self.exchange.create_limit_buy_order(self.symbol, amt, level)
                    self.active_orders[level] = {"order": order, "side": "buy", "amount": amt}
            elif level > current_price:
                amt = round(order_amount * sell_mult, 6)
                if amt > 0:
                    order = self.exchange.create_limit_sell_order(self.symbol, amt, level)
                    self.active_orders[level] = {"order": order, "side": "sell", "amount": amt}

    def place_initial_orders(self, current_price):
        self.rebuild_grid(current_price)
        self.initialized = True
        self.log.info(
            f"  [{self.symbol}] Grid: ${self.lower:.0f}-${self.upper:.0f} | "
            f"Step: ${self.step:.2f} | Orders: {len(self.active_orders)}"
        )

    def update(self, current_price, hourly_candle=None, daily_close=None):
        """Main update cycle."""
        # Update price history
        if hourly_candle:
            self.hourly_highs.append(hourly_candle["high"])
            self.hourly_lows.append(hourly_candle["low"])
            self.hourly_closes.append(hourly_candle["close"])
            self.hourly_volumes.append(hourly_candle["volume"])

        if daily_close is not None:
            self.daily_closes.append(daily_close)

        # Layer 3: Volume spike check
        self.volume_paused = self.check_volume_spike()
        if self.volume_paused:
            return  # skip this cycle

        # Layer 1: Volatility-adaptive grid (rebuild if changed)
        if self.update_volatility_grid():
            self.log.info(
                f"  [{self.symbol}] Grid adapted: ${self.lower:.0f}-${self.upper:.0f} "
                f"(ATR=${self.current_atr:.2f})"
            )
            self.rebuild_grid(current_price)

        # Check fills
        if hasattr(self.exchange, 'check_and_fill'):
            self.exchange.check_and_fill(self.symbol, current_price)

        buy_mult, sell_mult = self.get_trend_bias()
        tp_levels = self.get_take_profit_levels()
        order_amount = self._calc_order_amount()

        filled_levels = []
        for level, info in list(self.active_orders.items()):
            order = info["order"]
            if order["status"] != "closed":
                continue

            filled_levels.append(level)
            side = info["side"]
            amt = info["amount"]
            self.trades_count += 1

            if side == "buy":
                self.buy_count += 1
                # Layer 4: Dynamic take-profit
                sell_price = round(level + self.step * tp_levels, 2)
                sell_amt = round(amt * sell_mult, 6)
                if sell_amt > 0:
                    new_order = self.exchange.create_limit_sell_order(
                        self.symbol, sell_amt, sell_price
                    )
                    self.active_orders[sell_price] = {
                        "order": new_order, "side": "sell", "amount": sell_amt
                    }
            else:
                self.sell_count += 1
                profit = amt * self.step * tp_levels * 0.998
                self.total_profit += profit
                buy_price = round(level - self.step, 2)
                buy_amt = round(order_amount * buy_mult, 6)
                if buy_amt > 0:
                    new_order = self.exchange.create_limit_buy_order(
                        self.symbol, buy_amt, buy_price
                    )
                    self.active_orders[buy_price] = {
                        "order": new_order, "side": "buy", "amount": buy_amt
                    }

        for level in filled_levels:
            if level in self.active_orders:
                del self.active_orders[level]


# ──────────────────────────────────────────────
#  Smart Bot
# ──────────────────────────────────────────────

class SmartBot:
    def __init__(self, config_path="smart_config.json", on_trade=None):
        self.cfg = load_config(config_path)
        self.paper = self.cfg["paper_trading"]
        self.on_trade = on_trade
        self._running = False

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(Path(__file__).parent / self.cfg["log_file"]),
                logging.StreamHandler(sys.stdout),
            ],
        )
        self.log = logging.getLogger("SmartBot")

        exchange_class = getattr(ccxt, self.cfg["exchange"])
        self.real_exchange = exchange_class({
            "apiKey": self.cfg.get("api_key", ""),
            "secret": self.cfg.get("api_secret", ""),
            "enableRateLimit": True,
        })

        total_investment = sum(p["grid"]["investment_usdt"] for p in self.cfg["pairs"])
        if self.paper:
            self.log.info("=== PAPER TRADING MODE ===")
            self.exchange = PaperExchange(total_investment, self.real_exchange)
        else:
            self.exchange = self.real_exchange

        self.pairs = []
        for pair_cfg in self.cfg["pairs"]:
            pg = SmartPairGrid(
                symbol=pair_cfg["symbol"],
                pair_cfg=pair_cfg,
                vol_cfg=self.cfg["volatility"],
                trend_cfg=self.cfg["trend"],
                volume_cfg=self.cfg["volume_filter"],
                tp_cfg=self.cfg["dynamic_tp"],
                exchange=self.exchange,
                log=self.log,
            )
            self.pairs.append(pg)

        self.start_balance = total_investment

    def load_history(self):
        """Load candle history for all indicators."""
        for pg in self.pairs:
            try:
                candles_1h = self.exchange.fetch_ohlcv(pg.symbol, "1h", limit=100)
                for c in candles_1h:
                    pg.hourly_highs.append(c[2])
                    pg.hourly_lows.append(c[3])
                    pg.hourly_closes.append(c[4])
                    pg.hourly_volumes.append(c[5])

                candles_1d = self.exchange.fetch_ohlcv(pg.symbol, "1d", limit=30)
                for c in candles_1d:
                    pg.daily_closes.append(c[4])

                self.log.info(f"  [{pg.symbol}] Loaded {len(candles_1h)} 1h + {len(candles_1d)} 1d candles")
            except Exception as e:
                self.log.warning(f"  [{pg.symbol}] History load failed: {e}")

    def print_status(self):
        self.log.info("─" * 70)
        for pg in self.pairs:
            trend = pg.current_trend
            atr = f"${pg.current_atr:.1f}" if pg.current_atr else "N/A"
            vol_status = "PAUSED" if pg.volume_paused else "OK"
            self.log.info(
                f"  {pg.symbol:>10} | Trend={trend:>7} | ATR={atr:>7} | "
                f"Vol={vol_status:>6} | Grid=${pg.lower:.0f}-${pg.upper:.0f} | "
                f"Trades={pg.trades_count} ({pg.buy_count}B/{pg.sell_count}S) | "
                f"Profit=${pg.total_profit:.2f}"
            )

        if self.paper:
            bal = self.exchange.balance
            usdt = bal["USDT"]
            coin_value = 0
            for pg in self.pairs:
                amt = bal.get(pg.coin, 0)
                if amt > 0:
                    try:
                        t = self.exchange.fetch_ticker(pg.symbol)
                        coin_value += amt * t["last"]
                    except Exception:
                        pass
            total = usdt + coin_value
            pnl = total - self.start_balance
            pnl_pct = (pnl / self.start_balance) * 100
            self.log.info(
                f"  {'TOTAL':>10} | USDT=${usdt:.2f} | Coins=${coin_value:.2f} | "
                f"Value=${total:.2f} | P&L=${pnl:.2f} ({pnl_pct:+.2f}%)"
            )
        self.log.info("─" * 70)

    def get_status(self):
        """Return current bot status as a dict."""
        total_profit = 0.0
        total_fees = 0.0
        num_trades = 0
        total_active_orders = 0

        for pg in self.pairs:
            total_profit += pg.total_profit
            total_fees += pg.total_fees
            num_trades += pg.trades_count
            total_active_orders += len(pg.active_orders)

        try:
            current_price = self.exchange.fetch_ticker(self.pairs[0].symbol)["last"] if self.pairs else 0.0
        except Exception:
            current_price = 0.0

        if self.paper:
            bal = self.exchange.balance
            balance_usdt = bal.get("USDT", 0.0)
            balance_coin = sum(bal.get(pg.coin, 0.0) for pg in self.pairs)
            coin_value = 0
            for pg in self.pairs:
                amt = bal.get(pg.coin, 0)
                if amt > 0:
                    try:
                        t = self.exchange.fetch_ticker(pg.symbol)
                        coin_value += amt * t["last"]
                    except Exception:
                        pass
            portfolio_value = balance_usdt + coin_value
        else:
            balance_usdt = 0.0
            balance_coin = 0.0
            portfolio_value = self.start_balance + total_profit

        return {
            "status": "running" if self._running else "stopped",
            "total_profit": total_profit,
            "total_fees": total_fees,
            "num_trades": num_trades,
            "balance_usdt": balance_usdt,
            "balance_coin": balance_coin,
            "active_orders": total_active_orders,
            "current_price": current_price,
            "portfolio_value": portfolio_value,
        }

    def stop(self):
        """Stop the bot gracefully."""
        self._running = False

    def run(self):
        self._running = True
        self.log.info("=" * 70)
        self.log.info("  SMART GRID BOT")
        self.log.info(f"  Pairs: {[p.symbol for p in self.pairs]}")
        self.log.info(f"  Volatility adaptive: {'ON' if self.cfg['volatility']['enabled'] else 'OFF'}")
        self.log.info(f"  Trend filter: {'ON' if self.cfg['trend']['enabled'] else 'OFF'}")
        self.log.info(f"  Volume filter: {'ON' if self.cfg['volume_filter']['enabled'] else 'OFF'}")
        self.log.info(f"  Dynamic TP: {'ON' if self.cfg['dynamic_tp']['enabled'] else 'OFF'}")
        self.log.info("=" * 70)

        self.load_history()

        for pg in self.pairs:
            t = self.exchange.fetch_ticker(pg.symbol)
            pg.update_volatility_grid()
            pg.place_initial_orders(t["last"])

        self.log.info("\nAll pairs initialized. Running...\n")

        cycle = 0
        interval = self.cfg["check_interval_seconds"]

        while self._running:
            try:
                cycle += 1
                for pg in self.pairs:
                    t = self.exchange.fetch_ticker(pg.symbol)
                    old_trades = pg.trades_count
                    pg.update(t["last"])

                    # Fire on_trade callback for new fills
                    if self.on_trade and pg.trades_count > old_trades:
                        self.on_trade({
                            "symbol": pg.symbol,
                            "trades_count": pg.trades_count,
                            "total_profit": pg.total_profit,
                            "price": t["last"],
                            "timestamp": datetime.utcnow().isoformat(),
                        })

                if cycle % 20 == 0:
                    self.log.info(f"\n--- Cycle {cycle} ---")
                    self.print_status()

                time.sleep(interval)

            except ccxt.NetworkError as e:
                self.log.warning(f"Network error: {e}. Retrying in 60s...")
                time.sleep(60)
            except ccxt.ExchangeError as e:
                self.log.error(f"Exchange error: {e}")
                time.sleep(60)
            except KeyboardInterrupt:
                self.log.info("\nStopping bot...")
                self.print_status()
                break


if __name__ == "__main__":
    bot = SmartBot()
    bot.run()
