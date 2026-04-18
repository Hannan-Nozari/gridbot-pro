"""Autonomy router — control the set-and-forget loops."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/autonomy", tags=["autonomy"], dependencies=[Depends(verify_token)])


class ConfigUpdate(BaseModel):
    rebalance_enabled: Optional[bool] = None
    rebalance_drift_pct: Optional[float] = None
    rebalance_notify_only: Optional[bool] = None
    weekly_reeval_enabled: Optional[bool] = None
    digest_enabled: Optional[bool] = None
    digest_hour_utc: Optional[int] = None


@router.get("/status")
async def get_status():
    from services.autonomy_service import get_autonomy_service
    svc = get_autonomy_service()
    if svc is None:
        return {"enabled": False, "summary": "Autonomy service not running"}

    return {
        "enabled": True,
        "config": {
            "rebalance_enabled": svc.config.rebalance_enabled,
            "rebalance_drift_pct": svc.config.rebalance_drift_pct,
            "rebalance_notify_only": svc.config.rebalance_notify_only,
            "rebalance_check_seconds": svc.config.rebalance_check_seconds,
            "weekly_reeval_enabled": svc.config.weekly_reeval_enabled,
            "weekly_reeval_day": svc.config.weekly_reeval_day,
            "weekly_reeval_hour_utc": svc.config.weekly_reeval_hour_utc,
            "digest_enabled": svc.config.digest_enabled,
            "digest_hour_utc": svc.config.digest_hour_utc,
        },
        "last_rebalance_check": svc._last_rebalance_check,
        "last_reeval_check": svc._last_reeval_check,
        "last_digest_sent": svc._last_digest_sent,
        "rebalance_actions": svc._rebalance_actions[-10:],
    }


@router.put("/config")
async def update_config(body: ConfigUpdate):
    from services.autonomy_service import get_autonomy_service
    svc = get_autonomy_service()
    if svc is None:
        raise HTTPException(503, "Autonomy service not running")

    data = body.model_dump(exclude_none=True)
    for k, v in data.items():
        if hasattr(svc.config, k):
            setattr(svc.config, k, v)

    return {"config": svc.config.__dict__}


@router.post("/digest/send-now")
async def send_digest_now():
    """Force the daily digest to send immediately (for testing)."""
    from services.autonomy_service import get_autonomy_service
    svc = get_autonomy_service()
    if svc is None:
        raise HTTPException(503, "Autonomy service not running")

    # Force by resetting last-sent time
    svc._last_digest_sent = 0
    # Lie about the hour to trigger the check unconditionally
    original_hour = svc.config.digest_hour_utc
    from datetime import datetime, timezone
    svc.config.digest_hour_utc = datetime.now(timezone.utc).hour
    try:
        svc._check_daily_digest()
    finally:
        svc.config.digest_hour_utc = original_hour
    return {"sent": True}


@router.post("/rebalance/check-now")
async def rebalance_check_now():
    """Force an immediate rebalance check."""
    from services.autonomy_service import get_autonomy_service
    svc = get_autonomy_service()
    if svc is None:
        raise HTTPException(503, "Autonomy service not running")

    svc._last_rebalance_check = 0
    svc._check_rebalance()
    return {
        "checked": True,
        "actions": svc._rebalance_actions[-10:],
    }
