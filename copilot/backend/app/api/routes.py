from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .. import __version__
from ..security import parse_bearer, token_matches

router = APIRouter(prefix="/api")


def require_token(request: Request) -> None:
    expected: str = request.app.state.token
    if not token_matches(expected, parse_bearer(request.headers.get("authorization"))):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing token")


@router.get("/health")
async def health() -> dict:
    """Unauthenticated liveness probe. Reveals nothing about the account."""
    return {"ok": True, "version": __version__}


@router.get("/status", dependencies=[Depends(require_token)])
async def get_status(request: Request) -> dict:
    hub = request.app.state.hub
    return {
        "version": __version__,
        "readOnly": True,
        "clients": hub.subscriber_count,
        "feed": hub.status_payload(),
    }


@router.get("/analysis", dependencies=[Depends(require_token)])
async def get_analysis(request: Request) -> dict:
    last = request.app.state.analysis.last
    if last is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "no analysis yet")
    return last


@router.get("/symbol", dependencies=[Depends(require_token)])
async def get_symbol(request: Request) -> dict:
    hub = request.app.state.hub
    if hub.spec is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "symbol spec not loaded yet")
    return hub.spec.to_wire()
