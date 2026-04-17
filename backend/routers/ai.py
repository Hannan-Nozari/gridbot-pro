"""AI Auto-Pilot router — runs backtests, ranks strategies, deploys the best."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import verify_token
from database import insert_bot, update_bot_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(verify_token)])


# ─────────────────────────────────────────────────────────
#  Analysis configuration
# ─────────────────────────────────────────────────────────

# Default universe for AI to analyse — popular USDT pairs
DEFAULT_PAIRS = [
    {"symbol": "ETH/USDT", "grid_range_pct": 0.12, "num_grids": 10},
    {"symbol": "SOL/USDT", "grid_range_pct": 0.15, "num_grids": 10},
    {"symbol": "BNB/USDT", "grid_range_pct": 0.10, "num_grids": 10},
    {"symbol": "BTC/USDT", "grid_range_pct": 0.08, "num_grids": 12},
]

DEFAULT_STRATEGIES = ["grid", "dca", "mean_reversion"]

# How we score strategies (higher = better)
#   score = return_pct * w_return
#         + sharpe      * w_sharpe
#         - max_dd      * w_drawdown_penalty
SCORE_WEIGHTS = {
    "return": 1.0,
    "sharpe": 2.0,
    "drawdown_penalty": 0.5,
}


# ─────────────────────────────────────────────────────────
#  Models
# ─────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    investment: float = Field(1000, ge=50, le=1_000_000)
    days: int = Field(90, ge=7, le=365)
    pairs: Optional[List[str]] = None
    strategies: Optional[List[str]] = None


class StrategyResult(BaseModel):
    pair: str
    strategy: str
    pnl: float
    pnl_pct: float
    monthly_roi: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    num_trades: int
    score: float
    config: Dict[str, Any]


class AnalyzeResponse(BaseModel):
    investment: float
    days: int
    results_30d: List[StrategyResult]
    results_90d: List[StrategyResult]
    recommendation: StrategyResult
    alternative: Optional[StrategyResult] = None
    confidence: str  # "high" | "medium" | "low"
    risk_level: str  # "low" | "medium" | "high"
    expected_monthly_return_usd: float
    expected_monthly_return_pct: float


class DeployRequest(BaseModel):
    investment: float = Field(..., ge=50, le=1_000_000)
    pair: str
    strategy: str
    config: Dict[str, Any]
    paper: bool = True
    name: Optional[str] = None


class DeployResponse(BaseModel):
    bot_id: str
    name: str
    status: str
    message: str


# ─────────────────────────────────────────────────────────
#  Scoring helpers
# ─────────────────────────────────────────────────────────

def _compute_score(metrics: Dict[str, float]) -> float:
    """Composite score. Higher = better risk-adjusted return."""
    ret = metrics.get("pnl_pct", 0)
    sharpe = metrics.get("sharpe_ratio", 0) or 0
    dd = abs(metrics.get("max_drawdown_pct", 0)) or 0

    # Clamp extreme sharpe to avoid dominating the score
    sharpe = max(-3, min(5, sharpe))

    score = (
        ret * SCORE_WEIGHTS["return"]
        + sharpe * SCORE_WEIGHTS["sharpe"]
        - dd * SCORE_WEIGHTS["drawdown_penalty"]
    )
    return round(score, 2)


def _confidence(best: Dict, alternative: Optional[Dict]) -> str:
    """Confidence in the recommendation based on score spread & abs values."""
    best_score = best.get("score", 0)
    if best_score < 0:
        return "low"
    if alternative is None:
        return "high" if best_score > 10 else "medium"
    spread = best_score - alternative.get("score", 0)
    if spread > 15 and best_score > 10:
        return "high"
    if spread > 5:
        return "medium"
    return "low"


def _risk_level(metrics: Dict[str, float]) -> str:
    dd = abs(metrics.get("max_drawdown_pct", 0))
    if dd < 8:
        return "low"
    if dd < 18:
        return "medium"
    return "high"


def _build_config(pair_cfg: Dict, strategy: str, investment: float, current_price: float) -> Dict:
    """Generate strategy config based on pair and current price."""
    if strategy == "grid":
        range_pct = pair_cfg.get("grid_range_pct", 0.12)
        num_grids = pair_cfg.get("num_grids", 10)
        return {
            "symbol": pair_cfg["symbol"],
            "lower_price": round(current_price * (1 - range_pct), 4),
            "upper_price": round(current_price * (1 + range_pct), 4),
            "num_grids": num_grids,
            "total_investment": investment,
        }
    elif strategy == "dca":
        return {
            "symbol": pair_cfg["symbol"],
            "total_investment": investment,
            "buy_interval_hours": 4,
            "take_profit_pct": 3.0,
            "chunk_pct": 2.0,
        }
    elif strategy == "mean_reversion":
        return {
            "symbol": pair_cfg["symbol"],
            "total_investment": investment,
            "bb_period": 20,
            "z_entry": 2.0,
            "z_exit": 0.5,
            "position_pct": 10,
        }
    return {"symbol": pair_cfg["symbol"], "total_investment": investment}


# ─────────────────────────────────────────────────────────
#  Analysis endpoint
# ─────────────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(body: AnalyzeRequest, request: Request):
    """
    Run backtests across multiple pairs × strategies for 30 and 90 days,
    score each combination, and return the best recommendation.

    This is the "AI analysis" step of the Auto-Pilot wizard.
    """
    try:
        from services.backtest_service import run_backtest
        from routers.market import _get_exchange
    except Exception as exc:
        raise HTTPException(500, f"Backtest service unavailable: {exc}")

    investment = body.investment
    pairs = body.pairs or [p["symbol"] for p in DEFAULT_PAIRS]
    strategies = body.strategies or DEFAULT_STRATEGIES

    # Fetch current prices once per pair (uses configured exchange)
    current_prices: Dict[str, float] = {}
    exchange = _get_exchange()
    for symbol in pairs:
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_prices[symbol] = float(ticker.get("last") or 0)
        except Exception:
            current_prices[symbol] = 0

    # Find full pair configs
    pair_cfgs = {p["symbol"]: p for p in DEFAULT_PAIRS}
    for symbol in pairs:
        if symbol not in pair_cfgs:
            pair_cfgs[symbol] = {"symbol": symbol, "grid_range_pct": 0.10, "num_grids": 10}

    results_30d: List[StrategyResult] = []
    results_90d: List[StrategyResult] = []

    # Run backtests for each combination × both timeframes
    for pair in pairs:
        pair_cfg = pair_cfgs[pair]
        price = current_prices.get(pair, 0)

        # Investment per bot = user's total (AI will pick the single best to allocate to)
        inv_per_bot = investment

        for strat in strategies:
            cfg = _build_config(pair_cfg, strat, inv_per_bot, price)

            # Translate the web-shape config to the strategy-class init args
            bt_params = _config_to_bt_params(strat, cfg, price)

            for days, bucket in [(30, results_30d), (90, results_90d)]:
                try:
                    result = run_backtest(
                        strategy=strat,
                        symbol=pair,
                        days=days,
                        params=bt_params,
                    )
                    metrics = (result or {}).get("metrics", {})
                    score = _compute_score(metrics)

                    bucket.append(
                        StrategyResult(
                            pair=pair,
                            strategy=strat,
                            pnl=metrics.get("pnl", 0),
                            pnl_pct=metrics.get("pnl_pct", 0),
                            monthly_roi=metrics.get("monthly_roi", 0),
                            sharpe=metrics.get("sharpe_ratio", 0),
                            max_drawdown=metrics.get("max_drawdown_pct", 0),
                            win_rate=metrics.get("win_rate", 0),
                            num_trades=metrics.get("num_trades", 0),
                            score=score,
                            config=cfg,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Backtest failed %s %s %dd: %s", pair, strat, days, exc
                    )

    # Sort each bucket by score (best first)
    results_30d.sort(key=lambda r: r.score, reverse=True)
    results_90d.sort(key=lambda r: r.score, reverse=True)

    # The recommendation: best of 90d (longer history = more reliable)
    # but only if it's also positive in 30d
    if not results_90d:
        raise HTTPException(500, "No backtest results produced — check logs")

    best_90d = results_90d[0]

    # Verify the 90d winner is also profitable in 30d
    match_30d = next(
        (r for r in results_30d if r.pair == best_90d.pair and r.strategy == best_90d.strategy),
        None,
    )
    if match_30d and match_30d.pnl_pct < -5:
        # 30d is very negative → fall back to best 30d winner
        best = results_30d[0] if results_30d else best_90d
    else:
        best = best_90d

    alternative = results_90d[1] if len(results_90d) > 1 else None

    best_dict = best.model_dump()
    alt_dict = alternative.model_dump() if alternative else None

    monthly_pct = best.monthly_roi
    monthly_usd = investment * (monthly_pct / 100)

    return AnalyzeResponse(
        investment=investment,
        days=body.days,
        results_30d=results_30d,
        results_90d=results_90d,
        recommendation=best,
        alternative=alternative,
        confidence=_confidence(best_dict, alt_dict),
        risk_level=_risk_level({"max_drawdown_pct": best.max_drawdown}),
        expected_monthly_return_usd=round(monthly_usd, 2),
        expected_monthly_return_pct=round(monthly_pct, 2),
    )


def _config_to_bt_params(strategy: str, cfg: Dict, price: float) -> Dict:
    """Translate the web-shape config dict to backtest service params."""
    if strategy == "grid":
        return {
            "lower": cfg.get("lower_price") or price * 0.88,
            "upper": cfg.get("upper_price") or price * 1.12,
            "num_grids": cfg.get("num_grids", 10),
            "investment": cfg.get("total_investment", 100),
        }
    elif strategy == "dca":
        return {
            "investment": cfg.get("total_investment", 100),
            "buy_interval_hours": cfg.get("buy_interval_hours", 4),
            "take_profit_pct": cfg.get("take_profit_pct", 3.0),
            "chunk_pct": cfg.get("chunk_pct", 2.0),
        }
    elif strategy == "mean_reversion":
        return {
            "investment": cfg.get("total_investment", 100),
            "bb_period": cfg.get("bb_period", 20),
            "z_entry": cfg.get("z_entry", 2.0),
            "z_exit": cfg.get("z_exit", 0.5),
            "position_pct": cfg.get("position_pct", 10),
        }
    return {"investment": cfg.get("total_investment", 100)}


# ─────────────────────────────────────────────────────────
#  Deploy endpoint
# ─────────────────────────────────────────────────────────

@router.post("/deploy", response_model=DeployResponse)
async def deploy_recommendation(body: DeployRequest, request: Request):
    """
    Deploy the AI-recommended strategy as a running bot. Creates, persists,
    registers with the bot manager, and starts it in one call.
    """
    bm = request.app.state.bot_manager

    # Map strategy → bot type. For now: grid strategy → grid bot
    strat_to_bot = {
        "grid": "grid",
        "dca": "grid",  # no dedicated DCA bot yet → use grid as safe default
        "mean_reversion": "smart",
        "momentum": "smart",
    }
    bot_type = strat_to_bot.get(body.strategy, "grid")

    bot_id = str(uuid.uuid4())
    name = body.name or f"AI {body.strategy.capitalize()} · {body.pair}"

    # Persist
    try:
        insert_bot(
            bot_id=bot_id,
            name=name,
            bot_type=bot_type,
            config=body.config,
            paper=body.paper,
        )
    except Exception as exc:
        raise HTTPException(500, f"DB error: {exc}")

    # Register with manager
    try:
        bm.create_bot(bot_id, bot_type, body.config, paper=body.paper)
    except Exception as exc:
        logger.warning("create_bot failed: %s", exc)

    # Start it
    try:
        bm.start_bot(bot_id)
        update_bot_status(bot_id, "running", timestamp_col="started_at")
        status = "running"
        msg = f"Auto-Pilot deployed {name}. Monitoring started."
    except Exception as exc:
        logger.warning("start_bot failed: %s", exc)
        update_bot_status(bot_id, "error")
        status = "error"
        msg = f"Bot created but failed to start: {exc}"

    # Fire alert if configured
    try:
        alert = getattr(request.app.state, "alert_service", None)
        if alert:
            alert.send_telegram(
                f"🚀 <b>Auto-Pilot Deployed</b>\n"
                f"Bot: {name}\n"
                f"Pair: {body.pair}\n"
                f"Strategy: {body.strategy}\n"
                f"Investment: ${body.investment:.2f}\n"
                f"Mode: {'Paper' if body.paper else 'LIVE'}"
            )
    except Exception:
        pass

    return DeployResponse(
        bot_id=bot_id,
        name=name,
        status=status,
        message=msg,
    )
