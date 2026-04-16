"""Router for backtesting operations."""

from __future__ import annotations

import json
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import verify_token
from database import (
    get_backtest_result,
    insert_backtest_result,
    list_backtest_results,
)
from models import BacktestRequest, BacktestResponse
from services.backtest_service import run_backtest

router = APIRouter(prefix="/backtest", tags=["backtest"], dependencies=[Depends(verify_token)])


def _row_to_response(row: dict) -> BacktestResponse:
    """Convert a DB row to a BacktestResponse."""
    result = row.get("result", "{}")
    if isinstance(result, str):
        result = json.loads(result)

    metrics = result.get("metrics", {})
    return BacktestResponse(
        id=row["id"],
        strategy=row["strategy"],
        symbol=row["symbol"],
        pnl=metrics.get("pnl", 0.0),
        pnl_pct=metrics.get("pnl_pct", 0.0),
        monthly_roi=metrics.get("monthly_roi", 0.0),
        sharpe=metrics.get("sharpe", 0.0),
        max_drawdown=metrics.get("max_drawdown", 0.0),
        win_rate=metrics.get("win_rate", 0.0),
        profit_factor=metrics.get("profit_factor", 0.0),
        num_trades=metrics.get("num_trades", 0),
        total_fees=metrics.get("total_fees", 0.0),
        equity_curve=result.get("equity_curve", []),
        trades=result.get("trades", []),
    )


@router.post("/run", response_model=BacktestResponse, status_code=201)
async def run_backtest_endpoint(body: BacktestRequest):
    """Execute a backtest, cache the result in DB, and return it."""
    try:
        result = run_backtest(
            strategy=body.strategy,
            symbol=body.symbol,
            days=body.days,
            params=body.params,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Backtest execution failed: {exc}"
        ) from exc

    result_id = str(uuid.uuid4())
    insert_backtest_result(
        result_id=result_id,
        strategy=body.strategy,
        symbol=body.symbol,
        params=body.params,
        days=body.days,
        result=result,
    )

    row = get_backtest_result(result_id)
    if not row:
        raise HTTPException(status_code=500, detail="Failed to persist backtest result")

    return _row_to_response(row)


@router.get("/results", response_model=List[BacktestResponse])
async def list_results(
    limit: int = Query(50, ge=1, le=200, description="Max results to return"),
):
    """List cached backtest results."""
    rows = list_backtest_results(limit=limit)
    return [_row_to_response(r) for r in rows]


@router.get("/results/{result_id}", response_model=BacktestResponse)
async def get_result(result_id: str):
    """Get a specific backtest result by ID."""
    row = get_backtest_result(result_id)
    if not row:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return _row_to_response(row)
