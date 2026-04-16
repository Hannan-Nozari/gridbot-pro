"""
Crypto Grid Trading Bot
-----------------------
Runs 24/7. Places buy/sell orders across a price grid.
Profits from price bouncing within a range.

Default: PAPER TRADING (no real money).
"""

import json
import time
import logging
import sys
from datetime import datetime
from pathlib import Path

import ccxt


def load_config(path="config.json"):
    with open(Path(__file__).parent / path) as f:
        return json.load(f)


class PaperExchange:
    """Simulates an exchange for paper trading."""

    def __init__(self, balance_usdt, real_exchange):
        self.balance = {"USDT": balance_usdt, "ETH": 0.0}
        self.real_exchange = real_exchange
        self.open_orders = []
        self.order_id = 0
        self.filled_orders = []

    def fetch_ticker(self, symbol):
        return self.real_exchange.fetch_ticker(symbol)

    def create_limit_buy_order(self, symbol, amount, price):
        self.order_id += 1
        order = {
            "id": str(self.order_id),
            "symbol": symbol,
            "side": "buy",
            "type": "limit",
            "price": price,
            "amount": amount,
            "status": "open",
            "filled": 0,
        }
        self.open_orders.append(order)
        return order

    def create_limit_sell_order(self, symbol, amount, price):
        self.order_id += 1
        order = {
            "id": str(self.order_id),
            "symbol": symbol,
            "side": "sell",
            "type": "limit",
            "price": price,
            "amount": amount,
            "status": "open",
            "filled": 0,
        }
        self.open_orders.append(order)
        return order

    def cancel_order(self, order_id, symbol=None):
        self.open_orders = [o for o in self.open_orders if o["id"] != order_id]

    def fetch_open_orders(self, symbol=None):
        return self.open_orders

    def check_and_fill(self, current_price):
        """Simulate fills based on current market price."""
        still_open = []
        for order in self.open_orders:
            filled = False
            if order["side"] == "buy" and current_price <= order["price"]:
                cost = order["amount"] * order["price"]
                fee = cost * 0.001  # 0.1% fee
                if self.balance["USDT"] >= cost + fee:
                    self.balance["USDT"] -= cost + fee
                    self.balance["ETH"] += order["amount"]
                    order["status"] = "closed"
                    order["filled"] = order["amount"]
                    order["fee"] = fee
                    self.filled_orders.append(order)
                    filled = True

            elif order["side"] == "sell" and current_price >= order["price"]:
                if self.balance["ETH"] >= order["amount"]:
                    revenue = order["amount"] * order["price"]
                    fee = revenue * 0.001
                    self.balance["USDT"] += revenue - fee
                    self.balance["ETH"] -= order["amount"]
                    order["status"] = "closed"
                    order["filled"] = order["amount"]
                    order["fee"] = fee
                    self.filled_orders.append(order)
                    filled = True

            if not filled:
                still_open.append(order)

        self.open_orders = still_open
        return self.filled_orders[-len(self.filled_orders):]


class GridBot:
    def __init__(self, config_path="config.json", on_trade=None):
        self.cfg = load_config(config_path)
        self.symbol = self.cfg["symbol"]
        self.grid = self.cfg["grid"]
        self.paper = self.cfg["paper_trading"]
        self.on_trade = on_trade
        self._running = False

        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(Path(__file__).parent / self.cfg["log_file"]),
                logging.StreamHandler(sys.stdout),
            ],
        )
        self.log = logging.getLogger("GridBot")

        # Connect to real exchange (for price data at minimum)
        exchange_class = getattr(ccxt, self.cfg["exchange"])
        self.real_exchange = exchange_class({
            "apiKey": self.cfg["api_key"],
            "secret": self.cfg["api_secret"],
            "enableRateLimit": True,
        })

        if self.paper:
            self.log.info("=== PAPER TRADING MODE ===")
            self.exchange = PaperExchange(
                self.cfg["initial_balance_usdt"], self.real_exchange
            )
        else:
            self.exchange = self.real_exchange

        # Grid state
        self.grid_levels = []
        self.active_orders = {}  # price_level -> order
        self.total_profit = 0.0
        self.total_fees = 0.0
        self.trades_count = 0
        self.start_balance = self.cfg["initial_balance_usdt"]

    def calculate_grid(self):
        """Calculate grid price levels."""
        lower = self.grid["lower_price"]
        upper = self.grid["upper_price"]
        num = self.grid["num_grids"]
        step = (upper - lower) / num
        self.grid_levels = [round(lower + i * step, 2) for i in range(num + 1)]
        self.order_amount = round(
            self.grid["total_investment_usdt"] / num / ((lower + upper) / 2), 6
        )
        self.log.info(f"Grid: {num} levels from ${lower} to ${upper}")
        self.log.info(f"Step size: ${step:.2f}")
        self.log.info(f"Order size: {self.order_amount} {self.symbol.split('/')[0]}")

    def get_price(self):
        """Get current market price."""
        ticker = self.exchange.fetch_ticker(self.symbol)
        return ticker["last"]

    def place_initial_orders(self, current_price):
        """Place buy orders below price, sell orders above."""
        self.log.info(f"Current price: ${current_price:.2f}")
        for level in self.grid_levels:
            if level < current_price:
                order = self.exchange.create_limit_buy_order(
                    self.symbol, self.order_amount, level
                )
                self.active_orders[level] = {"order": order, "side": "buy"}
                self.log.info(f"  BUY  order at ${level:.2f}")
            elif level > current_price:
                order = self.exchange.create_limit_sell_order(
                    self.symbol, self.order_amount, level
                )
                self.active_orders[level] = {"order": order, "side": "sell"}
                self.log.info(f"  SELL order at ${level:.2f}")

    def check_and_replace_orders(self, current_price):
        """Check fills and place counter-orders."""
        if self.paper:
            self.exchange.check_and_fill(current_price)

        filled_levels = []
        for level, info in self.active_orders.items():
            order = info["order"]
            if self.paper:
                is_filled = order["status"] == "closed"
            else:
                try:
                    updated = self.exchange.fetch_order(order["id"], self.symbol)
                    is_filled = updated["status"] == "closed"
                except Exception:
                    is_filled = False

            if is_filled:
                filled_levels.append(level)
                side = info["side"]
                self.trades_count += 1

                if side == "buy":
                    # Buy filled -> place sell one grid level up
                    sell_price = level + (self.grid_levels[1] - self.grid_levels[0])
                    profit = self.order_amount * (sell_price - level) * 0.999  # after fee
                    self.log.info(
                        f"  BUY  FILLED at ${level:.2f} -> "
                        f"placing SELL at ${sell_price:.2f} "
                        f"(potential profit: ${profit:.4f})"
                    )
                    new_order = self.exchange.create_limit_sell_order(
                        self.symbol, self.order_amount, sell_price
                    )
                    self.active_orders[sell_price] = {"order": new_order, "side": "sell"}

                    if self.on_trade:
                        self.on_trade({
                            "side": "buy",
                            "price": level,
                            "amount": self.order_amount,
                            "symbol": self.symbol,
                            "timestamp": datetime.utcnow().isoformat(),
                        })

                else:
                    # Sell filled -> place buy one grid level down
                    buy_price = level - (self.grid_levels[1] - self.grid_levels[0])
                    step = self.grid_levels[1] - self.grid_levels[0]
                    profit = self.order_amount * step * 0.999
                    self.total_profit += profit
                    self.log.info(
                        f"  SELL FILLED at ${level:.2f} -> "
                        f"placing BUY  at ${buy_price:.2f} "
                        f"(realized profit: ${profit:.4f})"
                    )
                    new_order = self.exchange.create_limit_buy_order(
                        self.symbol, self.order_amount, buy_price
                    )
                    self.active_orders[buy_price] = {"order": new_order, "side": "buy"}

                    if self.on_trade:
                        self.on_trade({
                            "side": "sell",
                            "price": level,
                            "amount": self.order_amount,
                            "symbol": self.symbol,
                            "profit": profit,
                            "timestamp": datetime.utcnow().isoformat(),
                        })

        for level in filled_levels:
            del self.active_orders[level]

    def print_status(self):
        """Print current bot status."""
        if self.paper:
            bal = self.exchange.balance
            total_value = bal["USDT"] + bal["ETH"] * self.get_price()
            pnl = total_value - self.start_balance
            pnl_pct = (pnl / self.start_balance) * 100
            self.log.info(
                f"  Status: USDT={bal['USDT']:.2f} | "
                f"ETH={bal['ETH']:.6f} | "
                f"Total=${total_value:.2f} | "
                f"P&L=${pnl:.2f} ({pnl_pct:+.2f}%) | "
                f"Trades={self.trades_count}"
            )
        else:
            self.log.info(
                f"  Realized profit: ${self.total_profit:.4f} | "
                f"Trades: {self.trades_count}"
            )

    def get_status(self):
        """Return current bot status as a dict."""
        try:
            current_price = self.get_price()
        except Exception:
            current_price = 0.0

        if self.paper:
            bal = self.exchange.balance
            balance_usdt = bal.get("USDT", 0.0)
            balance_coin = bal.get("ETH", 0.0)
            portfolio_value = balance_usdt + balance_coin * current_price
        else:
            balance_usdt = 0.0
            balance_coin = 0.0
            portfolio_value = self.start_balance + self.total_profit

        return {
            "status": "running" if self._running else "stopped",
            "total_profit": self.total_profit,
            "total_fees": self.total_fees,
            "num_trades": self.trades_count,
            "balance_usdt": balance_usdt,
            "balance_coin": balance_coin,
            "active_orders": len(self.active_orders),
            "current_price": current_price,
            "portfolio_value": portfolio_value,
        }

    def stop(self):
        """Stop the bot gracefully."""
        self._running = False

    def run(self):
        """Main loop."""
        self._running = True
        self.log.info("=" * 50)
        self.log.info("  GRID BOT STARTING")
        self.log.info(f"  Pair: {self.symbol}")
        self.log.info(f"  Paper: {self.paper}")
        self.log.info("=" * 50)

        self.calculate_grid()
        current_price = self.get_price()
        self.place_initial_orders(current_price)
        self.log.info(f"Placed {len(self.active_orders)} initial orders. Running...\n")

        cycle = 0
        interval = self.cfg["check_interval_seconds"]

        while self._running:
            try:
                cycle += 1
                current_price = self.get_price()
                self.check_and_replace_orders(current_price)

                if cycle % 10 == 0:  # Status every 10 cycles
                    self.log.info(f"--- Cycle {cycle} | Price: ${current_price:.2f} ---")
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
    bot = GridBot()
    bot.run()
