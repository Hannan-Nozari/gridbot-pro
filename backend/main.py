import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, List, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from auth import router as auth_router
from config import settings
from database import init_db

logger = logging.getLogger("uvicorn.error")


# ---------------------------------------------------------------------------
# Bot manager (thin wrapper kept on app.state)
# ---------------------------------------------------------------------------

class BotManager:
    """Tracks running bot tasks so they can be stopped on shutdown."""

    def __init__(self) -> None:
        self._tasks: Dict[str, asyncio.Task] = {}  # bot_id -> task
        self._ws_clients: Set[WebSocket] = set()

    # -- bot lifecycle -------------------------------------------------------

    def register_task(self, bot_id: str, task: asyncio.Task) -> None:
        self._tasks[bot_id] = task

    def cancel_task(self, bot_id: str) -> None:
        task = self._tasks.pop(bot_id, None)
        if task and not task.done():
            task.cancel()

    def is_running(self, bot_id: str) -> bool:
        task = self._tasks.get(bot_id)
        return task is not None and not task.done()

    async def stop_all(self) -> None:
        for bot_id in list(self._tasks):
            self.cancel_task(bot_id)
        logger.info("All bot tasks cancelled")

    # -- websocket broadcast -------------------------------------------------

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
            except Exception:
                closed.append(ws)
        for ws in closed:
            self._ws_clients.discard(ws)


bot_manager = BotManager()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    init_db()
    logger.info("Database initialized")
    _app.state.bot_manager = bot_manager
    yield
    # Shutdown
    await bot_manager.stop_all()
    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Crypto Grid Bot",
    version="1.0.0",
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


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    bot_manager.add_ws(ws)
    try:
        while True:
            # Keep connection alive; ignore incoming messages.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        bot_manager.remove_ws(ws)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/v1/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}
