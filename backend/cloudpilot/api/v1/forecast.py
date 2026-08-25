"""Forecast endpoints — reads persisted Prophet snapshots, and the budget the
overrun checks are measured against."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.api.deps import client_ip, get_current_user, get_db, require_permission
from cloudpilot.core.audit import write_audit
from cloudpilot.models.user import User
from cloudpilot.schemas.forecast import BudgetResponse, BudgetUpdate, ForecastResponse
from cloudpilot.services.forecast_service import ForecastService

router = APIRouter()


@router.get("", response_model=ForecastResponse)
async def get_forecast(
    horizon_days: int = Query(default=30, ge=30, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ForecastResponse:
    return await ForecastService(db, user.organization_id).get_forecast(horizon_days)


@router.get("/budget", response_model=BudgetResponse)
async def get_budget(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    budget = await ForecastService(db, user.organization_id).get_budget()
    return BudgetResponse(budget_usd=budget)


@router.patch("/budget", response_model=BudgetResponse)
async def set_budget(
    payload: BudgetUpdate,
    request: Request,
    user: User = Depends(require_permission("budget.manage")),
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    """Set the organization's monthly budget.

    Audited: this changes the threshold every ForecastAgent overrun alert is
    measured against, so who moved it and to what is worth being able to prove
    after the fact.
    """
    service = ForecastService(db, user.organization_id)
    previous = await service.get_budget()
    stored = await service.set_budget(payload.budget_usd)

    await write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        event_type="budget.update",
        resource_type="organization",
        resource_id=str(user.organization_id),
        payload={"previous_usd": previous, "new_usd": stored},
        ip_address=client_ip(request),
    )
    return BudgetResponse(budget_usd=stored)
