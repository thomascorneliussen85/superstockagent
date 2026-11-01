"""Coach REST API (token-protected, read + generate reviews only)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from ..coach.validation import evaluate_candidates
from .routes import require_token

router = APIRouter(prefix="/api/coach", dependencies=[Depends(require_token)])


@router.get("/summary")
async def coach_summary(request: Request) -> dict:
    return request.app.state.coach.summary()


@router.post("/refresh")
async def coach_refresh(request: Request) -> dict:
    coach = request.app.state.coach
    await asyncio.to_thread(coach.refresh_sync)
    await coach.evaluate_ai()
    coach.publish()
    return coach.summary()


@router.get("/similar")
async def coach_similar(request: Request) -> dict:
    return request.app.state.coach.similar_now()


@router.get("/reviews")
async def coach_reviews(request: Request, limit: int = 30) -> dict:
    return {"reviews": request.app.state.coach.store.reviews(limit)}


class ReviewIn(BaseModel):
    period: str = "day"
    useAi: bool = True


@router.post("/reviews")
async def coach_make_review(body: ReviewIn, request: Request) -> dict:
    if body.period not in ("day", "week"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "period må være day eller week")
    return await request.app.state.coach.generate_review(body.period, use_ai=body.useAi)


@router.get("/walkforward")
async def coach_walkforward(request: Request) -> dict:
    trades = request.app.state.journal.store.trades()
    return {"candidates": await asyncio.to_thread(evaluate_candidates, trades)}
