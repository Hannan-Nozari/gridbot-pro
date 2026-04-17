"""Market data router — live prices and candles for frontend charts.

Exchange selection:
    Set EXCHANGE_ID env var to any CCXT exchange id.
    Defaults to 'okx' because it's globally accessible (some regions
    block Binance). Popular alternatives: bybit, kraken, kucoin, okx, binance.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["market"], dependencies=[Depends(verify_token)])

# Simple in-memory cache so we don't hammer the exchange
_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL_SECONDS = 30

_exchange = None
_exchange_id = os.environ.get("EXCHANGE_ID", "okx").lower()

# Fallback chain — try these in order if the primary is geo-blocked
_FALLBACK_EXCHANGES = ["okx", "bybit", "kraken", "kucoin", "binance"]


def _try_load(exchange_id: str):
    """Try to load a CCXT exchange and verify it can reach the market."""
    try:
        import ccxt
        cls = getattr(ccxt, exchange_id, None)
        if cls is None:
            return None
        ex = cls({"enableRateLimit": True})
        # Quick sanity check: try a known pair
        ex.fetch_ticker("BTC/USDT")
        logger.info("Using exchange: %s", exchange_id)
        return ex
    except Exception as exc:  # noqa: BLE001
        logger.warning("Exchange %s failed: %s", exchange_id, exc)
        return None


def _get_exchange():
    global _exchange, _exchange_id
    if _exchange is not None:
        return _exchange

    # Try configured exchange first
    _exchange = _try_load(_exchange_id)

    # Fall back through the chain
    if _exchange is None:
        for eid in _FALLBACK_EXCHANGES:
            if eid == _exchange_id:
                continue
            _exchange = _try_load(eid)
            if _exchange is not None:
                _exchange_id = eid
                break

    if _exchange is None:
        raise HTTPException(
            503,
            "No reachable exchange found. "
            "Set EXCHANGE_ID env var or check network.",
        )
    return _exchange


def _cache_key(*parts: Any) -> str:
    return "|".join(str(p) for p in parts)


def _get_cached(key: str):
    entry = _CACHE.get(key)
    if entry and (time.time() - entry["at"]) < _CACHE_TTL_SECONDS:
        return entry["data"]
    return None


def _set_cached(key: str, data: Any) -> None:
    _CACHE[key] = {"at": time.time(), "data": data}


@router.get("/ticker/{symbol:path}")
async def get_ticker(symbol: str):
    """Current price + 24h change for a symbol."""
    key = _cache_key("ticker", symbol)
    cached = _get_cached(key)
    if cached:
        return cached

    try:
        ex = _get_exchange()
        t = ex.fetch_ticker(symbol)
        data = {
            "symbol": symbol,
            "price": float(t.get("last") or 0),
            "change_24h_pct": float(t.get("percentage") or 0),
            "high_24h": float(t.get("high") or 0),
            "low_24h": float(t.get("low") or 0),
            "volume_24h": float(t.get("baseVolume") or 0),
            "timestamp": int(t.get("timestamp") or time.time() * 1000),
        }
        _set_cached(key, data)
        return data
    except Exception as exc:
        logger.exception("Ticker fetch failed for %s", symbol)
        raise HTTPException(502, f"Exchange error: {exc}")


@router.get("/candles/{symbol:path}")
async def get_candles(
    symbol: str,
    timeframe: str = Query("1h", pattern="^(1m|5m|15m|30m|1h|4h|1d)$"),
    limit: int = Query(100, ge=10, le=500),
):
    """
    OHLCV candles for charting. Returns an array of:
        { timestamp, open, high, low, close, volume }
    """
    key = _cache_key("candles", symbol, timeframe, limit)
    cached = _get_cached(key)
    if cached:
        return cached

    try:
        ex = _get_exchange()
        raw = ex.fetch_ohlcv(symbol, timeframe, limit=limit)
        candles = [
            {
                "timestamp": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
            for row in raw
        ]
        data = {"symbol": symbol, "timeframe": timeframe, "candles": candles}
        _set_cached(key, data)
        return data
    except Exception as exc:
        logger.exception("Candles fetch failed for %s", symbol)
        raise HTTPException(502, f"Exchange error: {exc}")


@router.get("/pairs")
async def list_pairs():
    """List supported USDT trading pairs (top by volume)."""
    cached = _get_cached("pairs")
    if cached:
        return cached

    popular = [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
        "XRP/USDT", "DOGE/USDT", "ADA/USDT", "AVAX/USDT",
        "LINK/USDT", "DOT/USDT",
    ]
    data = {"pairs": popular}
    _set_cached("pairs", data)
    return data
