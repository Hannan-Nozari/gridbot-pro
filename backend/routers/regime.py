"""Market regime detection router."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/regime", tags=["regime"], dependencies=[Depends(verify_token)])


class ThresholdUpdate(BaseModel):
    auto_pause_enabled: Optional[bool] = None
    auto_resume_enabled: Optional[bool] = None
    btc_1h_caution_pct: Optional[float] = None
    btc_1h_bad_pct: Optional[float] = None
    btc_24h_caution_pct: Optional[float] = None
    btc_24h_bad_pct: Optional[float] = None
    volatility_caution_pct: Optional[float] = None
    volatility_bad_pct: Optional[float] = None
    trend_caution_pct: Optional[float] = None
    trend_bad_pct: Optional[float] = None
    drawdown_caution_pct: Optional[float] = None
    drawdown_bad_pct: Optional[float] = None
    resume_cooldown_minutes: Optional[int] = None
    check_interval_seconds: Optional[int] = None


@router.get("/status")
async def get_status():
    """Current regime + latest signals."""
    from services.regime_detector import get_regime_detector
    det = get_regime_detector()
    if det is None:
        return {
            "regime": "unknown",
            "action": "hold",
            "summary": "Regime detector not running",
            "enabled": False,
        }

    report = det.last_report
    if report is None:
        # Run one analysis on-demand
        try:
            report = det.analyze()
        except Exception as exc:
            raise HTTPException(500, f"Analysis failed: {exc}")

    return {
        **report.to_dict(),
        "enabled": True,
        "thresholds": det.thresholds.__dict__,
        "bots_paused_by_regime": len(det._paused_by_us),
    }


@router.get("/history")
async def get_history(limit: int = Query(50, ge=1, le=500)):
    """Past regime transitions."""
    from services.regime_detector import get_regime_detector
    det = get_regime_detector()
    if det is None:
        return {"history": []}
    return {"history": det.get_history(limit=limit)}


@router.post("/analyze-now")
async def analyze_now():
    """Force an immediate analysis (ignores the schedule)."""
    from services.regime_detector import get_regime_detector
    det = get_regime_detector()
    if det is None:
        raise HTTPException(503, "Regime detector not running")

    try:
        report = det.analyze()
        det._last_report = report
        return report.to_dict()
    except Exception as exc:
        raise HTTPException(500, f"Analysis failed: {exc}")


@router.put("/thresholds")
async def update_thresholds(body: ThresholdUpdate):
    """Update regime detection thresholds."""
    from services.regime_detector import get_regime_detector
    det = get_regime_detector()
    if det is None:
        raise HTTPException(503, "Regime detector not running")

    data = body.model_dump(exclude_none=True)
    for k, v in data.items():
        if hasattr(det.thresholds, k):
            setattr(det.thresholds, k, v)

    return {"thresholds": det.thresholds.__dict__}
