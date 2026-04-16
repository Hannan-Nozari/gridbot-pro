"""Router for portfolio analytics and equity curves."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import verify_token
from database import get_portfolio_snapshots, get_portfolio_summary, list_bots, get_bot_pnl
from models import PortfolioSummary

router = APIRouter(
    prefix="/portfolio", tags=["portfolio"], dependencies=[Depends(verify_token)]
)

_PERIOD_DAYS = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "all": None,
}


@router.get("/summary", response_model=PortfolioSummary)
async def portfolio_summary(request: Request):
    """Return aggregate portfolio summary combining DB stats with live bot data."""
    db_summary = get_portfolio_summary()

    # Enrich with live bot data if available
    try:
        bm = request.app.state.bot_manager
        all_statuses = bm.get_all_statuses()
        live_value = sum(
            s.get("total_value", 0.0)
            for s in all_statuses.values()
            if isinstance(s, dict)
        )
        if live_value > 0:
            db_summary["total_value"] = live_value
            if db_summary["total_value"] > 0:
                db_summary["pnl_pct"] = (
                    db_summary["total_pnl"] / db_summary["total_value"] * 100
                )
    except Exception:
        pass  # Gracefully fall back to DB-only data

    return PortfolioSummary(**db_summary)


@router.get("/equity-curve")
async def equity_curve(
    period: str = Query("30d", description="Time period: 7d, 30d, 90d, or all"),
):
    """Return equity curve time-series data filtered by period."""
    if period not in _PERIOD_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period. Choose from: {', '.join(_PERIOD_DAYS)}",
        )

    days = _PERIOD_DAYS[period]
    snapshots = get_portfolio_snapshots(limit=10_000)

    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
        snapshots = [
            s for s in snapshots
            if s.get("timestamp", "") >= cutoff_str
        ]

    # Reverse so oldest is first (snapshots come newest-first from DB)
    snapshots.reverse()

    return {
        "period": period,
        "data": [
            {
                "timestamp": s["timestamp"],
                "total_value": s["total_value"],
                "pnl": s["pnl"],
            }
            for s in snapshots
        ],
    }


@router.get("/analytics")
async def portfolio_analytics(request: Request):
    """Compute aggregate analytics across all bots."""
    bots = list_bots()
    if not bots:
        return {
            "total_bots": 0,
            "running_bots": 0,
            "stopped_bots": 0,
            "total_pnl": 0.0,
            "best_bot": None,
            "worst_bot": None,
            "bots": [],
        }

    # Collect per-bot PnL data
    bot_analytics = []
    for bot in bots:
        pnl_data = get_bot_pnl(bot["id"])
        bot_analytics.append({
            "id": bot["id"],
            "name": bot["name"],
            "type": bot["type"],
            "status": bot["status"],
            "pnl": pnl_data.get("pnl", 0.0),
        })

    # Enrich statuses from live bot manager
    try:
        bm = request.app.state.bot_manager
        all_statuses = bm.get_all_statuses()
        for ba in bot_analytics:
            live = all_statuses.get(ba["id"])
            if isinstance(live, dict) and "status" in live:
                ba["status"] = live["status"]
    except Exception:
        pass

    total_pnl = sum(b["pnl"] for b in bot_analytics)
    running = sum(1 for b in bot_analytics if b["status"] == "running")
    stopped = len(bot_analytics) - running

    sorted_by_pnl = sorted(bot_analytics, key=lambda b: b["pnl"])
    best_bot = sorted_by_pnl[-1] if sorted_by_pnl else None
    worst_bot = sorted_by_pnl[0] if sorted_by_pnl else None

    return {
        "total_bots": len(bot_analytics),
        "running_bots": running,
        "stopped_bots": stopped,
        "total_pnl": total_pnl,
        "best_bot": best_bot,
        "worst_bot": worst_bot,
        "bots": bot_analytics,
    }
