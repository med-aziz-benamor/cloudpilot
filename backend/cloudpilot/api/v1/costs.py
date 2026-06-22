"""Cost analytics endpoints — summary, breakdown, timeseries, drivers, anomalies."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.api.deps import get_current_user, get_db
from cloudpilot.models.user import User
from cloudpilot.schemas.cost import (
    AnomalyEntry,
    CostBreakdownResponse,
    CostSummary,
    CostTimeseriesResponse,
    TopCostDriver,
)
from cloudpilot.services.cost_service import CostService

router = APIRouter()


@router.get("/summary", response_model=CostSummary)
async def cost_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CostSummary:
    return await CostService(db, user.organization_id).get_summary()


@router.get("/breakdown", response_model=CostBreakdownResponse)
async def cost_breakdown(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CostBreakdownResponse:
    data = await CostService(db, user.organization_id).get_breakdown()
    return CostBreakdownResponse(**data)


@router.get("/timeseries", response_model=CostTimeseriesResponse)
async def cost_timeseries(
    period_days: int = Query(default=90, ge=7, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CostTimeseriesResponse:
    return await CostService(db, user.organization_id).get_timeseries(period_days)


@router.get("/top-drivers", response_model=list[TopCostDriver])
async def top_drivers(
    limit: int = Query(default=5, ge=1, le=20),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TopCostDriver]:
    return await CostService(db, user.organization_id).get_top_drivers(limit)


@router.get("/anomalies", response_model=list[AnomalyEntry])
async def anomalies(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AnomalyEntry]:
    return await CostService(db, user.organization_id).get_anomalies()
