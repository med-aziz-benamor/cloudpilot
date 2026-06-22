"""Forecast endpoint — reads persisted Prophet snapshots."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.api.deps import get_current_user, get_db
from cloudpilot.models.user import User
from cloudpilot.schemas.forecast import ForecastResponse
from cloudpilot.services.forecast_service import ForecastService

router = APIRouter()


@router.get("", response_model=ForecastResponse)
async def get_forecast(
    horizon_days: int = Query(default=30, ge=30, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ForecastResponse:
    return await ForecastService(db, user.organization_id).get_forecast(horizon_days)
