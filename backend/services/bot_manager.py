"""
Bot Manager
-------------
Manages the full lifecycle of trading bots: creation, start, stop,
status queries, and persistence of trades to a SQLite database.
"""

import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

import ccxt

from bots.strategies import (
    GridStrategy,
    DCAStrategy,
    MeanReversionStrategy,
    MomentumStrategy,
    CombinedStrategy,
)
from services.exchange_service import ExchangeService, PaperExchange

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Live bot wrapper
# ──────────────────────────────────────────────

class LiveBot:
    """Wraps a strategy instance and runs it in a polling loop,
    fetching live candle data on each tick."""

    def __init__(
        self,
        bot_id: str,
        strategy,
        exchange: Union[ccxt.Exchange, PaperExchange],
        symbol: str,
        interval_seconds: int = 60,
        on_trade: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self.bot_id = bot_id
        self.strategy = strategy
        self.exchange = exchange
        self.symbol = symbol
        self.interval_seconds = interval_seconds
        self.on_trade = on_trade

        self._running = False
        self._started_at: Optional[str] = None
        self._last_tick: Optional[str] = None
        self._error: Optional[str] = None
        self._prev_trade_count = 0

    # -- Main loop --------------------------------------------------------

    def run(self) -> None:
        """Blocking loop that runs until ``_running`` is set to False."""
        self._running = True
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._error = None
        self._prev_trade_count = self.strategy.num_trades

        logger.info("[%s] Bot started for %s", self.bot_id, self.symbol)

        while self._running:
            try:
                self._tick()
                self._last_tick = datetime.now(timezone.utc).isoformat()
            except ccxt.NetworkError as exc:
                logger.warning("[%s] Network error: %s", self.bot_id, exc)
                self._error = str(exc)
                time.sleep(30)
                continue
            except ccxt.ExchangeError as exc:
                logger.error("[%s] Exchange error: %s", self.bot_id, exc)
                self._error = str(exc)
                time.sleep(30)
                continue
            except Exception as exc:
                logger.exception("[%s] Unexpected error", self.bot_id)
                self._error = str(exc)
                time.sleep(30)
                continue

            time.sleep(self.interval_seconds)

        logger.info("[%s] Bot stopped", self.bot_id)

    def _tick(self) -> None:
        """Fetch latest candle and feed to the strategy."""
        # Get the most recent closed 1-hour candle
        candles = self.exchange.fetch_ohlcv(
            self.symbol, "1h", limit=2
        ) if not isinstance(self.exchange, PaperExchange) else (
            self.exchange.real_exchange.fetch_ohlcv(
                self.symbol, "1h", limit=2
            )
        )

        if not candles or len(candles) < 2:
            return

        # Use the second-to-last candle (the latest *closed* candle)
        candle = candles[-2]
        ts_ms, open_, high, low, close, volume = candle
        ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)

        self.strategy.update(ts, high, low, close, volume)

        # If paper exchange, simulate fills at the current price
        if isinstance(self.exchange, PaperExchange):
            ticker = self.exchange.fetch_ticker(self.symbol)
            self.exchange.check_and_fill(self.symbol, ticker["last"])

        # Check for new trades and fire callback
        current_count = self.strategy.num_trades
        if current_count > self._prev_trade_count and self.on_trade:
            new_trades = self.strategy.trades[self._prev_trade_count:]
            for trade in new_trades:
                try:
                    self.on_trade(self.bot_id, trade)
                except Exception:
                    logger.exception(
                        "[%s] on_trade callback failed", self.bot_id
                    )
            self._prev_trade_count = current_count

    # -- Properties -------------------------------------------------------

    @property
    def status(self) -> Dict[str, Any]:
        current_price = None
        try:
            if isinstance(self.exchange, PaperExchange):
                ticker = self.exchange.fetch_ticker(self.symbol)
            else:
                ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = ticker.get("last")
        except Exception:
            pass

        portfolio_value = (
            self.strategy.value(current_price) if current_price else None
        )

        return {
            "bot_id": self.bot_id,
            "symbol": self.symbol,
            "running": self._running,
            "started_at": self._started_at,
            "last_tick": self._last_tick,
            "error": self._error,
            "num_trades": self.strategy.num_trades,
            "total_profit": round(self.strategy.total_profit, 4),
            "total_fees": round(self.strategy.total_fees, 6),
            "current_price": current_price,
            "portfolio_value": (
                round(portfolio_value, 4) if portfolio_value else None
            ),
        }


# ──────────────────────────────────────────────
#  Database helpers
# ──────────────────────────────────────────────

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS bot_instances (
    bot_id       TEXT PRIMARY KEY,
    bot_type     TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    config_json  TEXT NOT NULL,
    paper        INTEGER NOT NULL DEFAULT 1,
    status       TEXT NOT NULL DEFAULT 'stopped',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_trades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id       TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    side         TEXT NOT NULL,
    price        REAL NOT NULL,
    amount       REAL NOT NULL,
    profit       REAL,
    fee          REAL,
    FOREIGN KEY (bot_id) REFERENCES bot_instances(bot_id)
);
"""


def _init_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_CREATE_TABLES_SQL)
    conn.commit()
    conn.close()


def _save_trade(db_path: str, bot_id: str, trade: dict) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO bot_trades (bot_id, timestamp, side, price, amount, profit, fee)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            bot_id,
            str(trade.get("time", datetime.now(timezone.utc).isoformat())),
            trade.get("side", ""),
            trade.get("price", 0),
            trade.get("amount", 0),
            trade.get("profit"),
            trade.get("fee"),
        ),
    )
    conn.commit()
    conn.close()


def _update_bot_status(db_path: str, bot_id: str, status: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """UPDATE bot_instances SET status = ?, updated_at = ? WHERE bot_id = ?""",
        (status, datetime.now(timezone.utc).isoformat(), bot_id),
    )
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
#  Bot Manager
# ──────────────────────────────────────────────

class BotManager:
    """Manages bot lifecycle: create, start, stop, status.

    Parameters
    ----------
    db_path:
        Path to the SQLite database for persisting bots and trades.
    broadcast_callback:
        Optional callable ``(event_type: str, data: dict) -> None``
        invoked on WebSocket-worthy events such as trade fills or
        status changes.
    """

    STRATEGY_MAP: Dict[str, type] = {
        "grid": GridStrategy,
        "dca": DCAStrategy,
        "mean_reversion": MeanReversionStrategy,
        "momentum": MomentumStrategy,
        "combined": CombinedStrategy,
    }

    def __init__(
        self,
        db_path: str = "./data/trading.db",
        broadcast_callback: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self.db_path = db_path
        self.broadcast = broadcast_callback
        self.bots: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        _init_db(db_path)

    # -- Helpers ----------------------------------------------------------

    def _on_trade(self, bot_id: str, trade: dict) -> None:
        """Callback fired by LiveBot when a trade is executed."""
        try:
            _save_trade(self.db_path, bot_id, trade)
        except Exception:
            logger.exception("Failed to persist trade for %s", bot_id)

        if self.broadcast:
            try:
                self.broadcast("trade_executed", {
                    "bot_id": bot_id,
                    "trade": trade,
                })
            except Exception:
                logger.exception("broadcast failed for trade on %s", bot_id)

    def _build_strategy(
        self, bot_type: str, config: Dict[str, Any]
    ):
        """Instantiate the correct strategy from *bot_type* and *config*."""
        key = bot_type.lower().strip()
        cls = self.STRATEGY_MAP.get(key)
        if cls is None:
            raise ValueError(
                f"Unknown bot type '{bot_type}'. "
                f"Choose from: {list(self.STRATEGY_MAP.keys())}"
            )

        investment = config.get("investment", 1000.0)

        if key == "grid":
            return cls(
                lower=config.get("lower", config.get("lower_price", 1500)),
                upper=config.get("upper", config.get("upper_price", 2500)),
                num_grids=config.get("num_grids", 10),
                investment=investment,
            )
        elif key == "dca":
            return cls(
                investment=investment,
                buy_interval_hours=config.get("buy_interval_hours", 4),
                take_profit_pct=config.get("take_profit_pct", 3.0),
                chunk_pct=config.get("chunk_pct", 2.0),
            )
        elif key == "mean_reversion":
            return cls(
                investment=investment,
                bb_period=config.get("bb_period", 20),
                bb_std=config.get("bb_std", 2.0),
                z_entry=config.get("z_entry", 2.0),
                z_exit=config.get("z_exit", 0.5),
                position_pct=config.get("position_pct", 10.0),
            )
        elif key == "momentum":
            return cls(
                investment=investment,
                fast_ema=config.get("fast_ema", 12),
                slow_ema=config.get("slow_ema", 26),
                atr_period=config.get("atr_period", 14),
                atr_stop_mult=config.get("atr_stop_mult", 2.0),
                position_pct=config.get("position_pct", 30.0),
            )
        elif key == "combined":
            return cls(
                investment=investment,
                grid_lower=config.get("grid_lower", config.get("lower_price", 1500)),
                grid_upper=config.get("grid_upper", config.get("upper_price", 2500)),
                grid_num=config.get("grid_num", config.get("num_grids", 10)),
            )
        raise ValueError(f"Unhandled bot type: {key}")

    # -- Public API -------------------------------------------------------

    def create_bot(
        self,
        bot_id: Optional[str],
        bot_type: str,
        config: Dict[str, Any],
        paper: bool = True,
    ) -> str:
        """Create a new bot and register it.

        Parameters
        ----------
        bot_id:
            Unique identifier.  If ``None`` one is generated.
        bot_type:
            One of ``"grid"``, ``"dca"``, ``"mean_reversion"``,
            ``"momentum"``, ``"combined"``.
        config:
            Strategy parameters plus ``"symbol"`` and ``"investment"``.
        paper:
            Use paper trading if ``True``.

        Returns
        -------
        str
            The ``bot_id``.
        """
        if bot_id is None:
            bot_id = f"{bot_type}-{uuid.uuid4().hex[:8]}"

        with self._lock:
            if bot_id in self.bots:
                raise ValueError(f"Bot '{bot_id}' already exists.")

            symbol = config.get("symbol", "ETH/USDT")
            investment = config.get("investment", 1000.0)

            # Build exchange
            exchange = ExchangeService.get_exchange(
                api_key=config.get("api_key", ""),
                api_secret=config.get("api_secret", ""),
                paper=paper,
                paper_balance=investment,
            )

            # Build strategy
            strategy = self._build_strategy(bot_type, config)

            # Build live bot
            live_bot = LiveBot(
                bot_id=bot_id,
                strategy=strategy,
                exchange=exchange,
                symbol=symbol,
                interval_seconds=config.get("interval_seconds", 60),
                on_trade=self._on_trade,
            )

            self.bots[bot_id] = {
                "instance": live_bot,
                "thread": None,
                "config": config,
                "bot_type": bot_type,
                "paper": paper,
                "status": "created",
            }

            # Persist to DB
            import json
            now = datetime.now(timezone.utc).isoformat()
            try:
                conn = sqlite3.connect(self.db_path)
                conn.execute(
                    """INSERT OR REPLACE INTO bot_instances
                       (bot_id, bot_type, symbol, config_json, paper, status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (bot_id, bot_type, symbol, json.dumps(config),
                     1 if paper else 0, "created", now, now),
                )
                conn.commit()
                conn.close()
            except Exception:
                logger.exception("Failed to persist bot %s", bot_id)

        logger.info("Created bot %s (%s on %s, paper=%s)", bot_id, bot_type, symbol, paper)
        return bot_id

    def start_bot(self, bot_id: str) -> None:
        """Start the bot's polling loop in a daemon thread."""
        with self._lock:
            entry = self.bots.get(bot_id)
            if entry is None:
                raise KeyError(f"Bot '{bot_id}' not found.")
            if entry["status"] == "running":
                raise RuntimeError(f"Bot '{bot_id}' is already running.")

            live_bot: LiveBot = entry["instance"]
            thread = threading.Thread(
                target=live_bot.run,
                name=f"bot-{bot_id}",
                daemon=True,
            )
            entry["thread"] = thread
            entry["status"] = "running"

        thread.start()
        _update_bot_status(self.db_path, bot_id, "running")

        if self.broadcast:
            self.broadcast("bot_started", {"bot_id": bot_id})

        logger.info("Started bot %s", bot_id)

    def stop_bot(self, bot_id: str, timeout: float = 10.0) -> None:
        """Signal the bot to stop and wait for its thread to finish."""
        with self._lock:
            entry = self.bots.get(bot_id)
            if entry is None:
                raise KeyError(f"Bot '{bot_id}' not found.")

            live_bot: LiveBot = entry["instance"]
            thread: Optional[threading.Thread] = entry["thread"]

        # Signal stop (outside lock so the tick loop can finish)
        live_bot._running = False

        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning(
                    "Bot %s thread did not stop within %.1fs",
                    bot_id,
                    timeout,
                )

        with self._lock:
            entry["status"] = "stopped"
            entry["thread"] = None

        _update_bot_status(self.db_path, bot_id, "stopped")

        if self.broadcast:
            self.broadcast("bot_stopped", {"bot_id": bot_id})

        logger.info("Stopped bot %s", bot_id)

    def remove_bot(self, bot_id: str) -> None:
        """Stop (if running) and remove a bot entirely."""
        with self._lock:
            entry = self.bots.get(bot_id)
            if entry is None:
                raise KeyError(f"Bot '{bot_id}' not found.")

        if entry["status"] == "running":
            self.stop_bot(bot_id)

        with self._lock:
            del self.bots[bot_id]

        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("DELETE FROM bot_instances WHERE bot_id = ?", (bot_id,))
            conn.commit()
            conn.close()
        except Exception:
            logger.exception("Failed to remove bot %s from DB", bot_id)

        logger.info("Removed bot %s", bot_id)

    def get_status(self, bot_id: str) -> Dict[str, Any]:
        """Return current status from the live bot instance."""
        with self._lock:
            entry = self.bots.get(bot_id)
            if entry is None:
                raise KeyError(f"Bot '{bot_id}' not found.")

        live_bot: LiveBot = entry["instance"]
        status = live_bot.status
        status["bot_type"] = entry["bot_type"]
        status["paper"] = entry["paper"]
        status["manager_status"] = entry["status"]
        return status

    def get_all_statuses(self) -> List[Dict[str, Any]]:
        """Return status of every registered bot."""
        with self._lock:
            bot_ids = list(self.bots.keys())

        statuses = []
        for bid in bot_ids:
            try:
                statuses.append(self.get_status(bid))
            except Exception:
                logger.exception("Failed to get status for %s", bid)
        return statuses

    def get_trades(self, bot_id: str, limit: int = 100) -> List[dict]:
        """Retrieve persisted trades for a bot from the database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT * FROM bot_trades
               WHERE bot_id = ?
               ORDER BY id DESC
               LIMIT ?""",
            (bot_id, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
