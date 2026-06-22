"""Agent orchestrator — APScheduler process that runs the scheduled agents.

Cadence (from the AI spec):
* CostAgent          — every 60 minutes
* RightSizingAgent   — daily at 02:00 UTC
* ForecastAgent      — daily at 03:00 UTC

Run as a standalone process: ``python -m cloudpilot.ai.orchestrator``.
The API never invokes scheduled agents inline; it only reads their persisted output.
"""

from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from sqlalchemy import select

from cloudpilot.ai.cost_agent import CostAgent
from cloudpilot.ai.forecast_agent import ForecastAgent
from cloudpilot.ai.rightsizing_agent import RightSizingAgent
from cloudpilot.cloud.sync_scheduler import run_all_syncs
from cloudpilot.database import AsyncSessionLocal
from cloudpilot.models.organization import Organization

_cost_agent = CostAgent()
_rightsizing_agent = RightSizingAgent()
_forecast_agent = ForecastAgent()


async def _run_for_all_orgs(agent) -> None:
    """Execute an agent for every organization in its own transaction."""
    async with AsyncSessionLocal() as db:
        org_ids = (await db.execute(select(Organization.id))).scalars().all()
    for org_id in org_ids:
        async with AsyncSessionLocal() as db:
            try:
                await agent.run_with_logging(org_id, db)
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("Agent {} failed for org {}", agent.name, org_id)


async def run_cost_agent() -> None:
    logger.info("Scheduler: running CostAgent")
    await _run_for_all_orgs(_cost_agent)


async def run_rightsizing_agent() -> None:
    logger.info("Scheduler: running RightSizingAgent")
    await _run_for_all_orgs(_rightsizing_agent)


async def run_forecast_agent() -> None:
    logger.info("Scheduler: running ForecastAgent")
    await _run_for_all_orgs(_forecast_agent)


async def run_cloud_sync() -> None:
    logger.info("Scheduler: running cloud sync")
    await run_all_syncs()


def build_scheduler() -> AsyncIOScheduler:
    """Construct and configure the APScheduler instance with all agent jobs."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_cost_agent, IntervalTrigger(minutes=60), id="cost_agent", replace_existing=True
    )
    scheduler.add_job(
        run_rightsizing_agent,
        CronTrigger(hour=2, minute=0),
        id="rightsizing_agent",
        replace_existing=True,
    )
    scheduler.add_job(
        run_forecast_agent,
        CronTrigger(hour=3, minute=0),
        id="forecast_agent",
        replace_existing=True,
    )
    scheduler.add_job(
        run_cloud_sync,
        IntervalTrigger(hours=1),
        id="cloud_sync",
        replace_existing=True,
    )
    return scheduler


async def main() -> None:
    """Entry point for the standalone scheduler process."""
    logger.info("Starting CloudPilot agent orchestrator")
    scheduler = build_scheduler()
    scheduler.start()
    # Kick off one immediate pass so the demo has fresh output quickly.
    await run_cost_agent()
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):  # pragma: no cover
        logger.info("Stopping orchestrator")
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
