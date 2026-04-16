from routers.alerts import router as alerts_router
from routers.backtest import router as backtest_router
from routers.bots import router as bots_router
from routers.portfolio import router as portfolio_router
from routers.trades import router as trades_router

__all__ = [
    "alerts_router",
    "backtest_router",
    "bots_router",
    "portfolio_router",
    "trades_router",
]
