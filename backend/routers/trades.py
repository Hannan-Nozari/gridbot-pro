"""Router for trade history queries."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from auth import verify_token
from database import get_trades
from models import TradeResponse

router = APIRouter(prefix="/trades", tags=["trades"], dependencies=[Depends(verify_token)])


@router.get("", response_model=List[TradeResponse])
async def list_trades(
    bot_id: Optional[str] = Query(None, description="Filter by bot ID"),
    symbol: Optional[str] = Query(None, description="Filter by trading symbol"),
    side: Optional[str] = Query(None, pattern="^(buy|sell)$", description="Filter by trade side"),
    limit: int = Query(50, ge=1, le=500, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    """Return a paginated list of trades with optional filters."""
    rows = get_trades(bot_id=bot_id, limit=limit, offset=offset)

    # Apply in-memory filters for fields the DB helper doesn't support directly
    if symbol:
        rows = [r for r in rows if r.get("symbol", "").upper() == symbol.upper()]
    if side:
        rows = [r for r in rows if r.get("side", "").lower() == side.lower()]

    return [TradeResponse(**r) for r in rows]
