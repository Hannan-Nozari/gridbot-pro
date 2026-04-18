"""Main FastAPI application for GridBot Pro backend."""

import asyncio
import json
import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from auth import router as auth_router
from config import settings
from database import init_db

# Routers — wrapped in try to prevent startup failure on import errors
_router_errors: List[str] = []

try:
    from routers.bots import router as bots_router
except Exception as exc:  # noqa: BLE001
    bots_router = None
    _router_errors.append(f"bots: {exc}")

try:
    from routers.trades import router as trades_router
except Exception as exc:  # noqa: BLE001
    trades_router = None
    _router_errors.append(f"trades: {exc}")

try:
    from routers.backtest import router as backtest_router
except Exception as exc:  # noqa: BLE001
    backtest_router = None
    _router_errors.append(f"backtest: {exc}")

try:
    from routers.portfolio import router as portfolio_router
except Exception as exc:  # noqa: BLE001
    portfolio_router = None
    _router_errors.append(f"portfolio: {exc}")

try:
    from routers.alerts import router as alerts_router
except Exception as exc:  # noqa: BLE001
    alerts_router = None
    _router_errors.append(f"alerts: {exc}")

try:
    from routers.ai import router as ai_router
except Exception as exc:  # noqa: BLE001
    ai_router = None
    _router_errors.append(f"ai: {exc}")

try:
    from routers.market import router as market_router
except Exception as exc:  # noqa: BLE001
    market_router = None
    _router_errors.append(f"market: {exc}")

try:
    from routers.regime import router as regime_router
except Exception as exc:  # noqa: BLE001
    regime_router = None
    _router_errors.append(f"regime: {exc}")

try:
    from services.regime_detector import build_regime_detector
except Exception as exc:  # noqa: BLE001
    build_regime_detector = None
    _router_errors.append(f"regime_detector: {exc}")

try:
    from services.bot_manager import BotManager as FullBotManager
except Exception as exc:  # noqa: BLE001
    FullBotManager = None
    _router_errors.append(f"bot_manager: {exc}")

try:
    from services.alert_service import AlertService
except Exception as exc:  # noqa: BLE001
    AlertService = None
    _router_errors.append(f"alert_service: {exc}")


logger = logging.getLogger("uvicorn.error")


# ---------------------------------------------------------------------------
# Fallback minimal bot manager (used if the full one fails to import)
# ---------------------------------------------------------------------------

class _MinimalBotManager:
    """Keeps websocket clients and stubs for the full bot manager API."""

    def __init__(self) -> None:
        self._tasks: Dict[str, asyncio.Task] = {}
        self._ws_clients: Set[WebSocket] = set()

    def create_bot(self, bot_id, bot_type, config, paper=True):
        raise RuntimeError("Full bot manager failed to load — cannot create bots")

    def start_bot(self, bot_id):
        raise RuntimeError("Full bot manager failed to load — cannot start bots")

    def stop_bot(self, bot_id):
        # Allow stopping even in fallback mode (kill switch safety)
        task = self._tasks.pop(bot_id, None)
        if task and not task.done():
            task.cancel()

    def remove_bot(self, bot_id):
        self.stop_bot(bot_id)

    def get_status(self, bot_id):
        return {"status": "unknown"}

    def get_all_statuses(self):
        return {}

    async def stop_all(self) -> None:
        for bot_id in list(self._tasks):
            self.stop_bot(bot_id)

    # -- websocket -----------------------------------------------------------

    def add_ws(self, ws: WebSocket) -> None:
        self._ws_clients.add(ws)

    def remove_ws(self, ws: WebSocket) -> None:
        self._ws_clients.discard(ws)

    async def broadcast(self, event: str, data: dict) -> None:
        message = json.dumps({"event": event, "data": data})
        closed: List[WebSocket] = []
        for ws in self._ws_clients:
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001
                closed.append(ws)
        for ws in closed:
            self._ws_clients.discard(ws)


# ---------------------------------------------------------------------------
# App state bootstrap
# ---------------------------------------------------------------------------

def _build_bot_manager():
    """Prefer the full BotManager, fall back to minimal one."""
    if FullBotManager is None:
        logger.warning("Using minimal BotManager (imports failed): %s", _router_errors)
        return _MinimalBotManager()
    try:
        db_path = os.environ.get("DATABASE_PATH", "/app/data/trading.db")
        return FullBotManager(db_path=db_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to instantiate full BotManager: %s", exc)
        return _MinimalBotManager()


def _build_alert_service():
    """Instantiate AlertService from env vars."""
    if AlertService is None:
        return None
    try:
        return AlertService(
            db_path=os.environ.get("DATABASE_PATH", "/app/data/trading.db"),
            smtp_host=os.environ.get("ALERT_EMAIL_SMTP_HOST", ""),
            smtp_port=int(os.environ.get("ALERT_EMAIL_SMTP_PORT", "587")),
            smtp_user=os.environ.get("ALERT_EMAIL_USERNAME", ""),
            smtp_password=os.environ.get("ALERT_EMAIL_PASSWORD", ""),
            email_from=os.environ.get("ALERT_EMAIL_FROM", ""),
            telegram_bot_token=os.environ.get("ALERT_TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.environ.get("ALERT_TELEGRAM_CHAT_ID", ""),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to build AlertService: %s", exc)
        return None


bot_manager = _build_bot_manager()
alert_service = _build_alert_service()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    init_db()
    logger.info("Database initialized")

    if _router_errors:
        logger.warning("Some routers failed to load: %s", _router_errors)

    _app.state.bot_manager = bot_manager
    _app.state.alert_service = alert_service
    _app.state.started_at = datetime.now(timezone.utc).isoformat()

    # Send startup alert if Telegram is configured
    if alert_service and alert_service.telegram_bot_token and alert_service.telegram_chat_id:
        try:
            alert_service.send_telegram(
                "🟢 <b>GridBot Pro started</b>\n"
                f"Server time: {_app.state.started_at}"
            )
        except Exception:  # noqa: BLE001
            pass

    # Launch the Market Regime Detector in the background
    regime_task = None
    if build_regime_detector is not None:
        try:
            det = build_regime_detector(bot_manager, alert_service)
            _app.state.regime_detector = det
            regime_task = asyncio.create_task(det.run())
            logger.info("Regime detector background task started")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to start regime detector")
    else:
        _app.state.regime_detector = None

    yield

    # Shutdown
    try:
        if regime_task and not regime_task.done():
            regime_task.cancel()
    except Exception:  # noqa: BLE001
        pass

    try:
        if hasattr(bot_manager, "stop_all"):
            result = bot_manager.stop_all()
            if asyncio.iscoroutine(result):
                await result
    except Exception:  # noqa: BLE001
        logger.exception("Error during bot_manager.stop_all()")

    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="GridBot Pro",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router, prefix="/api/v1")
if bots_router is not None:
    app.include_router(bots_router, prefix="/api/v1")
if trades_router is not None:
    app.include_router(trades_router, prefix="/api/v1")
if backtest_router is not None:
    app.include_router(backtest_router, prefix="/api/v1")
if portfolio_router is not None:
    app.include_router(portfolio_router, prefix="/api/v1")
if alerts_router is not None:
    app.include_router(alerts_router, prefix="/api/v1")
if ai_router is not None:
    app.include_router(ai_router, prefix="/api/v1")
if market_router is not None:
    app.include_router(market_router, prefix="/api/v1")
if regime_router is not None:
    app.include_router(regime_router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    bot_manager.add_ws(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        bot_manager.remove_ws(ws)


# ---------------------------------------------------------------------------
# Health & system endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/health")
def health() -> Dict[str, str]:
    """Basic liveness check."""
    return {"status": "ok"}


@app.get("/api/v1/system/status")
def system_status() -> Dict[str, object]:
    """Detailed system health check — DB, bot manager, alerts, uptime."""
    result: Dict[str, object] = {
        "status": "ok",
        "checks": {},
        "started_at": getattr(app.state, "started_at", None),
        "router_errors": _router_errors,
    }

    # Database check
    try:
        db_path = os.environ.get("DATABASE_PATH", "/app/data/trading.db")
        conn = sqlite3.connect(db_path, timeout=2)
        cur = conn.execute("SELECT COUNT(*) FROM bots")
        bot_count = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(*) FROM trades")
        trade_count = cur.fetchone()[0]
        conn.close()
        db_size_kb = Path(db_path).stat().st_size // 1024 if Path(db_path).exists() else 0
        result["checks"]["database"] = {
            "status": "ok",
            "bot_count": bot_count,
            "trade_count": trade_count,
            "size_kb": db_size_kb,
        }
    except Exception as exc:  # noqa: BLE001
        result["status"] = "degraded"
        result["checks"]["database"] = {"status": "error", "error": str(exc)}

    # Bot manager check
    try:
        statuses = bot_manager.get_all_statuses() if hasattr(bot_manager, "get_all_statuses") else {}
        # Normalize to list of dicts regardless of the backing representation
        if isinstance(statuses, dict):
            status_iter = list(statuses.values())
        elif isinstance(statuses, list):
            status_iter = statuses
        else:
            status_iter = []
        running = sum(1 for v in status_iter if (v or {}).get("status") == "running")
        result["checks"]["bot_manager"] = {
            "status": "ok",
            "total": len(status_iter),
            "running": running,
            "mode": "full" if FullBotManager is not None and not isinstance(bot_manager, _MinimalBotManager) else "minimal",
        }
    except Exception as exc:  # noqa: BLE001
        result["status"] = "degraded"
        result["checks"]["bot_manager"] = {"status": "error", "error": str(exc)}

    # Alert service check
    result["checks"]["alerts"] = {
        "status": "ok" if alert_service is not None else "disabled",
        "email_configured": bool(alert_service and alert_service.smtp_host),
        "telegram_configured": bool(
            alert_service and alert_service.telegram_bot_token and alert_service.telegram_chat_id
        ),
    }

    # WebSocket count
    result["checks"]["websocket"] = {
        "connected_clients": len(getattr(bot_manager, "_ws_clients", set())),
    }

    return result
