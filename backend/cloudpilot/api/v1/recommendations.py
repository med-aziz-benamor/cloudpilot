"""Recommendation endpoints — list, savings summary, status updates."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.api.deps import get_current_user, get_db, require_permission
from cloudpilot.models.recommendation import AgentType, RecommendationStatus
from cloudpilot.models.user import User
from cloudpilot.schemas.recommendation import (
    RecommendationResponse,
    RecommendationStatusUpdate,
    SavingsSummary,
)
from cloudpilot.services.recommendation_service import RecommendationService

router = APIRouter()


@router.get("", response_model=list[RecommendationResponse])
async def list_recommendations(
    agent: AgentType | None = Query(default=None),
    status_filter: RecommendationStatus | None = Query(default=None, alias="status"),
    sort: str = Query(default="impact", pattern="^(impact|date|confidence)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RecommendationResponse]:
    svc = RecommendationService(db, user.organization_id)
    return await svc.list_recommendations(
        agent=agent, status_filter=status_filter, sort=sort
    )


@router.get("/savings", response_model=SavingsSummary)
async def savings_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavingsSummary:
    return await RecommendationService(db, user.organization_id).savings_summary()


@router.patch("/{rec_id}/status", response_model=RecommendationResponse)
async def update_status(
    rec_id: uuid.UUID,
    payload: RecommendationStatusUpdate,
    user: User = Depends(require_permission("recommendations.write")),
    db: AsyncSession = Depends(get_db),
) -> RecommendationResponse:
    svc = RecommendationService(db, user.organization_id)
    return await svc.update_status(rec_id, payload, user.id)
