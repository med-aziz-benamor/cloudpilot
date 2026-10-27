"""Recommendation service — listing, filtering, status transitions, savings summary."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.core import cache
from cloudpilot.core.audit import write_audit
from cloudpilot.models.recommendation import (
    AgentType,
    Recommendation,
    RecommendationStatus,
)
from cloudpilot.models.resource import Resource
from cloudpilot.schemas.recommendation import (
    RecommendationResponse,
    RecommendationStatusUpdate,
    SavingsSummary,
)


class RecommendationService:
    def __init__(self, db: AsyncSession, organization_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = organization_id

    async def list_recommendations(
        self,
        agent: AgentType | None = None,
        status_filter: RecommendationStatus | None = None,
        sort: str = "impact",
    ) -> list[RecommendationResponse]:
        stmt = select(Recommendation).where(
            Recommendation.organization_id == self.org_id
        )
        if agent:
            stmt = stmt.where(Recommendation.agent == agent)
        if status_filter:
            stmt = stmt.where(Recommendation.status == status_filter)

        if sort == "impact":
            stmt = stmt.order_by(Recommendation.estimated_saving_usd.desc().nullslast())
        elif sort == "confidence":
            stmt = stmt.order_by(Recommendation.confidence.desc())
        else:
            stmt = stmt.order_by(Recommendation.created_at.desc())

        recs = (await self.db.execute(stmt)).scalars().all()
        return [await self._to_response(r) for r in recs]

    async def get(self, rec_id: uuid.UUID) -> Recommendation:
        rec = await self.db.get(Recommendation, rec_id)
        if rec is None or rec.organization_id != self.org_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")
        return rec

    async def update_status(
        self,
        rec_id: uuid.UUID,
        payload: RecommendationStatusUpdate,
        actor_user_id: uuid.UUID,
    ) -> RecommendationResponse:
        rec = await self.get(rec_id)
        rec.status = payload.status
        if payload.status == RecommendationStatus.SNOOZED:
            hours = payload.snooze_hours or 24
            rec.snoozed_until = datetime.now(UTC) + timedelta(hours=hours)
        else:
            rec.snoozed_until = None
        await self.db.flush()
        await write_audit(
            self.db,
            organization_id=self.org_id,
            actor_user_id=actor_user_id,
            event_type=f"recommendation.{payload.status.value}",
            resource_type="recommendation",
            resource_id=str(rec.id),
        )
        # The dashboard summary counts pending recommendations and sums their
        # savings, so actioning one makes the cached figures wrong immediately.
        # Waiting out the TTL would leave the KPI row visibly disagreeing with
        # the action the user just took.
        await cache.invalidate_org(self.org_id)
        return await self._to_response(rec)

    async def savings_summary(self) -> SavingsSummary:
        rows = (
            await self.db.execute(
                select(
                    Recommendation.status,
                    func.count(Recommendation.id),
                    func.coalesce(func.sum(Recommendation.estimated_saving_usd), 0),
                )
                .where(Recommendation.organization_id == self.org_id)
                .group_by(Recommendation.status)
            )
        ).all()
        by_status = {s: (c, float(total)) for s, c, total in rows}
        pending = by_status.get(RecommendationStatus.PENDING, (0, 0.0))
        accepted = by_status.get(RecommendationStatus.ACCEPTED, (0, 0.0))
        rejected = by_status.get(RecommendationStatus.REJECTED, (0, 0.0))
        snoozed = by_status.get(RecommendationStatus.SNOOZED, (0, 0.0))
        return SavingsSummary(
            total_potential_usd=round(pending[1], 2),
            accepted_usd=round(accepted[1], 2),
            pending_count=pending[0],
            accepted_count=accepted[0],
            rejected_count=rejected[0],
            snoozed_count=snoozed[0],
        )

    async def _to_response(self, rec: Recommendation) -> RecommendationResponse:
        names: list[str] = []
        for rid in rec.affected_resource_ids or []:
            resource = await self.db.get(Resource, rid)
            if resource:
                names.append(resource.name)
        return RecommendationResponse(
            id=rec.id,
            agent=rec.agent,
            title=rec.title,
            description=rec.description,
            estimated_saving_usd=(
                float(rec.estimated_saving_usd)
                if rec.estimated_saving_usd is not None
                else None
            ),
            confidence=rec.confidence,
            status=rec.status,
            snoozed_until=rec.snoozed_until,
            affected_resource_ids=list(rec.affected_resource_ids or []),
            affected_resource_names=names,
            metadata_json=rec.metadata_json or {},
            created_at=rec.created_at,
        )
