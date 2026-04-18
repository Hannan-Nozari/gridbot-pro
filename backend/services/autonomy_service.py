"""
Autonomy Service
================
True set-and-forget automation on top of running bots.

Three independent loops run in the background:

1. **Auto-Rebalancer** (every 4h):
   Re-centers the grid range of each grid-type bot when the current
   market price has drifted more than REBALANCE_DRIFT_PCT% from the
   centre of the bot's configured grid.

2. **Weekly AI Re-evaluator** (every Sunday):
   For each running bot, re-runs the AI analysis on the latest market
   data. If a significantly better (>50% higher score) strategy/pair
   combination is found, sends a Telegram alert so the user can
   approve the switch. Does NOT auto-switch without confirmation.

3. **Daily Digest** (once every 24h):
   Sends a Telegram summary of portfolio value, 24h P&L, trade count,
   and current market regime.

Every loop is tolerant of failures — one loop crashing never kills the
others, and the whole service is designed to be completely silent in
the happy path.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────────────────

@dataclass
class AutonomyConfig:
    # Auto-rebalancer
    rebalance_enabled: bool = True
    rebalance_drift_pct: float = 15.0         # re-center if price drifts >15% from grid centre
    rebalance_check_seconds: int = 14_400     # every 4 hours
    rebalance_notify_only: bool = False       # if True, alert instead of acting

    # Weekly re-evaluator
    weekly_reeval_enabled: bool = True
    weekly_reeval_day: int = 6                # Sunday (0=Mon, 6=Sun)
    weekly_reeval_hour_utc: int = 6           # 06:00 UTC
    weekly_reeval_min_score_gain_pct: float = 50.0  # alert if alternative is >50% better score

    # Daily digest
    digest_enabled: bool = True
    digest_hour_utc: int = 8                  # 08:00 UTC every day
    digest_min_interval_seconds: int = 82_800  # ~23h (avoid double-send around DST)


# ─────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _load_state(db_path: str) -> Dict[str, Any]:
    """Load autonomy state (last-run timestamps) from the alert_config table."""
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS autonomy_state (key TEXT PRIMARY KEY, value TEXT)"
        )
        rows = conn.execute("SELECT key, value FROM autonomy_state").fetchall()
        conn.close()
        return {k: json.loads(v) if v else None for k, v in rows}
    except Exception:  # noqa: BLE001
        return {}


def _save_state(db_path: str, key: str, value: Any) -> None:
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS autonomy_state (key TEXT PRIMARY KEY, value TEXT)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO autonomy_state (key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )
        conn.commit()
        conn.close()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to save autonomy state '%s'", key)


def _get_running_bots(db_path: str) -> List[Dict[str, Any]]:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, name, type, config, paper, status FROM bots WHERE status = 'running'"
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["config"] = json.loads(d["config"]) if d.get("config") else {}
            except Exception:  # noqa: BLE001
                d["config"] = {}
            result.append(d)
        return result
    except Exception:  # noqa: BLE001
        logger.exception("Failed to load running bots")
        return []


def _get_bot_pnl_and_trades(db_path: str, bot_id: str, hours: int = 24) -> Dict[str, Any]:
    """Return {pnl, trade_count} for a bot over the last N hours."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        since = (_now_utc() - timedelta(hours=hours)).isoformat()
        row = conn.execute(
            """
            SELECT COALESCE(SUM(profit), 0) as pnl, COUNT(*) as trades
            FROM trades WHERE bot_id = ? AND timestamp >= ?
            """,
            (bot_id, since),
        ).fetchone()
        conn.close()
        return dict(row) if row else {"pnl": 0.0, "trades": 0}
    except Exception:  # noqa: BLE001
        return {"pnl": 0.0, "trades": 0}


def _portfolio_summary(db_path: str) -> Dict[str, Any]:
    """Quick summary across all running bots in the last 24h."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        since = (_now_utc() - timedelta(hours=24)).isoformat()
        total_pnl_row = conn.execute(
            "SELECT COALESCE(SUM(profit), 0) as pnl, COUNT(*) as trades FROM trades WHERE timestamp >= ?",
            (since,),
        ).fetchone()
        bot_count = conn.execute(
            "SELECT COUNT(*) as n FROM bots WHERE status='running'"
        ).fetchone()["n"]
        conn.close()
        return {
            "pnl_24h": total_pnl_row["pnl"] if total_pnl_row else 0,
            "trades_24h": total_pnl_row["trades"] if total_pnl_row else 0,
            "running_bots": bot_count,
        }
    except Exception:  # noqa: BLE001
        return {"pnl_24h": 0, "trades_24h": 0, "running_bots": 0}


def _fetch_current_price(symbol: str, get_exchange: Callable) -> Optional[float]:
    try:
        ex = get_exchange()
        t = ex.fetch_ticker(symbol)
        return float(t.get("last") or 0)
    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────
#  Autonomy Service
# ─────────────────────────────────────────────────────────

class AutonomyService:
    """Runs the three autonomy loops on a shared asyncio task."""

    def __init__(
        self,
        db_path: str,
        bot_manager,
        alert_service=None,
        get_exchange: Optional[Callable] = None,
        config: Optional[AutonomyConfig] = None,
    ) -> None:
        self.db_path = db_path
        self.bot_manager = bot_manager
        self.alert_service = alert_service
        self.get_exchange = get_exchange
        self.config = config or AutonomyConfig()
        self._running = False
        self._last_rebalance_check: float = 0
        self._last_reeval_check: float = 0
        self._last_digest_sent: float = 0
        self._rebalance_actions: List[Dict[str, Any]] = []

        # Load last-run timestamps from persistent storage
        state = _load_state(db_path)
        self._last_rebalance_check = float(state.get("last_rebalance", 0) or 0)
        self._last_reeval_check = float(state.get("last_reeval", 0) or 0)
        self._last_digest_sent = float(state.get("last_digest", 0) or 0)

    # -- Logging + telegram --------------------------------------------------

    def _notify(self, message: str) -> None:
        if self.alert_service is None:
            return
        try:
            self.alert_service.send_telegram(message)
        except Exception:  # noqa: BLE001
            logger.exception("Telegram notify failed")

    # -- Loop 1: Auto-Rebalance ---------------------------------------------

    def _check_rebalance(self) -> None:
        if not self.config.rebalance_enabled:
            return

        now_ts = time.time()
        if (now_ts - self._last_rebalance_check) < self.config.rebalance_check_seconds:
            return

        self._last_rebalance_check = now_ts
        _save_state(self.db_path, "last_rebalance", now_ts)

        logger.info("Autonomy: running rebalance check")

        bots = _get_running_bots(self.db_path)
        for bot in bots:
            if bot["type"] != "grid":  # only grids have explicit ranges
                continue
            cfg = bot.get("config", {})
            lower = cfg.get("lower_price") or cfg.get("lower")
            upper = cfg.get("upper_price") or cfg.get("upper")
            symbol = cfg.get("symbol") or cfg.get("pair")
            if not (lower and upper and symbol and self.get_exchange):
                continue

            price = _fetch_current_price(symbol, self.get_exchange)
            if price is None or price <= 0:
                continue

            centre = (lower + upper) / 2
            drift_pct = abs(price - centre) / centre * 100
            threshold = self.config.rebalance_drift_pct

            if drift_pct < threshold:
                continue

            direction = "up" if price > centre else "down"
            logger.info(
                "Bot %s drifted %.1f%% %s (price %s, centre %s)",
                bot["name"], drift_pct, direction, price, centre,
            )

            action = {
                "bot_id": bot["id"],
                "bot_name": bot["name"],
                "symbol": symbol,
                "old_lower": lower,
                "old_upper": upper,
                "old_centre": centre,
                "current_price": price,
                "drift_pct": drift_pct,
                "timestamp": _now_utc().isoformat(),
            }

            if self.config.rebalance_notify_only:
                # Alert only
                self._notify(
                    f"⚠️ <b>Grid drift detected</b>\n"
                    f"Bot: {bot['name']}\n"
                    f"Symbol: {symbol}\n"
                    f"Grid centre: ${centre:,.2f}\n"
                    f"Current price: ${price:,.2f} ({direction} {drift_pct:.1f}%)\n\n"
                    f"<i>Auto-rebalance is set to notify-only mode.</i>"
                )
                action["applied"] = False
            else:
                # Actually rebalance — stop the bot, replace config, start again
                try:
                    range_pct = (upper - lower) / 2 / centre
                    new_lower = round(price * (1 - range_pct), 4)
                    new_upper = round(price * (1 + range_pct), 4)

                    # Stop bot
                    try:
                        self.bot_manager.stop_bot(bot["id"])
                    except Exception:  # noqa: BLE001
                        pass

                    # Update config in DB
                    new_config = {**cfg, "lower_price": new_lower, "upper_price": new_upper}
                    try:
                        conn = sqlite3.connect(self.db_path)
                        conn.execute(
                            "UPDATE bots SET config = ? WHERE id = ?",
                            (json.dumps(new_config), bot["id"]),
                        )
                        conn.commit()
                        conn.close()
                    except Exception:  # noqa: BLE001
                        pass

                    # Re-register + restart
                    try:
                        self.bot_manager.remove_bot(bot["id"])
                    except Exception:  # noqa: BLE001
                        pass
                    try:
                        self.bot_manager.create_bot(
                            bot["id"], bot["type"], new_config, paper=bool(bot.get("paper", True))
                        )
                        self.bot_manager.start_bot(bot["id"])
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Failed to restart bot after rebalance: %s", exc)

                    action.update({
                        "new_lower": new_lower,
                        "new_upper": new_upper,
                        "applied": True,
                    })

                    self._notify(
                        f"♻️ <b>Grid auto-rebalanced</b>\n"
                        f"Bot: {bot['name']}\n"
                        f"Symbol: {symbol}\n"
                        f"Old range: ${lower:,.2f}–${upper:,.2f}\n"
                        f"New range: ${new_lower:,.2f}–${new_upper:,.2f}\n"
                        f"Current price: ${price:,.2f}\n\n"
                        f"<i>Drifted {drift_pct:.1f}% from old centre, now re-centered.</i>"
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("Rebalance failed for %s", bot["id"])
                    action["applied"] = False

            self._rebalance_actions.append(action)

    # -- Loop 2: Weekly Re-evaluation ---------------------------------------

    def _check_weekly_reeval(self) -> None:
        if not self.config.weekly_reeval_enabled:
            return

        now_ts = time.time()
        now = _now_utc()

        # Only run at the configured day/hour
        if now.weekday() != self.config.weekly_reeval_day:
            return
        if now.hour != self.config.weekly_reeval_hour_utc:
            return
        # Avoid repeated runs within the same hour
        if (now_ts - self._last_reeval_check) < 3500:
            return

        self._last_reeval_check = now_ts
        _save_state(self.db_path, "last_reeval", now_ts)

        logger.info("Autonomy: running weekly AI re-evaluation")

        try:
            from routers.ai import analyze, AnalyzeRequest
            import asyncio as _asyncio

            bots = _get_running_bots(self.db_path)
            if not bots:
                return

            # Get unique investments to analyse
            for bot in bots:
                cfg = bot.get("config", {})
                investment = float(cfg.get("total_investment") or cfg.get("investment") or 1000)

                # Build fake request object to match the FastAPI handler
                class _FakeReq:
                    class _State:
                        bot_manager = self.bot_manager
                        alert_service = self.alert_service
                    app = type("App", (), {"state": _State})()

                try:
                    # analyze() is an async function
                    loop = _asyncio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures
                        import threading
                        # Schedule in a new loop in a thread to avoid "already running"
                        result_holder: Dict[str, Any] = {}
                        def _runner():
                            new_loop = _asyncio.new_event_loop()
                            _asyncio.set_event_loop(new_loop)
                            try:
                                res = new_loop.run_until_complete(
                                    analyze(AnalyzeRequest(investment=investment), _FakeReq())
                                )
                                result_holder["result"] = res
                            finally:
                                new_loop.close()
                        t = threading.Thread(target=_runner, daemon=True)
                        t.start()
                        t.join(timeout=180)
                        ai_result = result_holder.get("result")
                    else:
                        ai_result = loop.run_until_complete(
                            analyze(AnalyzeRequest(investment=investment), _FakeReq())
                        )
                except Exception:  # noqa: BLE001
                    logger.exception("Weekly reeval analyze failed for %s", bot["id"])
                    continue

                if ai_result is None:
                    continue

                rec = ai_result.recommendation
                current_strategy = bot.get("type", "grid")
                current_symbol = cfg.get("symbol") or "?"

                # Compare: recommended vs current
                is_different = (rec.pair != current_symbol) or (rec.strategy != current_strategy)
                if not is_different:
                    continue

                # Find score of current combo in the results
                current_score = None
                for r in (ai_result.results_90d or []):
                    if r.pair == current_symbol and r.strategy == current_strategy:
                        current_score = r.score
                        break

                if current_score is None or current_score <= 0:
                    current_score = 0.01

                gain_pct = (rec.score - current_score) / abs(current_score) * 100

                if gain_pct >= self.config.weekly_reeval_min_score_gain_pct:
                    self._notify(
                        f"💡 <b>Better strategy found</b>\n"
                        f"Current: {current_strategy} on {current_symbol}\n"
                        f"Suggested: {rec.strategy} on {rec.pair}\n"
                        f"Score gain: +{gain_pct:.0f}%\n"
                        f"Expected: +{rec.monthly_roi:.2f}%/mo\n\n"
                        f"<i>Visit https://tradinix.com/autopilot to switch.</i>"
                    )
        except Exception:  # noqa: BLE001
            logger.exception("Weekly re-evaluation failed")

    # -- Loop 3: Daily Digest -----------------------------------------------

    def _check_daily_digest(self) -> None:
        if not self.config.digest_enabled:
            return

        now_ts = time.time()
        now = _now_utc()

        if now.hour != self.config.digest_hour_utc:
            return
        if (now_ts - self._last_digest_sent) < self.config.digest_min_interval_seconds:
            return

        self._last_digest_sent = now_ts
        _save_state(self.db_path, "last_digest", now_ts)

        logger.info("Autonomy: sending daily digest")

        try:
            summary = _portfolio_summary(self.db_path)
            pnl = summary["pnl_24h"]
            trades = summary["trades_24h"]
            bots = summary["running_bots"]

            # Regime snapshot
            regime_line = ""
            try:
                from services.regime_detector import get_regime_detector
                det = get_regime_detector()
                if det and det.last_report:
                    r = det.last_report
                    emoji = {"good": "🟢", "caution": "🟡", "bad": "🔴"}.get(r.regime.value, "⚪")
                    regime_line = f"{emoji} Market: <b>{r.regime.value.upper()}</b>\n"
            except Exception:  # noqa: BLE001
                pass

            pnl_sign = "+" if pnl >= 0 else ""
            pnl_emoji = "📈" if pnl >= 0 else "📉"

            msg = (
                "🌅 <b>Daily Digest</b>\n"
                f"{regime_line}\n"
                f"<b>Last 24 hours:</b>\n"
                f"{pnl_emoji} P&amp;L: <b>{pnl_sign}${abs(pnl):,.2f}</b>\n"
                f"🔄 Trades: <b>{trades}</b>\n"
                f"🤖 Running bots: <b>{bots}</b>\n\n"
                f"<i>{now.strftime('%Y-%m-%d %H:%M UTC')}</i>\n"
                f"<i>Full dashboard: https://tradinix.com</i>"
            )
            self._notify(msg)
        except Exception:  # noqa: BLE001
            logger.exception("Daily digest failed")

    # -- Main loop ---------------------------------------------------------

    async def run(self) -> None:
        self._running = True
        logger.info("Autonomy service started")
        # Small delay on boot to let the rest of the app come up
        await asyncio.sleep(10)

        while self._running:
            try:
                self._check_rebalance()
                self._check_weekly_reeval()
                self._check_daily_digest()
            except Exception:  # noqa: BLE001
                logger.exception("Autonomy loop iteration failed")

            # Check every 5 minutes — actual actions are rate-limited above
            await asyncio.sleep(300)

    def stop(self) -> None:
        self._running = False


# ─────────────────────────────────────────────────────────
#  Factory
# ─────────────────────────────────────────────────────────

_singleton: Optional[AutonomyService] = None


def build_autonomy_service(bot_manager, alert_service) -> AutonomyService:
    global _singleton

    def _get_ex():
        from routers.market import _get_exchange
        return _get_exchange()

    config = AutonomyConfig(
        rebalance_enabled=os.environ.get("AUTONOMY_REBALANCE", "true").lower() == "true",
        rebalance_drift_pct=float(os.environ.get("AUTONOMY_DRIFT_PCT", "15")),
        rebalance_notify_only=os.environ.get("AUTONOMY_NOTIFY_ONLY", "false").lower() == "true",
        weekly_reeval_enabled=os.environ.get("AUTONOMY_WEEKLY_AI", "true").lower() == "true",
        digest_enabled=os.environ.get("AUTONOMY_DIGEST", "true").lower() == "true",
    )

    db_path = os.environ.get("DATABASE_PATH", "/app/data/trading.db")
    _singleton = AutonomyService(
        db_path=db_path,
        bot_manager=bot_manager,
        alert_service=alert_service,
        get_exchange=_get_ex,
        config=config,
    )
    return _singleton


def get_autonomy_service() -> Optional[AutonomyService]:
    return _singleton
