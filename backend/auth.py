import secrets
from typing import Annotated, Dict, Optional, Set

from fastapi import APIRouter, Depends, Header, HTTPException, status

from config import settings
from models import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory set of valid tokens. Cleared on server restart.
_active_tokens: Set[str] = set()


def _create_token() -> str:
    token = secrets.token_hex(32)
    _active_tokens.add(token)
    return token


def verify_token(
    authorization: Annotated[Optional[str], Header()] = None,
) -> str:
    """FastAPI dependency that validates the Bearer token."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected: Bearer <token>",
        )
    token = parts[1]
    if token not in _active_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return token


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    if body.password != settings.AUTH_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )
    token = _create_token()
    return TokenResponse(token=token)


@router.post("/logout")
def logout(token: str = Depends(verify_token)) -> Dict[str, str]:
    _active_tokens.discard(token)
    return {"detail": "Logged out"}
