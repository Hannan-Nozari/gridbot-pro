from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    token: str


# ---------------------------------------------------------------------------
# Bots
# ---------------------------------------------------------------------------

class BotCreate(BaseModel):
    type: str = Field(..., description="Bot strategy type, e.g. 'grid'")
    name: str = Field(..., min_length=1, max_length=120)
    config: Dict[str, Any] = Field(default_factory=dict)
    paper: bool = True


class BotResponse(BaseModel):
    id: str
    name: str
    type: str
    status: str
    paper: bool
    config: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    pnl: float = 0.0
    total_value: float = 0.0


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

class TradeResponse(BaseModel):
    id: int
    bot_id: str
    symbol: str
    side: str
    price: float
    amount: float
    fee: float = 0.0
    profit: Optional[float] = None
    timestamp: str


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    strategy: str
    symbol: str
    days: int = Field(30, ge=1, le=3650)
    params: Dict[str, Any] = Field(default_factory=dict)


class BacktestResponse(BaseModel):
    id: str
    strategy: str
    symbol: str
    pnl: float = 0.0
    pnl_pct: float = 0.0
    monthly_roi: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    num_trades: int = 0
    total_fees: float = 0.0
    equity_curve: List[float] = Field(default_factory=list)
    trades: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class EmailSettings(BaseModel):
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    from_addr: str = ""
    to_addr: str = ""


class TelegramSettings(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


class AlertTrigger(BaseModel):
    on_trade: bool = True
    on_error: bool = True
    on_stop: bool = True
    daily_summary: bool = False
    pnl_threshold: Optional[float] = None


class AlertConfig(BaseModel):
    email: EmailSettings = Field(default_factory=EmailSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    triggers: AlertTrigger = Field(default_factory=AlertTrigger)


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

class PortfolioSummary(BaseModel):
    total_value: float = 0.0
    total_pnl: float = 0.0
    pnl_pct: float = 0.0
    num_bots: int = 0
    num_trades: int = 0
