"""Router for bot CRUD and lifecycle management."""

from __future__ import annotations

import json
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import verify_token
from database import (
    delete_bot,
    get_bot,
    get_bot_pnl,
    insert_bot,
    list_bots,
    update_bot_status,
)
from models import BotCreate, BotResponse

router = APIRouter(prefix="/bots", tags=["bots"], dependencies=[Depends(verify_token)])


def _bot_manager(request: Request):
    """Retrieve the BotManager instance from app state."""
    return request.app.state.bot_manager


def _row_to_response(row: dict, status_override: Optional[str] = None) -> BotResponse:
    """Convert a DB row dict to a BotResponse model."""
    config = row.get("config", "{}")
    if isinstance(config, str):
        config = json.loads(config)
    pnl_data = get_bot_pnl(row["id"])
    return BotResponse(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        status=status_override or row.get("status", "unknown"),
        paper=bool(row.get("paper", True)),
        config=config,
        created_at=row.get("created_at"),
        pnl=pnl_data.get("pnl", 0.0),
        total_value=pnl_data.get("total_value", 0.0),
    )


@router.get("", response_model=List[BotResponse])
async def get_bots(request: Request):
    """List all bots with live status from the bot manager."""
    bm = _bot_manager(request)
    rows = list_bots()
    all_statuses = bm.get_all_statuses()

    results: List[BotResponse] = []
    for row in rows:
        live_status = all_statuses.get(row["id"], {}).get("status")
        results.append(_row_to_response(row, status_override=live_status))
    return results


@router.post("", response_model=BotResponse, status_code=201)
async def create_bot(body: BotCreate, request: Request):
    """Create a new bot, persist to DB, and register with the bot manager."""
    bm = _bot_manager(request)
    bot_id = str(uuid.uuid4())

    row = insert_bot(
        bot_id=bot_id,
        name=body.name,
        bot_type=body.type,
        config=body.config,
        paper=body.paper,
    )

    try:
        bm.create_bot(bot_id, body.type, body.config, paper=body.paper)
    except Exception as exc:
        # Roll back DB entry if manager registration fails
        delete_bot(bot_id)
        raise HTTPException(status_code=500, detail=f"Bot manager error: {exc}") from exc

    return _row_to_response(row)


@router.get("/{bot_id}", response_model=BotResponse)
async def get_bot_detail(bot_id: str, request: Request):
    """Get detailed bot info, preferring live status from the bot manager."""
    row = get_bot(bot_id)
    if not row:
        raise HTTPException(status_code=404, detail="Bot not found")

    bm = _bot_manager(request)
    try:
        live = bm.get_status(bot_id)
        live_status = live.get("status") if isinstance(live, dict) else None
    except Exception:
        live_status = None

    return _row_to_response(row, status_override=live_status)


@router.post("/{bot_id}/start", response_model=BotResponse)
async def start_bot(bot_id: str, request: Request):
    """Start a bot via the bot manager and update DB status."""
    row = get_bot(bot_id)
    if not row:
        raise HTTPException(status_code=404, detail="Bot not found")

    if row["status"] == "running":
        raise HTTPException(status_code=409, detail="Bot is already running")

    bm = _bot_manager(request)
    try:
        bm.start_bot(bot_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {exc}") from exc

    update_bot_status(bot_id, "running", timestamp_col="started_at")
    row = get_bot(bot_id)
    return _row_to_response(row, status_override="running")


@router.post("/{bot_id}/stop", response_model=BotResponse)
async def stop_bot(bot_id: str, request: Request):
    """Stop a running bot via the bot manager and update DB status."""
    row = get_bot(bot_id)
    if not row:
        raise HTTPException(status_code=404, detail="Bot not found")

    if row["status"] != "running":
        raise HTTPException(status_code=409, detail="Bot is not running")

    bm = _bot_manager(request)
    try:
        bm.stop_bot(bot_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to stop bot: {exc}") from exc

    update_bot_status(bot_id, "stopped", timestamp_col="stopped_at")
    row = get_bot(bot_id)
    return _row_to_response(row, status_override="stopped")


@router.delete("/{bot_id}", status_code=204)
async def remove_bot(bot_id: str, request: Request):
    """Delete a bot. Must be stopped first."""
    row = get_bot(bot_id)
    if not row:
        raise HTTPException(status_code=404, detail="Bot not found")

    if row["status"] == "running":
        raise HTTPException(
            status_code=409,
            detail="Bot must be stopped before deletion",
        )

    bm = _bot_manager(request)
    try:
        bm.remove_bot(bot_id)
    except Exception:
        pass  # Bot may not be registered in the manager

    delete_bot(bot_id)
    return None
