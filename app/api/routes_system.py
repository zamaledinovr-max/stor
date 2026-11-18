"""Unauthenticated health check for load balancers and containers."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.timeutils import utcnow

router = APIRouter(prefix="/api", tags=["system"])


class HealthOut(BaseModel):
    status: str
    time: datetime


@router.get("/health", response_model=HealthOut, summary="Проверка живости")
def health() -> HealthOut:
    return HealthOut(status="ok", time=utcnow())
