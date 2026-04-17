"""
Backtest Service
-----------------
Runs a chosen strategy against historical OHLCV data and returns
the full results including equity curve, trades, and computed metrics.
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from bots.strategies import (
    GridStrategy,
    DCAStrategy,
    MeanReversionStrategy,
    MomentumStrategy,
    CombinedStrategy,
)
from services.exchange_service import ExchangeService
from services.analytics_service import compute_metrics

logger = logging.getLogger(__name__)

# ── Strategy name -> class mapping ─────────────────────────────────────

STRATEGY_MAP: Dict[str, type] = {
    "grid": GridStrategy,
    "dca": DCAStrategy,
    "mean_reversion": MeanReversionStrategy,
    "momentum": MomentumStrategy,
    "combined": CombinedStrategy,
}


def _build_strategy(strategy_name: str, params: Dict[str, Any]):
    """Instantiate the correct strategy class from a name and param dict.

    Parameters
    ----------
    strategy_name:
        One of ``"grid"``, ``"dca"``, ``"mean_reversion"``,
        ``"momentum"``, or ``"combined"``.
    params:
        Keyword arguments forwarded to the strategy constructor.
        Must include ``"investment"`` for every strategy.

    Returns
    -------
    Strategy instance.
    """
    key = strategy_name.lower().strip()
    cls = STRATEGY_MAP.get(key)
    if cls is None:
        raise ValueError(
            f"Unknown strategy '{strategy_name}'. "
            f"Choose from: {list(STRATEGY_MAP.keys())}"
        )

    investment = params.get("investment", 1000.0)

    if key == "grid":
        return cls(
            lower=params.get("lower", params.get("lower_price", 1500)),
            upper=params.get("upper", params.get("upper_price", 2500)),
            num_grids=params.get("num_grids", 10),
            investment=investment,
        )
    elif key == "dca":
        return cls(
            investment=investment,
            buy_interval_hours=params.get("buy_interval_hours", 4),
            take_profit_pct=params.get("take_profit_pct", 3.0),
            chunk_pct=params.get("chunk_pct", 2.0),
        )
    elif key == "mean_reversion":
        return cls(
            investment=investment,
            bb_period=params.get("bb_period", 20),
            bb_std=params.get("bb_std", 2.0),
            z_entry=params.get("z_entry", 2.0),
            z_exit=params.get("z_exit", 0.5),
            position_pct=params.get("position_pct", 10.0),
        )
    elif key == "momentum":
        return cls(
            investment=investment,
            fast_ema=params.get("fast_ema", 12),
            slow_ema=params.get("slow_ema", 26),
            atr_period=params.get("atr_period", 14),
            atr_stop_mult=params.get("atr_stop_mult", 2.0),
            position_pct=params.get("position_pct", 30.0),
        )
    elif key == "combined":
        return cls(
            investment=investment,
            grid_lower=params.get("grid_lower", params.get("lower_price", 1500)),
            grid_upper=params.get("grid_upper", params.get("upper_price", 2500)),
            grid_num=params.get("grid_num", params.get("num_grids", 10)),
        )
    # Should not reach here thanks to the check above
    raise ValueError(f"Unhandled strategy key: {key}")


def run_backtest(
    strategy: str,
    symbol: str,
    days: int,
    params: Dict[str, Any],
    exchange: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run a full backtest and return results with metrics.

    Parameters
    ----------
    strategy:
        Strategy name (e.g. ``"grid"``, ``"dca"``).
    symbol:
        Trading pair (e.g. ``"ETH/USDT"``).
    days:
        Number of historical days to backtest.
    params:
        Strategy-specific parameters.  Must include ``"investment"``.
    exchange:
        Optional pre-built exchange/PaperExchange.  If ``None`` a
        temporary Binance connection is created for fetching data.

    Returns
    -------
    dict
        ``{"equity_curve", "trades", "metrics", "summary", "candles"}``
    """
    investment = params.get("investment", 1000.0)

    # ── Fetch OHLCV data ───────────────────────────────────────────────
    # Use the market router's exchange (handles geo-restriction fallback)
    if exchange is None:
        try:
            from routers.market import _get_exchange
            exchange = _get_exchange()
        except Exception:
            exchange = ExchangeService.get_exchange(paper=True)

    logger.info("Fetching %d days of %s %s data for backtest", days, symbol, "1h")

    # Raw ccxt fetch (works with any CCXT-supported exchange)
    import time
    try:
        since = exchange.milliseconds() - days * 86_400_000
        all_candles: List[list] = []
        while since < exchange.milliseconds():
            batch = exchange.fetch_ohlcv(symbol, "1h", since=since, limit=1000)
            if not batch:
                break
            all_candles.extend(batch)
            since = batch[-1][0] + 1
            time.sleep(getattr(exchange, "rateLimit", 500) / 1000)

        if not all_candles:
            raise ValueError(f"No OHLCV data returned for {symbol} over {days} days.")

        df = pd.DataFrame(
            all_candles,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
    except Exception as exc:
        # Fallback to original ExchangeService method
        logger.warning("Direct fetch failed (%s), using ExchangeService", exc)
        df = ExchangeService.fetch_ohlcv(
            exchange, symbol, timeframe="1h", days=days
        )

    if df.empty:
        raise ValueError(
            f"No OHLCV data returned for {symbol} over {days} days."
        )

    logger.info(
        "Loaded %d candles from %s to %s",
        len(df),
        df["timestamp"].iloc[0],
        df["timestamp"].iloc[-1],
    )

    # ── Instantiate strategy ───────────────────────────────────────────
    strat = _build_strategy(strategy, params)

    # ── Run through candles ────────────────────────────────────────────
    equity_curve: List[float] = []
    for _, row in df.iterrows():
        strat.update(
            row["timestamp"],
            row["high"],
            row["low"],
            row["close"],
            row["volume"],
        )
        equity_curve.append(strat.value(row["close"]))

    final_price = float(df["close"].iloc[-1])
    hourly_prices = df["close"].values.tolist()

    # ── Compute metrics ────────────────────────────────────────────────
    metrics = compute_metrics(
        equity_curve=equity_curve,
        trades=strat.trades,
        investment=investment,
        days=days,
        hourly_prices=hourly_prices,
    )

    # Override total_fees from strategy if the analytics service did not
    # find per-trade fees (since our strategy objects track fees directly).
    if strat.total_fees > 0 and metrics.get("total_fees", 0) == 0:
        metrics["total_fees"] = round(strat.total_fees, 6)

    # ── Build response ─────────────────────────────────────────────────
    return {
        "symbol": symbol,
        "strategy": strategy,
        "days": days,
        "investment": investment,
        "final_value": round(strat.value(final_price), 4),
        "equity_curve": equity_curve,
        "trades": strat.trades,
        "num_trades": strat.num_trades,
        "total_profit": round(strat.total_profit, 4),
        "total_fees": round(strat.total_fees, 6),
        "metrics": metrics,
        "candle_count": len(df),
        "start_time": str(df["timestamp"].iloc[0]),
        "end_time": str(df["timestamp"].iloc[-1]),
    }
