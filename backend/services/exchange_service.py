"""
Exchange Service
-----------------
Wraps CCXT for Binance exchange access and provides a PaperExchange
for simulated order fills during paper trading and backtesting.
"""

import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

import ccxt
import pandas as pd

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Paper Exchange
# ──────────────────────────────────────────────

class PaperExchange:
    """Simulates an exchange for paper trading.

    Tracks balances and open orders.  When ``check_and_fill`` is called
    with the current market price, limit orders whose price condition is
    met are filled and balances are updated (including a configurable
    maker/taker fee).
    """

    DEFAULT_FEE_RATE = 0.001  # 0.1 %

    def __init__(
        self,
        balance_usdt: float,
        real_exchange: ccxt.Exchange,
        fee_rate: float = DEFAULT_FEE_RATE,
    ) -> None:
        self.balance: Dict[str, float] = {"USDT": balance_usdt}
        self.real_exchange = real_exchange
        self.fee_rate = fee_rate
        self.open_orders: List[dict] = []
        self.filled_orders: List[dict] = []
        self._order_id = 0

    # -- Market data (delegated to the real exchange) ---------------------

    def fetch_ticker(self, symbol: str) -> dict:
        return self.real_exchange.fetch_ticker(symbol)

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list:
        return self.real_exchange.fetch_ohlcv(
            symbol, timeframe, since=since, limit=limit
        )

    # -- Helpers ----------------------------------------------------------

    def _coin(self, symbol: str) -> str:
        return symbol.split("/")[0]

    def _next_id(self) -> str:
        self._order_id += 1
        return str(self._order_id)

    # -- Order management -------------------------------------------------

    def create_limit_buy_order(
        self, symbol: str, amount: float, price: float
    ) -> dict:
        order = {
            "id": self._next_id(),
            "symbol": symbol,
            "side": "buy",
            "type": "limit",
            "price": price,
            "amount": amount,
            "filled": 0.0,
            "remaining": amount,
            "status": "open",
            "timestamp": int(time.time() * 1000),
            "fee": 0.0,
        }
        self.open_orders.append(order)
        return order

    def create_limit_sell_order(
        self, symbol: str, amount: float, price: float
    ) -> dict:
        order = {
            "id": self._next_id(),
            "symbol": symbol,
            "side": "sell",
            "type": "limit",
            "price": price,
            "amount": amount,
            "filled": 0.0,
            "remaining": amount,
            "status": "open",
            "timestamp": int(time.time() * 1000),
            "fee": 0.0,
        }
        self.open_orders.append(order)
        return order

    def create_market_buy_order(
        self, symbol: str, amount: float
    ) -> dict:
        """Immediately fill a market buy at the current ticker price."""
        ticker = self.fetch_ticker(symbol)
        price = ticker["last"]
        order = {
            "id": self._next_id(),
            "symbol": symbol,
            "side": "buy",
            "type": "market",
            "price": price,
            "amount": amount,
            "filled": amount,
            "remaining": 0.0,
            "status": "closed",
            "timestamp": int(time.time() * 1000),
        }
        cost = amount * price
        fee = cost * self.fee_rate
        coin = self._coin(symbol)
        if self.balance.get("USDT", 0) >= cost + fee:
            self.balance["USDT"] = self.balance.get("USDT", 0) - cost - fee
            self.balance[coin] = self.balance.get(coin, 0) + amount
            order["fee"] = fee
        else:
            order["status"] = "rejected"
            order["fee"] = 0.0
        self.filled_orders.append(order)
        return order

    def create_market_sell_order(
        self, symbol: str, amount: float
    ) -> dict:
        """Immediately fill a market sell at the current ticker price."""
        ticker = self.fetch_ticker(symbol)
        price = ticker["last"]
        order = {
            "id": self._next_id(),
            "symbol": symbol,
            "side": "sell",
            "type": "market",
            "price": price,
            "amount": amount,
            "filled": amount,
            "remaining": 0.0,
            "status": "closed",
            "timestamp": int(time.time() * 1000),
        }
        coin = self._coin(symbol)
        revenue = amount * price
        fee = revenue * self.fee_rate
        if self.balance.get(coin, 0) >= amount:
            self.balance[coin] = self.balance.get(coin, 0) - amount
            self.balance["USDT"] = self.balance.get("USDT", 0) + revenue - fee
            order["fee"] = fee
        else:
            order["status"] = "rejected"
            order["fee"] = 0.0
        self.filled_orders.append(order)
        return order

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> dict:
        for i, o in enumerate(self.open_orders):
            if o["id"] == order_id:
                o["status"] = "canceled"
                self.open_orders.pop(i)
                return o
        return {"id": order_id, "status": "not_found"}

    def cancel_all_orders(self, symbol: str) -> List[dict]:
        canceled = []
        remaining = []
        for o in self.open_orders:
            if o["symbol"] == symbol:
                o["status"] = "canceled"
                canceled.append(o)
            else:
                remaining.append(o)
        self.open_orders = remaining
        return canceled

    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[dict]:
        if symbol is None:
            return list(self.open_orders)
        return [o for o in self.open_orders if o["symbol"] == symbol]

    def fetch_balance(self) -> dict:
        return dict(self.balance)

    # -- Fill simulation --------------------------------------------------

    def check_and_fill(
        self, symbol: str, current_price: float
    ) -> List[dict]:
        """Check open orders for *symbol* and fill any whose limit price
        has been reached.  Returns a list of newly-filled orders."""
        coin = self._coin(symbol)
        self.balance.setdefault(coin, 0.0)

        still_open: List[dict] = []
        newly_filled: List[dict] = []

        for order in self.open_orders:
            if order["symbol"] != symbol:
                still_open.append(order)
                continue

            filled = False

            if order["side"] == "buy" and current_price <= order["price"]:
                cost = order["amount"] * order["price"]
                fee = cost * self.fee_rate
                if self.balance.get("USDT", 0) >= cost + fee:
                    self.balance["USDT"] -= cost + fee
                    self.balance[coin] += order["amount"]
                    order["status"] = "closed"
                    order["filled"] = order["amount"]
                    order["remaining"] = 0.0
                    order["fee"] = fee
                    newly_filled.append(order)
                    filled = True

            elif order["side"] == "sell" and current_price >= order["price"]:
                if self.balance.get(coin, 0) >= order["amount"]:
                    revenue = order["amount"] * order["price"]
                    fee = revenue * self.fee_rate
                    self.balance["USDT"] += revenue - fee
                    self.balance[coin] -= order["amount"]
                    order["status"] = "closed"
                    order["filled"] = order["amount"]
                    order["remaining"] = 0.0
                    order["fee"] = fee
                    newly_filled.append(order)
                    filled = True

            if not filled:
                still_open.append(order)

        self.open_orders = still_open
        self.filled_orders.extend(newly_filled)
        return newly_filled


# ──────────────────────────────────────────────
#  Exchange Service
# ──────────────────────────────────────────────

class ExchangeService:
    """High-level wrapper around CCXT / PaperExchange."""

    def __init__(self) -> None:
        self._exchanges: Dict[str, Union[ccxt.Exchange, PaperExchange]] = {}

    # -- Factory ----------------------------------------------------------

    @staticmethod
    def get_exchange(
        api_key: str = "",
        api_secret: str = "",
        paper: bool = True,
        paper_balance: float = 10_000.0,
    ) -> Union[ccxt.Exchange, PaperExchange]:
        """Return a live Binance exchange or a :class:`PaperExchange`.

        Parameters
        ----------
        api_key, api_secret:
            Binance API credentials (ignored for paper mode).
        paper:
            If ``True`` return a ``PaperExchange`` backed by a real
            Binance connection for market data only.
        paper_balance:
            Starting USDT balance for paper trading.
        """
        real = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
        if paper:
            return PaperExchange(paper_balance, real)
        return real

    # -- Market data helpers ----------------------------------------------

    @staticmethod
    def fetch_ohlcv(
        exchange: Union[ccxt.Exchange, PaperExchange],
        symbol: str,
        timeframe: str = "1h",
        days: int = 30,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV candles and return a DataFrame.

        Handles pagination for large requests automatically.
        """
        real = (
            exchange.real_exchange
            if isinstance(exchange, PaperExchange)
            else exchange
        )
        since = real.milliseconds() - days * 86_400_000
        all_candles: List[list] = []

        while since < real.milliseconds():
            batch = real.fetch_ohlcv(
                symbol, timeframe, since=since, limit=1000
            )
            if not batch:
                break
            all_candles.extend(batch)
            since = batch[-1][0] + 1
            # Respect rate limits
            time.sleep(real.rateLimit / 1000)

        if not all_candles:
            return pd.DataFrame(
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )

        df = pd.DataFrame(
            all_candles,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
        return df

    @staticmethod
    def fetch_ticker(
        exchange: Union[ccxt.Exchange, PaperExchange],
        symbol: str,
    ) -> dict:
        """Get the current ticker for *symbol*."""
        if isinstance(exchange, PaperExchange):
            return exchange.fetch_ticker(symbol)
        return exchange.fetch_ticker(symbol)

    @staticmethod
    def fetch_available_pairs(
        exchange: Union[ccxt.Exchange, PaperExchange],
    ) -> List[str]:
        """Return a sorted list of active USDT spot trading pairs."""
        real = (
            exchange.real_exchange
            if isinstance(exchange, PaperExchange)
            else exchange
        )
        real.load_markets()
        pairs: List[str] = []
        for symbol, market in real.markets.items():
            if (
                market.get("quote") == "USDT"
                and market.get("active", True)
                and market.get("spot", False)
            ):
                pairs.append(symbol)
        return sorted(pairs)
