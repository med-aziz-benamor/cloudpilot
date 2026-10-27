"""Agent base contract and shared run bookkeeping."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.core import cache
from cloudpilot.models.agent_run_log import AgentRunLog, AgentRunStatus
from cloudpilot.models.recommendation import AgentType


class AgentBase(ABC):
    """Abstract base for all CloudPilot AI agents.

    Two execution tracks:
    * ``run`` — scheduled batch execution (writes recommendations to the DB).
    * ``trigger`` — on-demand execution with a custom payload (e.g. chat).
    """

    name: str
    description: str
    agent_type: AgentType

    @abstractmethod
    async def run(self, organization_id: uuid.UUID, db: AsyncSession) -> int:
        """Scheduled execution. Returns the number of recommendations created."""

    async def trigger(
        self, organization_id: uuid.UUID, db: AsyncSession, payload: dict[str, Any]
    ) -> Any:
        """On-demand execution. Default raises; agents override as needed."""
        raise NotImplementedError(f"{self.name} does not support on-demand triggering.")

    async def run_with_logging(
        self, organization_id: uuid.UUID, db: AsyncSession
    ) -> int:
        """Wrap :meth:`run` with an ``agent_run_logs`` entry for observability."""
        log = AgentRunLog(
            agent=self.agent_type,
            organization_id=organization_id,
            started_at=datetime.now(UTC),
            status=AgentRunStatus.RUNNING,
        )
        db.add(log)
        await db.flush()
        try:
            count = await self.run(organization_id, db)
            log.status = AgentRunStatus.SUCCESS
            log.recommendations_created = count
            log.finished_at = datetime.now(UTC)
            await db.flush()
            if count:
                # New recommendations change the dashboard's pending count and
                # potential-savings total.
                await cache.invalidate_org(organization_id)
            logger.info(
                "agent.run.success agent={} org={} created={}",
                self.name,
                organization_id,
                count,
            )
            return count
        except Exception as exc:
            log.status = AgentRunStatus.FAILED
            log.error_message = str(exc)
            log.finished_at = datetime.now(UTC)
            await db.flush()
            logger.exception("agent.run.failed agent={} org={}", self.name, organization_id)
            raise
