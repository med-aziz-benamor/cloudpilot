"""Admin endpoints — audit log viewer, agent runs, manual agent triggers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.ai.cost_agent import CostAgent
from cloudpilot.ai.forecast_agent import ForecastAgent
from cloudpilot.ai.rightsizing_agent import RightSizingAgent
from cloudpilot.api.deps import get_db, require_permission
from cloudpilot.core.audit import verify_chain
from cloudpilot.models.agent_run_log import AgentRunLog
from cloudpilot.models.audit_log import AuditLog
from cloudpilot.models.recommendation import AgentType
from cloudpilot.models.user import User

router = APIRouter()

_AGENTS = {
    AgentType.COST: CostAgent(),
    AgentType.RIGHTSIZING: RightSizingAgent(),
    AgentType.FORECAST: ForecastAgent(),
}


class AuditEntry(BaseModel):
    id: str
    event_type: str
    actor_user_id: str | None
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    created_at: str

    model_config = {"from_attributes": True}


class AgentRunEntry(BaseModel):
    id: str
    agent: AgentType
    status: str
    recommendations_created: int
    started_at: str
    finished_at: str | None

    model_config = {"from_attributes": True}


@router.get("/audit-log", response_model=list[AuditEntry])
async def audit_log(
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(require_permission("audit.read")),
    db: AsyncSession = Depends(get_db),
) -> list[AuditEntry]:
    rows = (
        await db.execute(
            select(AuditLog)
            .where(AuditLog.organization_id == user.organization_id)
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
        )
    ).scalars().all()
    return [
        AuditEntry(
            id=str(r.id),
            event_type=r.event_type,
            actor_user_id=str(r.actor_user_id) if r.actor_user_id else None,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            ip_address=str(r.ip_address) if r.ip_address else None,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.get("/audit-log/verify")
async def verify_audit(
    user: User = Depends(require_permission("audit.read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Recompute the audit hash chain and report integrity."""
    ok = await verify_chain(db, user.organization_id)
    return {"intact": ok}


@router.get("/agent-runs", response_model=list[AgentRunEntry])
async def agent_runs(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(require_permission("audit.read")),
    db: AsyncSession = Depends(get_db),
) -> list[AgentRunEntry]:
    rows = (
        await db.execute(
            select(AgentRunLog)
            .where(AgentRunLog.organization_id == user.organization_id)
            .order_by(desc(AgentRunLog.started_at))
            .limit(limit)
        )
    ).scalars().all()
    return [
        AgentRunEntry(
            id=str(r.id),
            agent=r.agent,
            status=r.status.value,
            recommendations_created=r.recommendations_created,
            started_at=r.started_at.isoformat(),
            finished_at=r.finished_at.isoformat() if r.finished_at else None,
        )
        for r in rows
    ]


@router.post("/agents/{agent}/run")
async def trigger_agent(
    agent: AgentType,
    user: User = Depends(require_permission("agents.trigger")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Manually run a scheduled agent for the caller's organization."""
    runner = _AGENTS.get(agent)
    if runner is None:
        return {"created": 0, "message": f"{agent.value} is on-demand only."}
    created = await runner.run_with_logging(user.organization_id, db)
    return {"created": created, "agent": agent.value}
