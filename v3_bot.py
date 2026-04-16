"""
Grid Bot V3 — Full Stack
--------------------------
All layers:

CORE:
  1. Grid trading (multi-pair)

ADAPTIVE:
  2. Bollinger Band grid (auto-adjusts range)
  3. Dynamic take-profit (momentum-based)
  4. VWAP bias (trade with institutional flow)
  5. Dynamic position sizing (risk more when winning)

SAFETY:
  6. BTC correlation filter (pause alts when BTC dumps)
  7. Drawdown circuit breaker (hard stop on big losses)
  8. Profit lock / ratchet (never give back all gains)

EDGE:
  9. Fear & Greed Index (contrarian sentiment)
  10. Fee optimization (simulate BNB discount)

Default: PAPER TRADING
"""

import json
import time
import logging
import sys
from datetime import datetime
from pathlib import Path
from collections import deque

import ccxt


def load_config(path="v3_config.json"):
    with open(Path(__file__).parent / path) as f:
        return json.load(f)


# ──────────────────────────────────────────────
#  Indicators
# ──────────────────────────────────────────────

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
    """Returns (lower_band, middle, upper_band) or None."""
    sma = calc_sma(prices, period)
    std = calc_std(prices, period)
    if sma is None or std is None:
        return None
    return (sma - num_std * std, sma, sma + num_std * std)


def calc_vwap(highs, lows, closes, volumes, period=20):
    """Volume-Weighted Average Price."""
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


# ──────────────────────────────────────────────
#  Fear & Greed (simplified from price action)
# ──────────────────────────────────────────────

def calc_fear_greed(closes, volumes, period=14):
    """
    Approximate Fear & Greed from price action + volume.
    Returns 0-100 (0 = extreme fear, 100 = extreme greed).
    In live mode you'd use alternative.me API instead.
    """
    if len(closes) < period + 1:
        return 50

    # Price momentum component (0-50)
    price_change = (closes[-1] - closes[-period - 1]) / closes[-period - 1]
    price_score = max(0, min(50, 25 + price_change * 500))

    # Volatility component (high vol = fear) (0-25)
    recent_vol = [abs(closes[i] - closes[i - 1]) / closes[i - 1]
                  for i in range(-period, 0)]
    avg_vol = sum(recent_vol) / len(recent_vol)
    vol_score = max(0, min(25, 25 - avg_vol * 1000))

    # Volume trend (rising volume = greed) (0-25)
    if len(volumes) >= period:
        vol_first = sum(list(volumes)[-period:-period // 2]) / max(period // 2, 1)
        vol_second = sum(list(volumes)[-period // 2:]) / max(period // 2, 1)
        if vol_first > 0:
            vol_trend_score = max(0, min(25, 12.5 + (vol_second / vol_first - 1) * 50))
        else:
            vol_trend_score = 12.5
    else:
        vol_trend_score = 12.5

    return price_score + vol_score + vol_trend_score


# ──────────────────────────────────────────────
#  Paper Exchange
# ───────���──────────────────────────────────────

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
        order = {"id": str(self.order_id), "symbol": symbol, "side": "buy",
                 "price": price, "amount": amount, "status": "open"}
        self.open_orders.append(order)
        return order

    def create_limit_sell_order(self, symbol, amount, price):
        self.order_id += 1
        order = {"id": str(self.order_id), "symbol": symbol, "side": "sell",
                 "price": price, "amount": amount, "status": "open"}
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
#  V3 Pair Grid
# ──────────────────────────────────────────────

class V3PairGrid:
    def __init__(self, symbol, pair_cfg, layers_cfg, exchange, log):
        self.symbol = symbol
        self.coin = symbol.split("/")[0]
        self.exchange = exchange
        self.log = log

        # Base grid
        self.base_lower = pair_cfg["grid"]["lower_price"]
        self.base_upper = pair_cfg["grid"]["upper_price"]
        self.base_investment = pair_cfg["grid"]["investment_usdt"]
        self.num_grids = pair_cfg["grid"]["num_grids"]

        self.lower = self.base_lower
        self.upper = self.base_upper
        self.step = (self.upper - self.lower) / self.num_grids
        self.current_investment = self.base_investment

        # Layer configs
        self.lcfg = layers_cfg

        # History
        self.hourly_highs = deque(maxlen=200)
        self.hourly_lows = deque(maxlen=200)
        self.hourly_closes = deque(maxlen=200)
        self.hourly_volumes = deque(maxlen=200)
        self.daily_closes = deque(maxlen=50)

        # State
        self.active_orders = {}
        self.total_profit = 0.0
        self.total_fees = 0.0
        self.trades_count = 0
        self.buy_count = 0
        self.sell_count = 0
        self.initialized = False

        # Profit lock
        self.peak_value = self.base_investment
        self.profit_floor = 0
        self.locked = False

        # Dynamic sizing
        self.consecutive_wins = 0
        self.consecutive_losses = 0

        # Stats
        self.bb_updates = 0
        self.vwap_adjustments = 0
        self.fg_adjustments = 0

    def _order_amount(self):
        return round(self.current_investment / self.num_grids / ((self.lower + self.upper) / 2), 6)

    def rebuild_grid(self, current_price, buy_mult=1.0, sell_mult=1.0):
        self.exchange.cancel_all_orders(self.symbol)
        self.active_orders.clear()
        self.step = (self.upper - self.lower) / self.num_grids
        grid_levels = [round(self.lower + i * self.step, 2) for i in range(self.num_grids + 1)]
        base_amt = self._order_amount()

        for level in grid_levels:
            if level < current_price:
                amt = round(base_amt * buy_mult, 6)
                if amt > 0:
                    order = self.exchange.create_limit_buy_order(self.symbol, amt, level)
                    self.active_orders[level] = {"order": order, "side": "buy", "amount": amt}
            elif level > current_price:
                amt = round(base_amt * sell_mult, 6)
                if amt > 0:
                    order = self.exchange.create_limit_sell_order(self.symbol, amt, level)
                    self.active_orders[level] = {"order": order, "side": "sell", "amount": amt}

    def update_bollinger_grid(self, current_price):
        """Layer 2: Bollinger Band adaptive grid."""
        cfg = self.lcfg["bollinger"]
        if not cfg["enabled"]:
            return False

        bb = calc_bollinger(list(self.hourly_closes), cfg["period"], cfg["num_std"])
        if bb is None:
            return False

        bb_lower, bb_mid, bb_upper = bb
        # Use Bollinger bands to set grid range, with padding
        padding = (bb_upper - bb_lower) * cfg["padding_pct"]
        new_lower = round(bb_lower - padding, 2)
        new_upper = round(bb_upper + padding, 2)

        # Minimum range
        min_range = current_price * 0.02
        if new_upper - new_lower < min_range:
            new_lower = round(current_price - min_range, 2)
            new_upper = round(current_price + min_range, 2)

        if abs(new_lower - self.lower) / max(self.lower, 1) > 0.02:
            self.lower = new_lower
            self.upper = new_upper
            self.bb_updates += 1
            return True
        return False

    def get_vwap_bias(self):
        """Layer 4: VWAP bias — trade with institutional flow."""
        cfg = self.lcfg["vwap"]
        if not cfg["enabled"]:
            return 1.0, 1.0

        vwap = calc_vwap(
            list(self.hourly_highs), list(self.hourly_lows),
            list(self.hourly_closes), list(self.hourly_volumes),
            cfg["period"]
        )
        if vwap is None:
            return 1.0, 1.0

        current = self.hourly_closes[-1]
        diff_pct = (current - vwap) / vwap * 100

        if diff_pct > cfg["threshold_pct"]:
            # Price above VWAP — favor sells
            self.vwap_adjustments += 1
            return cfg["below_vwap_buy_mult"], cfg["above_vwap_sell_mult"]
        elif diff_pct < -cfg["threshold_pct"]:
            # Price below VWAP — favor buys
            self.vwap_adjustments += 1
            return cfg["below_vwap_buy_mult"], cfg["above_vwap_sell_mult"]

        return 1.0, 1.0

    def get_dynamic_size_mult(self):
        """Layer 5: Dynamic position sizing."""
        cfg = self.lcfg["dynamic_sizing"]
        if not cfg["enabled"]:
            return 1.0

        if self.consecutive_wins >= cfg["win_streak_threshold"]:
            return cfg["win_streak_mult"]
        elif self.consecutive_losses >= cfg["loss_streak_threshold"]:
            return cfg["loss_streak_mult"]
        return 1.0

    def get_fear_greed_mult(self):
        """Layer 9: Fear & Greed contrarian."""
        cfg = self.lcfg["fear_greed"]
        if not cfg["enabled"]:
            return 1.0, 1.0

        fg = calc_fear_greed(
            list(self.hourly_closes), list(self.hourly_volumes),
            cfg["period"]
        )

        if fg <= cfg["extreme_fear"]:
            self.fg_adjustments += 1
            return cfg["fear_buy_mult"], cfg["fear_sell_mult"]
        elif fg >= cfg["extreme_greed"]:
            self.fg_adjustments += 1
            return cfg["greed_buy_mult"], cfg["greed_sell_mult"]
        return 1.0, 1.0

    def get_tp_levels(self):
        """Layer 3: Dynamic take-profit."""
        cfg = self.lcfg["dynamic_tp"]
        if not cfg["enabled"]:
            return 1

        mom = calc_momentum(list(self.hourly_closes), cfg["momentum_period"])
        if abs(mom) > cfg["strong_momentum_pct"]:
            return cfg["strong_skip_levels"]
        elif abs(mom) > cfg["mild_momentum_pct"]:
            return cfg["mild_skip_levels"]
        return 1

    def check_profit_lock(self, current_value):
        """Layer 8: Profit lock / ratchet."""
        cfg = self.lcfg["profit_lock"]
        if not cfg["enabled"]:
            return False

        profit_pct = (current_value - self.base_investment) / self.base_investment * 100

        if current_value > self.peak_value:
            self.peak_value = current_value

        if profit_pct >= cfg["lock_after_pct"]:
            floor_pct = profit_pct * cfg["lock_ratio"]
            new_floor = self.base_investment * (1 + floor_pct / 100)
            if new_floor > self.profit_floor:
                self.profit_floor = new_floor

        if self.profit_floor > 0 and current_value <= self.profit_floor:
            self.locked = True
            return True

        self.locked = False
        return False

    def update(self, current_price, hourly_candle=None, daily_close=None,
               btc_paused=False, drawdown_paused=False):
        if hourly_candle:
            self.hourly_highs.append(hourly_candle["high"])
            self.hourly_lows.append(hourly_candle["low"])
            self.hourly_closes.append(hourly_candle["close"])
            self.hourly_volumes.append(hourly_candle["volume"])
        if daily_close is not None:
            self.daily_closes.append(daily_close)

        # Safety pauses
        if btc_paused or drawdown_paused or self.locked:
            return

        # Bollinger grid update
        if self.update_bollinger_grid(current_price):
            buy_m, sell_m = self.get_combined_multipliers()
            self.rebuild_grid(current_price, buy_m, sell_m)

        # Check fills
        if hasattr(self.exchange, 'check_and_fill'):
            self.exchange.check_and_fill(self.symbol, current_price)

        buy_mult, sell_mult = self.get_combined_multipliers()
        tp_levels = self.get_tp_levels()
        base_amt = self._order_amount()

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
                sell_price = round(level + self.step * tp_levels, 2)
                sell_amt = round(amt * sell_mult, 6)
                if sell_amt > 0:
                    new_order = self.exchange.create_limit_sell_order(self.symbol, sell_amt, sell_price)
                    self.active_orders[sell_price] = {"order": new_order, "side": "sell", "amount": sell_amt}
            else:
                self.sell_count += 1
                profit = amt * self.step * tp_levels * 0.998
                self.total_profit += profit
                if profit > 0:
                    self.consecutive_wins += 1
                    self.consecutive_losses = 0
                else:
                    self.consecutive_losses += 1
                    self.consecutive_wins = 0

                buy_price = round(level - self.step, 2)
                buy_amt = round(base_amt * buy_mult, 6)
                if buy_amt > 0:
                    new_order = self.exchange.create_limit_buy_order(self.symbol, buy_amt, buy_price)
                    self.active_orders[buy_price] = {"order": new_order, "side": "buy", "amount": buy_amt}

        for level in filled_levels:
            if level in self.active_orders:
                del self.active_orders[level]

    def get_combined_multipliers(self):
        """Combine all multipliers from different layers."""
        buy_mult = 1.0
        sell_mult = 1.0

        # VWAP
        vb, vs = self.get_vwap_bias()
        buy_mult *= vb
        sell_mult *= vs

        # Fear & Greed
        fb, fs = self.get_fear_greed_mult()
        buy_mult *= fb
        sell_mult *= fs

        # Dynamic sizing
        size_mult = self.get_dynamic_size_mult()
        buy_mult *= size_mult
        sell_mult *= size_mult

        # Fee optimization (simulate BNB discount)
        if self.lcfg["fee_optimization"]["enabled"]:
            buy_mult *= self.lcfg["fee_optimization"]["size_boost"]
            sell_mult *= self.lcfg["fee_optimization"]["size_boost"]

        return buy_mult, sell_mult


# ──────────────────────────────────────────────
#  V3 Bot (live trading)
# ──────────────────────────────────────────────

class V3Bot:
    def __init__(self, config_path="v3_config.json"):
        self.cfg = load_config(config_path)
        self.paper = self.cfg["paper_trading"]

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(Path(__file__).parent / self.cfg["log_file"]),
                logging.StreamHandler(sys.stdout),
            ],
        )
        self.log = logging.getLogger("V3Bot")

        exchange_class = getattr(ccxt, self.cfg["exchange"])
        self.real_exchange = exchange_class({
            "apiKey": self.cfg.get("api_key", ""),
            "secret": self.cfg.get("api_secret", ""),
            "enableRateLimit": True,
        })

        total_inv = sum(p["grid"]["investment_usdt"] for p in self.cfg["pairs"])
        if self.paper:
            self.log.info("=== PAPER TRADING MODE ===")
            self.exchange = PaperExchange(total_inv, self.real_exchange)
        else:
            self.exchange = self.real_exchange

        self.pairs = []
        for pc in self.cfg["pairs"]:
            pg = V3PairGrid(pc["symbol"], pc, self.cfg["layers"], self.exchange, self.log)
            self.pairs.append(pg)

        self.start_balance = total_inv
        self.peak_portfolio = total_inv
        self.drawdown_paused = False
        self.btc_paused = False
        self.btc_prices = deque(maxlen=50)

    def check_btc_correlation(self):
        """Layer 6: BTC crash detection."""
        cfg = self.cfg["layers"]["btc_correlation"]
        if not cfg["enabled"]:
            return False
        try:
            t = self.exchange.fetch_ticker("BTC/USDT")
            self.btc_prices.append(t["last"])
            if len(self.btc_prices) >= cfg["lookback"]:
                recent = list(self.btc_prices)
                change = (recent[-1] - recent[-cfg["lookback"]]) / recent[-cfg["lookback"]] * 100
                if change < -cfg["crash_threshold_pct"]:
                    return True
        except Exception:
            pass
        return False

    def check_drawdown(self, portfolio_value):
        """Layer 7: Drawdown circuit breaker."""
        cfg = self.cfg["layers"]["drawdown_breaker"]
        if not cfg["enabled"]:
            return False
        if portfolio_value > self.peak_portfolio:
            self.peak_portfolio = portfolio_value
        dd = (self.peak_portfolio - portfolio_value) / self.peak_portfolio * 100
        return dd >= cfg["max_drawdown_pct"]

    def get_portfolio_value(self):
        if not self.paper:
            return self.start_balance
        bal = self.exchange.balance
        total = bal["USDT"]
        for pg in self.pairs:
            amt = bal.get(pg.coin, 0)
            if amt > 0:
                try:
                    t = self.exchange.fetch_ticker(pg.symbol)
                    total += amt * t["last"]
                except Exception:
                    pass
        return total

    def print_status(self):
        self.log.info("─" * 80)
        for pg in self.pairs:
            self.log.info(
                f"  {pg.symbol:>10} | Grid=${pg.lower:.0f}-{pg.upper:.0f} | "
                f"Trades={pg.trades_count} ({pg.buy_count}B/{pg.sell_count}S) | "
                f"Profit=${pg.total_profit:.2f} | "
                f"BB={pg.bb_updates} VWAP={pg.vwap_adjustments} FG={pg.fg_adjustments}"
            )
        pv = self.get_portfolio_value()
        pnl = pv - self.start_balance
        pnl_pct = (pnl / self.start_balance) * 100
        self.log.info(
            f"  {'TOTAL':>10} | Value=${pv:.2f} | P&L=${pnl:.2f} ({pnl_pct:+.2f}%) | "
            f"BTC_pause={self.btc_paused} | DD_pause={self.drawdown_paused}"
        )
        self.log.info("─" * 80)

    def run(self):
        layers = self.cfg["layers"]
        self.log.info("=" * 80)
        self.log.info("  GRID BOT V3 — FULL STACK")
        self.log.info(f"  Pairs: {[p.symbol for p in self.pairs]}")
        for name, lcfg in layers.items():
            if isinstance(lcfg, dict) and "enabled" in lcfg:
                self.log.info(f"  {name}: {'ON' if lcfg['enabled'] else 'OFF'}")
        self.log.info("=" * 80)

        # Load history
        for pg in self.pairs:
            try:
                c1h = self.exchange.fetch_ohlcv(pg.symbol, "1h", limit=100)
                for c in c1h:
                    pg.hourly_highs.append(c[2])
                    pg.hourly_lows.append(c[3])
                    pg.hourly_closes.append(c[4])
                    pg.hourly_volumes.append(c[5])
                c1d = self.exchange.fetch_ohlcv(pg.symbol, "1d", limit=30)
                for c in c1d:
                    pg.daily_closes.append(c[4])
            except Exception as e:
                self.log.warning(f"  [{pg.symbol}] History: {e}")

        for pg in self.pairs:
            t = self.exchange.fetch_ticker(pg.symbol)
            pg.update_bollinger_grid(t["last"])
            bm, sm = pg.get_combined_multipliers()
            pg.rebuild_grid(t["last"], bm, sm)
            pg.initialized = True
            self.log.info(f"  [{pg.symbol}] Grid: ${pg.lower:.0f}-${pg.upper:.0f}")

        self.log.info("\nRunning...\n")
        cycle = 0
        interval = self.cfg["check_interval_seconds"]

        while True:
            try:
                cycle += 1
                pv = self.get_portfolio_value()

                self.btc_paused = self.check_btc_correlation()
                self.drawdown_paused = self.check_drawdown(pv)

                for pg in self.pairs:
                    t = self.exchange.fetch_ticker(pg.symbol)
                    pg.check_profit_lock(pv / len(self.pairs))
                    pg.update(t["last"], btc_paused=self.btc_paused,
                              drawdown_paused=self.drawdown_paused)

                if cycle % 20 == 0:
                    self.print_status()

                time.sleep(interval)

            except ccxt.NetworkError as e:
                self.log.warning(f"Network: {e}")
                time.sleep(60)
            except ccxt.ExchangeError as e:
                self.log.error(f"Exchange: {e}")
                time.sleep(60)
            except KeyboardInterrupt:
                self.log.info("\nStopping...")
                self.print_status()
                break


if __name__ == "__main__":
    bot = V3Bot()
    bot.run()
