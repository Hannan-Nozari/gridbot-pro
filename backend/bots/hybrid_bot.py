"""
Hybrid Crypto Trading Bot
--------------------------
Layer 1: Grid trading (base income)
Layer 2: RSI filter (smart pause — avoid buying tops, selling bottoms)
Layer 3: Multi-pair (diversification)
Layer 4: Trailing stop loss (crash protection)

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


def load_config(path="hybrid_config.json"):
    with open(Path(__file__).parent / path) as f:
        return json.load(f)


# ──────────────────────────────────────────────
#  RSI Calculator
# ──────────────────────────────────────────────

class RSICalculator:
    """Calculates RSI from price history."""

    def __init__(self, period=14):
        self.period = period
        self.prices = deque(maxlen=period + 1)

    def update(self, price):
        self.prices.append(price)

    def value(self):
        if len(self.prices) < self.period + 1:
            return 50.0  # neutral until enough data

        gains = []
        losses = []
        prices = list(self.prices)
        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains[-self.period:]) / self.period
        avg_loss = sum(losses[-self.period:]) / self.period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))


# ──────────────────────────────────────────────
#  Paper Exchange (simulated trading)
# ──────────────────────────────────────────────

class PaperExchange:
    def __init__(self, balance_usdt, real_exchange):
        self.balance = {"USDT": balance_usdt}
        self.real_exchange = real_exchange
        self.open_orders = []
        self.order_id = 0
        self.filled_orders = []

    def fetch_ticker(self, symbol):
        return self.real_exchange.fetch_ticker(symbol)

    def fetch_ohlcv(self, symbol, timeframe, limit=None):
        return self.real_exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

    def _coin(self, symbol):
        return symbol.split("/")[0]

    def create_limit_buy_order(self, symbol, amount, price):
        self.order_id += 1
        order = {
            "id": str(self.order_id), "symbol": symbol, "side": "buy",
            "type": "limit", "price": price, "amount": amount,
            "status": "open", "filled": 0,
        }
        self.open_orders.append(order)
        return order

    def create_limit_sell_order(self, symbol, amount, price):
        self.order_id += 1
        order = {
            "id": str(self.order_id), "symbol": symbol, "side": "sell",
            "type": "limit", "price": price, "amount": amount,
            "status": "open", "filled": 0,
        }
        self.open_orders.append(order)
        return order

    def create_market_sell_order(self, symbol, amount):
        """Emergency sell for stop loss."""
        coin = self._coin(symbol)
        if self.balance.get(coin, 0) >= amount:
            ticker = self.fetch_ticker(symbol)
            price = ticker["last"]
            revenue = amount * price * 0.999  # fee
            self.balance["USDT"] += revenue
            self.balance[coin] -= amount
            return {"id": "market", "status": "closed", "price": price}
        return None

    def cancel_all_orders(self, symbol):
        self.open_orders = [o for o in self.open_orders if o["symbol"] != symbol]

    def fetch_open_orders(self, symbol=None):
        if symbol:
            return [o for o in self.open_orders if o["symbol"] == symbol]
        return self.open_orders

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
                    order["filled"] = order["amount"]
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
                    order["filled"] = order["amount"]
                    order["fee"] = fee
                    newly_filled.append(order)
                    filled = True

            if not filled:
                still_open.append(order)

        self.open_orders = still_open
        self.filled_orders.extend(newly_filled)
        return newly_filled


# ──────────────────────────────────────────────
#  Single Pair Grid (with RSI + stop loss)
# ──────────────────────────────────────────────

class PairGrid:
    """Manages grid trading for one pair."""

    def __init__(self, symbol, grid_cfg, rsi_cfg, stop_cfg, exchange, log):
        self.symbol = symbol
        self.exchange = exchange
        self.log = log
        self.coin = symbol.split("/")[0]

        # Grid config
        self.lower = grid_cfg["lower_price"]
        self.upper = grid_cfg["upper_price"]
        self.num_grids = grid_cfg["num_grids"]
        self.investment = grid_cfg["investment_usdt"]
        self.step = (self.upper - self.lower) / self.num_grids
        self.grid_levels = [round(self.lower + i * self.step, 2) for i in range(self.num_grids + 1)]
        self.order_amount = round(self.investment / self.num_grids / ((self.lower + self.upper) / 2), 6)

        # RSI
        self.rsi = RSICalculator(period=rsi_cfg["period"])
        self.rsi_overbought = rsi_cfg["overbought"]
        self.rsi_oversold = rsi_cfg["oversold"]
        self.rsi_enabled = rsi_cfg["enabled"]

        # Stop loss
        self.stop_enabled = stop_cfg["enabled"]
        self.stop_pct = stop_cfg["drop_percent"] / 100
        self.highest_price = 0
        self.stopped = False

        # State
        self.active_orders = {}
        self.total_profit = 0.0
        self.total_fees = 0.0
        self.trades_count = 0
        self.buy_count = 0
        self.sell_count = 0
        self.initialized = False

    def get_price(self):
        ticker = self.exchange.fetch_ticker(self.symbol)
        return ticker["last"]

    def init_rsi_history(self):
        """Load recent candles to warm up RSI."""
        try:
            candles = self.exchange.fetch_ohlcv(self.symbol, "1h", limit=20)
            for c in candles:
                self.rsi.update(c[4])  # close price
        except Exception as e:
            self.log.warning(f"  [{self.symbol}] Could not load RSI history: {e}")

    def place_initial_orders(self, current_price):
        self.log.info(f"  [{self.symbol}] Price: ${current_price:.2f} | Grid: ${self.lower}-${self.upper} | {self.num_grids} levels | ${self.step:.2f} step")
        for level in self.grid_levels:
            if level < current_price:
                order = self.exchange.create_limit_buy_order(self.symbol, self.order_amount, level)
                self.active_orders[level] = {"order": order, "side": "buy"}
            elif level > current_price:
                order = self.exchange.create_limit_sell_order(self.symbol, self.order_amount, level)
                self.active_orders[level] = {"order": order, "side": "sell"}
        self.initialized = True
        self.highest_price = current_price

    def check_stop_loss(self, current_price):
        """Trailing stop loss — if price drops X% from highest, sell everything."""
        if not self.stop_enabled or self.stopped:
            return False

        if current_price > self.highest_price:
            self.highest_price = current_price

        drop = (self.highest_price - current_price) / self.highest_price
        if drop >= self.stop_pct:
            self.log.warning(
                f"  [{self.symbol}] STOP LOSS triggered! "
                f"Price ${current_price:.2f} is {drop*100:.1f}% below peak ${self.highest_price:.2f}"
            )
            # Cancel all open orders
            self.exchange.cancel_all_orders(self.symbol)
            self.active_orders.clear()

            # Sell all held coin
            coin_balance = self.exchange.balance.get(self.coin, 0)
            if coin_balance > 0:
                self.exchange.create_market_sell_order(self.symbol, coin_balance)
                self.log.warning(f"  [{self.symbol}] Sold {coin_balance:.6f} {self.coin} at market")

            self.stopped = True
            return True
        return False

    def check_rsi_filter(self):
        """Returns which sides are allowed based on RSI."""
        if not self.rsi_enabled:
            return True, True  # buy_ok, sell_ok

        rsi_val = self.rsi.value()
        buy_ok = rsi_val < self.rsi_overbought   # don't buy when overbought
        sell_ok = rsi_val > self.rsi_oversold     # don't sell when oversold
        return buy_ok, sell_ok

    def recover_from_stop(self, current_price):
        """Re-enter after stop loss if price recovers."""
        if not self.stopped:
            return

        # If price is back above the lowest grid level, re-enter
        if current_price > self.lower:
            self.log.info(f"  [{self.symbol}] Price recovered to ${current_price:.2f}, re-entering grid")
            self.stopped = False
            self.highest_price = current_price
            self.place_initial_orders(current_price)

    def update(self, current_price):
        """Main update cycle for this pair."""
        if self.stopped:
            self.recover_from_stop(current_price)
            return

        self.rsi.update(current_price)
        buy_ok, sell_ok = self.check_rsi_filter()

        if self.check_stop_loss(current_price):
            return

        # Check fills in paper mode
        if hasattr(self.exchange, 'check_and_fill'):
            self.exchange.check_and_fill(self.symbol, current_price)

        filled_levels = []
        for level, info in list(self.active_orders.items()):
            order = info["order"]
            is_filled = order["status"] == "closed"

            if is_filled:
                filled_levels.append(level)
                side = info["side"]
                self.trades_count += 1

                if side == "buy":
                    self.buy_count += 1
                    sell_price = round(level + self.step, 2)
                    if sell_ok:
                        new_order = self.exchange.create_limit_sell_order(
                            self.symbol, self.order_amount, sell_price
                        )
                        self.active_orders[sell_price] = {"order": new_order, "side": "sell"}
                    rsi_val = self.rsi.value()
                    self.log.info(
                        f"  [{self.symbol}] BUY  filled ${level:.2f} → SELL ${sell_price:.2f} | RSI={rsi_val:.0f}"
                    )
                else:
                    self.sell_count += 1
                    buy_price = round(level - self.step, 2)
                    profit = self.order_amount * self.step * 0.998
                    self.total_profit += profit
                    if buy_ok:
                        new_order = self.exchange.create_limit_buy_order(
                            self.symbol, self.order_amount, buy_price
                        )
                        self.active_orders[buy_price] = {"order": new_order, "side": "buy"}
                    rsi_val = self.rsi.value()
                    self.log.info(
                        f"  [{self.symbol}] SELL filled ${level:.2f} → BUY  ${buy_price:.2f} | +${profit:.4f} | RSI={rsi_val:.0f}"
                    )

        for level in filled_levels:
            if level in self.active_orders:
                del self.active_orders[level]


# ──────────────────────────────────────────────
#  Main Hybrid Bot
# ──────────────────────────────────────────────

class HybridBot:
    def __init__(self, config_path="hybrid_config.json", on_trade=None):
        self.cfg = load_config(config_path)
        self.paper = self.cfg["paper_trading"]
        self.on_trade = on_trade
        self._running = False

        # Logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(Path(__file__).parent / self.cfg["log_file"]),
                logging.StreamHandler(sys.stdout),
            ],
        )
        self.log = logging.getLogger("HybridBot")

        # Exchange
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

        # Create pair grids
        self.pairs = []
        for pair_cfg in self.cfg["pairs"]:
            pg = PairGrid(
                symbol=pair_cfg["symbol"],
                grid_cfg=pair_cfg["grid"],
                rsi_cfg=self.cfg["rsi"],
                stop_cfg=self.cfg["trailing_stop"],
                exchange=self.exchange,
                log=self.log,
            )
            self.pairs.append(pg)

        self.start_balance = total_investment

    def print_status(self):
        self.log.info("─" * 60)
        total_profit = 0
        for pg in self.pairs:
            rsi_val = pg.rsi.value()
            status = "STOPPED" if pg.stopped else "ACTIVE"
            self.log.info(
                f"  {pg.symbol:>10} | {status:>7} | RSI={rsi_val:>5.1f} | "
                f"Trades={pg.trades_count:>4} ({pg.buy_count}B/{pg.sell_count}S) | "
                f"Grid profit=${pg.total_profit:.2f}"
            )
            total_profit += pg.total_profit

        if self.paper:
            bal = self.exchange.balance
            usdt = bal["USDT"]
            coin_value = 0
            for pg in self.pairs:
                coin = pg.coin
                amount = bal.get(coin, 0)
                if amount > 0:
                    try:
                        price = pg.get_price()
                        coin_value += amount * price
                    except Exception:
                        pass
            total = usdt + coin_value
            pnl = total - self.start_balance
            pnl_pct = (pnl / self.start_balance) * 100
            self.log.info(
                f"  {'TOTAL':>10} | USDT=${usdt:.2f} | Coins=${coin_value:.2f} | "
                f"Value=${total:.2f} | P&L=${pnl:.2f} ({pnl_pct:+.2f}%)"
            )
        self.log.info("─" * 60)

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
            current_price = self.pairs[0].get_price() if self.pairs else 0.0
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
                        coin_value += amt * pg.get_price()
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
        self.log.info("=" * 60)
        self.log.info("  HYBRID BOT STARTING")
        self.log.info(f"  Pairs: {[p.symbol for p in self.pairs]}")
        self.log.info(f"  RSI: {'ON' if self.cfg['rsi']['enabled'] else 'OFF'} "
                       f"(period={self.cfg['rsi']['period']}, "
                       f"OB={self.cfg['rsi']['overbought']}, "
                       f"OS={self.cfg['rsi']['oversold']})")
        self.log.info(f"  Stop loss: {'ON' if self.cfg['trailing_stop']['enabled'] else 'OFF'} "
                       f"({self.cfg['trailing_stop']['drop_percent']}% trailing)")
        self.log.info(f"  Paper: {self.paper}")
        self.log.info("=" * 60)

        # Init RSI and place orders
        for pg in self.pairs:
            pg.init_rsi_history()
            price = pg.get_price()
            pg.place_initial_orders(price)

        self.log.info(f"\nAll pairs initialized. Running...\n")

        cycle = 0
        interval = self.cfg["check_interval_seconds"]

        while self._running:
            try:
                cycle += 1
                for pg in self.pairs:
                    price = pg.get_price()
                    old_trades = pg.trades_count
                    pg.update(price)

                    # Fire on_trade callback for new fills
                    if self.on_trade and pg.trades_count > old_trades:
                        self.on_trade({
                            "symbol": pg.symbol,
                            "trades_count": pg.trades_count,
                            "total_profit": pg.total_profit,
                            "price": price,
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
    bot = HybridBot()
    bot.run()
