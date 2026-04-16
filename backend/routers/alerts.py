"""Router for alert configuration and test notifications."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import verify_token
from database import get_alert_config, update_alert_config
from models import AlertConfig

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(verify_token)])


def _alert_service(request: Request):
    """Retrieve the AlertService instance from app state."""
    return request.app.state.alert_service


@router.get("/config", response_model=AlertConfig)
async def get_config():
    """Return the current alert configuration."""
    raw = get_alert_config()
    return AlertConfig(**raw) if raw else AlertConfig()


@router.put("/config", response_model=AlertConfig)
async def set_config(body: AlertConfig):
    """Update the alert configuration."""
    update_alert_config(body.model_dump())
    # Return the persisted config
    raw = get_alert_config()
    return AlertConfig(**raw) if raw else body


@router.post("/test/email", status_code=200)
async def test_email(request: Request):
    """Send a test email using the current alert configuration."""
    raw = get_alert_config()
    config = AlertConfig(**raw) if raw else AlertConfig()

    if not config.email.enabled:
        raise HTTPException(status_code=400, detail="Email alerts are not enabled")

    svc = _alert_service(request)
    try:
        svc.send_email(
            subject="Crypto Grid Bot - Test Alert",
            body="This is a test email from your crypto grid trading bot. If you received this, email alerts are working correctly.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to send test email: {exc}"
        ) from exc

    return {"status": "ok", "message": "Test email sent successfully"}


@router.post("/test/telegram", status_code=200)
async def test_telegram(request: Request):
    """Send a test Telegram message using the current alert configuration."""
    raw = get_alert_config()
    config = AlertConfig(**raw) if raw else AlertConfig()

    if not config.telegram.enabled:
        raise HTTPException(status_code=400, detail="Telegram alerts are not enabled")

    svc = _alert_service(request)
    try:
        svc.send_telegram(
            message="Crypto Grid Bot - Test Alert\n\nThis is a test message. If you received this, Telegram alerts are working correctly.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to send test Telegram message: {exc}"
        ) from exc

    return {"status": "ok", "message": "Test Telegram message sent successfully"}
