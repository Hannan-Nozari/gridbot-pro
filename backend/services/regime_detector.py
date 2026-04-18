"""
Market Regime Detector
----------------------
Continuously monitors market conditions across multiple signals.
Automatically pauses trading bots when conditions degrade and
resumes them when conditions normalize.

Signals:
    1. BTC 1-hour price change   (crash detection)
    2. BTC 24-hour price change  (large moves)
    3. BTC volatility (ATR%)      (chop vs calm)
    4. BTC trend strength (EMA)   (grids fail in strong trends)
    5. Portfolio drawdown         (circuit breaker)

Regimes:
    GOOD    (🟢) - 0 bad signals, trade normally
    CAUTION (🟡) - 1 bad signal, hold new bots, keep running ones
    BAD     (🔴) - 2+ bad signals, auto-pause all running bots
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────────────────

@dataclass
class RegimeThresholds:
    # BTC 1h crash threshold — negative %
    btc_1h_caution_pct: float = -2.0
    btc_1h_bad_pct: float = -3.0

    # BTC 24h extreme move (absolute %)
    btc_24h_caution_pct: float = 8.0
    btc_24h_bad_pct: float = 12.0

    # Volatility (ATR as % of price)
    volatility_caution_pct: float = 1.8
    volatility_bad_pct: float = 2.5

    # Trend strength (|EMA20 - EMA50| / price)
    trend_caution_pct: float = 3.0
    trend_bad_pct: float = 6.0

    # Portfolio drawdown (from peak)
    drawdown_caution_pct: float = 5.0
    drawdown_bad_pct: float = 10.0

    # Hysteresis: how long conditions must stay good before resuming
    resume_cooldown_minutes: int = 120

    # Check interval (seconds)
    check_interval_seconds: int = 300  # 5 minutes

    # Enable/disable automatic pause/resume
    auto_pause_enabled: bool = True
    auto_resume_enabled: bool = True


class Regime(str, Enum):
    GOOD = "good"
    CAUTION = "caution"
    BAD = "bad"
    UNKNOWN = "unknown"


@dataclass
class RegimeSignals:
    btc_1h_pct: float = 0.0
    btc_24h_pct: float = 0.0
    volatility_pct: float = 0.0
    trend_strength_pct: float = 0.0
    drawdown_pct: float = 0.0
    btc_price: float = 0.0


@dataclass
class RegimeReport:
    regime: Regime
    action: str  # "run" | "hold" | "pause"
    signals: RegimeSignals
    reasons: List[str]
    bad_count: int
    caution_count: int
    timestamp: str
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["regime"] = self.regime.value
        return d


# ─────────────────────────────────────────────────────────
#  Analysis helpers
# ─────────────────────────────────────────────────────────

def _ema(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
    if len(highs) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    return sum(trs[-period:]) / period


# ─────────────────────────────────────────────────────────
#  Regime Detector
# ─────────────────────────────────────────────────────────

class RegimeDetector:
    """Monitors market and produces regime reports on a schedule."""

    def __init__(
        self,
        db_path: str,
        thresholds: Optional[RegimeThresholds] = None,
        get_exchange: Optional[Callable[[], Any]] = None,
        bot_manager: Optional[Any] = None,
        alert_service: Optional[Any] = None,
    ) -> None:
        self.db_path = db_path
        self.thresholds = thresholds or RegimeThresholds()
        self._get_exchange = get_exchange
        self.bot_manager = bot_manager
        self.alert_service = alert_service

        self._last_report: Optional[RegimeReport] = None
        self._last_good_ts: Optional[float] = None  # when conditions were last GOOD
        self._paused_by_us: List[str] = []  # bot_ids we auto-paused
        self._task: Optional[asyncio.Task] = None
        self._running = False

        self._init_db()

    # -- DB ----------------------------------------------------------------

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS regime_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp  TEXT NOT NULL,
                regime     TEXT NOT NULL,
                action     TEXT NOT NULL,
                signals    TEXT,
                reasons    TEXT,
                summary    TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _persist(self, report: RegimeReport) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """
                INSERT INTO regime_history
                    (timestamp, regime, action, signals, reasons, summary)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    report.timestamp,
                    report.regime.value,
                    report.action,
                    json.dumps(asdict(report.signals)),
                    json.dumps(report.reasons),
                    report.summary,
                ),
            )
            conn.commit()
            conn.close()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to persist regime report")

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM regime_history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
            out = []
            for r in rows:
                d = dict(r)
                try:
                    d["signals"] = json.loads(d.get("signals") or "{}")
                    d["reasons"] = json.loads(d.get("reasons") or "[]")
                except Exception:  # noqa: BLE001
                    pass
                out.append(d)
            return out
        except Exception:  # noqa: BLE001
            logger.exception("Failed to load regime history")
            return []

    # -- Data fetching -----------------------------------------------------

    def _fetch_btc_candles(self, count: int = 100) -> List[Dict[str, float]]:
        """Fetch recent BTC/USDT 1h candles."""
        if self._get_exchange is None:
            return []
        try:
            ex = self._get_exchange()
            raw = ex.fetch_ohlcv("BTC/USDT", "1h", limit=count)
            return [
                {
                    "ts": int(r[0]),
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                    "volume": float(r[5]),
                }
                for r in raw
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch BTC candles: %s", exc)
            return []

    def _compute_drawdown(self) -> float:
        """Read portfolio snapshots and compute current drawdown from peak."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT total_value FROM portfolio_snapshots "
                "ORDER BY timestamp DESC LIMIT 288"  # ~24h of 5-min snapshots
            ).fetchall()
            conn.close()
            if not rows or len(rows) < 2:
                return 0.0
            vals = [r["total_value"] for r in rows if r["total_value"] is not None]
            if not vals:
                return 0.0
            peak = max(vals)
            current = vals[0]  # newest first
            if peak <= 0:
                return 0.0
            dd = (peak - current) / peak * 100
            return max(0.0, dd)
        except Exception:  # noqa: BLE001
            return 0.0

    # -- Analysis ----------------------------------------------------------

    def analyze(self) -> RegimeReport:
        """Run all checks and produce a regime report."""
        t = self.thresholds
        candles = self._fetch_btc_candles(100)

        if len(candles) < 50:
            # Not enough data → unknown regime, play it safe
            signals = RegimeSignals()
            return RegimeReport(
                regime=Regime.UNKNOWN,
                action="hold",
                signals=signals,
                reasons=["Not enough market data yet"],
                bad_count=0,
                caution_count=0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                summary="Waiting for market data",
            )

        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        current_price = closes[-1]

        # 1. BTC 1h change
        btc_1h_pct = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) >= 2 else 0.0

        # 2. BTC 24h change
        btc_24h_pct = (closes[-1] - closes[-25]) / closes[-25] * 100 if len(closes) >= 25 else 0.0

        # 3. Volatility (ATR as % of price)
        atr = _atr(highs, lows, closes, 14) or 0
        volatility_pct = (atr / current_price * 100) if current_price > 0 else 0.0

        # 4. Trend strength
        ema_20 = _ema(closes, 20) or current_price
        ema_50 = _ema(closes, 50) or current_price
        trend_strength_pct = abs(ema_20 - ema_50) / current_price * 100 if current_price > 0 else 0.0

        # 5. Portfolio drawdown
        drawdown_pct = self._compute_drawdown()

        signals = RegimeSignals(
            btc_1h_pct=round(btc_1h_pct, 2),
            btc_24h_pct=round(btc_24h_pct, 2),
            volatility_pct=round(volatility_pct, 2),
            trend_strength_pct=round(trend_strength_pct, 2),
            drawdown_pct=round(drawdown_pct, 2),
            btc_price=round(current_price, 2),
        )

        bad_count = 0
        caution_count = 0
        reasons: List[str] = []

        # BTC 1h crash (only negative counts — pumps are fine)
        if btc_1h_pct <= t.btc_1h_bad_pct:
            bad_count += 1
            reasons.append(f"🔴 BTC crashed {btc_1h_pct:.1f}% in 1h")
        elif btc_1h_pct <= t.btc_1h_caution_pct:
            caution_count += 1
            reasons.append(f"🟡 BTC down {btc_1h_pct:.1f}% in 1h")

        # BTC 24h extreme move (either direction)
        if abs(btc_24h_pct) >= t.btc_24h_bad_pct:
            bad_count += 1
            reasons.append(f"🔴 BTC moved {btc_24h_pct:+.1f}% in 24h (extreme)")
        elif abs(btc_24h_pct) >= t.btc_24h_caution_pct:
            caution_count += 1
            reasons.append(f"🟡 BTC moved {btc_24h_pct:+.1f}% in 24h")

        # Volatility
        if volatility_pct >= t.volatility_bad_pct:
            bad_count += 1
            reasons.append(f"🔴 Volatility high ({volatility_pct:.1f}% ATR)")
        elif volatility_pct >= t.volatility_caution_pct:
            caution_count += 1
            reasons.append(f"🟡 Volatility elevated ({volatility_pct:.1f}% ATR)")

        # Trend strength (grids lose in strong trends)
        if trend_strength_pct >= t.trend_bad_pct:
            bad_count += 1
            reasons.append(f"🔴 Strong trend detected ({trend_strength_pct:.1f}%)")
        elif trend_strength_pct >= t.trend_caution_pct:
            caution_count += 1
            reasons.append(f"🟡 Trend forming ({trend_strength_pct:.1f}%)")

        # Portfolio drawdown
        if drawdown_pct >= t.drawdown_bad_pct:
            bad_count += 1
            reasons.append(f"🔴 Portfolio drawdown {drawdown_pct:.1f}%")
        elif drawdown_pct >= t.drawdown_caution_pct:
            caution_count += 1
            reasons.append(f"🟡 Portfolio drawdown {drawdown_pct:.1f}%")

        # Decide regime
        if bad_count >= 2:
            regime = Regime.BAD
            action = "pause"
            summary = f"BAD — {bad_count} critical signals, auto-pausing bots"
        elif bad_count == 1 or caution_count >= 2:
            regime = Regime.CAUTION
            action = "hold"
            summary = f"CAUTION — keeping bots running, not starting new ones"
        else:
            regime = Regime.GOOD
            action = "run"
            if reasons:
                summary = f"GOOD — minor signals: {len(reasons)}"
            else:
                summary = "GOOD — market conditions normal"

        if not reasons:
            reasons.append("All signals within normal ranges")

        return RegimeReport(
            regime=regime,
            action=action,
            signals=signals,
            reasons=reasons,
            bad_count=bad_count,
            caution_count=caution_count,
            timestamp=datetime.now(timezone.utc).isoformat(),
            summary=summary,
        )

    # -- Auto pause / resume ----------------------------------------------

    def _apply_action(self, report: RegimeReport, previous: Optional[RegimeReport]) -> None:
        """Pause or resume bots based on regime change."""
        if self.bot_manager is None:
            return

        t = self.thresholds
        now = time.time()

        # Track when we were last GOOD for hysteresis
        if report.regime == Regime.GOOD:
            self._last_good_ts = now

        # Auto-pause when entering BAD
        if report.regime == Regime.BAD and t.auto_pause_enabled:
            if previous is None or previous.regime != Regime.BAD:
                self._auto_pause(report)

        # Auto-resume when conditions have been GOOD for cooldown duration
        elif report.regime == Regime.GOOD and t.auto_resume_enabled and self._paused_by_us:
            if self._last_good_ts and (now - self._last_good_ts) >= (t.resume_cooldown_minutes * 60 - 1):
                self._auto_resume(report)

    def _auto_pause(self, report: RegimeReport) -> None:
        """Stop all running bots and remember which ones we stopped."""
        try:
            statuses = self.bot_manager.get_all_statuses()
            if isinstance(statuses, dict):
                items = list(statuses.items())
            elif isinstance(statuses, list):
                items = [(s.get("id"), s) for s in statuses if s.get("id")]
            else:
                items = []

            paused = []
            for bot_id, st in items:
                if (st or {}).get("status") == "running":
                    try:
                        self.bot_manager.stop_bot(bot_id)
                        paused.append(bot_id)
                    except Exception:  # noqa: BLE001
                        logger.exception("Failed to pause %s", bot_id)

            self._paused_by_us = paused
            logger.warning("Auto-paused %d bot(s) due to BAD regime", len(paused))

            if self.alert_service and paused:
                try:
                    self.alert_service.send_telegram(
                        "🔴 <b>Market Regime: BAD</b>\n"
                        f"Auto-paused <b>{len(paused)}</b> bot(s)\n\n"
                        "<b>Reasons:</b>\n" + "\n".join(f"• {r}" for r in report.reasons[:5]) +
                        f"\n\n<i>Will auto-resume after {self.thresholds.resume_cooldown_minutes}min of GOOD conditions.</i>"
                    )
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            logger.exception("auto_pause failed")

    def _auto_resume(self, report: RegimeReport) -> None:
        """Restart bots we previously auto-paused."""
        try:
            resumed = []
            for bot_id in self._paused_by_us:
                try:
                    self.bot_manager.start_bot(bot_id)
                    resumed.append(bot_id)
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to resume %s", bot_id)

            self._paused_by_us = []
            logger.info("Auto-resumed %d bot(s)", len(resumed))

            if self.alert_service and resumed:
                try:
                    self.alert_service.send_telegram(
                        "🟢 <b>Market Regime: GOOD</b>\n"
                        f"Conditions normalized. Auto-resumed <b>{len(resumed)}</b> bot(s).\n\n"
                        f"BTC: ${report.signals.btc_price:,.0f} ({report.signals.btc_24h_pct:+.1f}% 24h)"
                    )
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            logger.exception("auto_resume failed")

    # -- Main loop ---------------------------------------------------------

    async def run(self) -> None:
        """Background loop: analyse market every N seconds."""
        self._running = True
        logger.info(
            "RegimeDetector started (check every %ds)",
            self.thresholds.check_interval_seconds,
        )

        # Initial analysis on startup
        await asyncio.sleep(5)

        while self._running:
            try:
                report = self.analyze()
                previous = self._last_report
                self._last_report = report

                # Persist if regime changed or every 10 checks
                if previous is None or previous.regime != report.regime:
                    self._persist(report)
                    if self.alert_service and report.regime != Regime.UNKNOWN:
                        try:
                            emoji = {"good": "🟢", "caution": "🟡", "bad": "🔴"}.get(
                                report.regime.value, "⚪"
                            )
                            self.alert_service.send_telegram(
                                f"{emoji} <b>Market Regime: {report.regime.value.upper()}</b>\n"
                                f"{report.summary}\n\n"
                                "<b>Signals:</b>\n" +
                                "\n".join(f"• {r}" for r in report.reasons[:5])
                            )
                        except Exception:  # noqa: BLE001
                            pass

                # Apply auto-pause/resume logic
                self._apply_action(report, previous)

            except Exception:  # noqa: BLE001
                logger.exception("Regime analysis failed")

            await asyncio.sleep(self.thresholds.check_interval_seconds)

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    @property
    def last_report(self) -> Optional[RegimeReport]:
        return self._last_report


# ─────────────────────────────────────────────────────────
#  Convenience for main.py
# ─────────────────────────────────────────────────────────

_singleton: Optional[RegimeDetector] = None


def build_regime_detector(bot_manager, alert_service) -> RegimeDetector:
    """Factory used by main.py lifespan."""
    global _singleton

    def _get_ex():
        from routers.market import _get_exchange
        return _get_exchange()

    db_path = os.environ.get("DATABASE_PATH", "/app/data/trading.db")
    t = RegimeThresholds(
        auto_pause_enabled=os.environ.get("REGIME_AUTO_PAUSE", "true").lower() == "true",
        auto_resume_enabled=os.environ.get("REGIME_AUTO_RESUME", "true").lower() == "true",
        check_interval_seconds=int(os.environ.get("REGIME_CHECK_SECONDS", "300")),
    )
    _singleton = RegimeDetector(
        db_path=db_path,
        thresholds=t,
        get_exchange=_get_ex,
        bot_manager=bot_manager,
        alert_service=alert_service,
    )
    return _singleton


def get_regime_detector() -> Optional[RegimeDetector]:
    return _singleton
