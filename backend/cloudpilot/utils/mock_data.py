"""Demo-data seeder — builds the "Acme Corp" tenant from the fleet simulation.

What is simulated and what is real matters here:

* **Simulated** — the estate. Which resources exist, how many nodes they run, how
  busy they are, and the two operational incidents that hit the bill.
* **Real** — every price. Billing rows are ``published_rate x simulated_usage``,
  priced from the snapshot in :mod:`cloudpilot.pricing` (Azure Retail Prices API,
  AWS Price List). No dollar figure in this file is typed by hand.
* **Computed** — the recommendations. Rather than seeding invented findings, the
  seeder runs the actual CostAgent, RightSizingAgent and ForecastAgent against the
  seeded estate. What the demo shows is genuinely what the agents found, and the
  agent run logs on the admin page are real runs.

Run with:  python -m cloudpilot.utils.mock_data
Idempotent: re-running drops and recreates the demo organization.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from loguru import logger
from sqlalchemy import delete, select

from cloudpilot.ai.cost_agent import CostAgent
from cloudpilot.ai.forecast_agent import ForecastAgent
from cloudpilot.ai.rightsizing_agent import RightSizingAgent
from cloudpilot.core.audit import write_audit
from cloudpilot.core.security import encrypt_credential, hash_password
from cloudpilot.database import AsyncSessionLocal
from cloudpilot.models.billing_entry import BillingEntry
from cloudpilot.models.chat_message import ChatMessage, MessageRole
from cloudpilot.models.chat_session import ChatSession
from cloudpilot.models.cloud_account import (
    CloudAccount,
    CloudAccountStatus,
    CloudProvider,
)
from cloudpilot.models.metric_sample import MetricSample
from cloudpilot.models.organization import Organization, OrgPlan
from cloudpilot.models.resource import Resource
from cloudpilot.models.user import User, UserRole
from cloudpilot.pricing import get_catalog
from cloudpilot.simulation import (
    HISTORY_DAYS,
    FleetResource,
    daily_costs,
    engine,
    fleet_for,
    metric_samples,
)

DEMO_EMAIL = "demo@cloudpilot.dev"
DEMO_PASSWORD = "demo1234"

_PROVIDERS: dict[str, CloudProvider] = {
    "azure": CloudProvider.AZURE,
    "aws": CloudProvider.AWS,
    "gcp": CloudProvider.GCP,
}

#: How a resource's service maps to the service label that appears on a bill. The
#: CostAgent groups anomalies by this label, so it is what the user sees.
_SERVICE_LABELS: dict[str, str] = {
    "virtual_machine": "Compute",
    "aks_cluster": "Kubernetes",
    "azure_sql": "Database",
    "blob_storage": "Storage",
    "app_service": "App Service",
    "redis_cache": "Cache",
    "ec2_instance": "EC2",
    "rds_instance": "RDS",
    "s3_bucket": "S3",
    "lambda_function": "Lambda",
    "elasticache": "ElastiCache",
    "cloudfront": "CloudFront",
    "compute_engine": "Compute Engine",
    "cloud_storage": "Cloud Storage",
    "cloud_sql": "Cloud SQL",
    "gke_cluster": "GKE",
}


def _service_label(service: str) -> str:
    return _SERVICE_LABELS.get(service, service.replace("_", " ").title())


async def _reset_existing(db) -> None:
    existing = (
        (await db.execute(select(Organization).where(Organization.name == "Acme Corp")))
        .scalars()
        .all()
    )
    for org in existing:
        # The audit log is not FK-bound to the org; clear it explicitly.
        from cloudpilot.models.audit_log import AuditLog

        await db.execute(delete(AuditLog).where(AuditLog.organization_id == org.id))
        await db.delete(org)
    await db.flush()


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        catalog = get_catalog()
        logger.info(
            "Seeding CloudPilot demo data (pricing: {} SKUs, {:.0f}% API-verified, "
            "as of {:%Y-%m-%d})",
            len(catalog),
            catalog.meta.api_verified_pct,
            catalog.meta.generated_at,
        )
        await _reset_existing(db)

        # Acme's estate runs a little over $8k/month, so a $7,500 budget puts them
        # genuinely — and narrowly — over. The budget is a business input; the overrun
        # it produces is still derived entirely from the priced estate.
        org = Organization(
            name="Acme Corp", plan=OrgPlan.PRO, monthly_budget_usd=Decimal("7500.00")
        )
        db.add(org)
        await db.flush()

        user = User(
            organization_id=org.id,
            email=DEMO_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD),
            full_name="Aziz Ben Amor",
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(user)
        await db.flush()

        accounts = await _seed_accounts(db, org.id)
        resources = await _seed_resources(db, accounts)
        total = await _seed_billing(db, accounts, resources)
        await _seed_metrics(db, resources)
        await _run_agents(db, org.id)
        await _seed_chat(db, org.id, user.id)

        await write_audit(
            db,
            organization_id=org.id,
            actor_user_id=user.id,
            event_type="demo.seeded",
            payload={
                "resources": len(resources),
                "billed_usd": round(total, 2),
                "pricing_as_of": catalog.meta.generated_at.date().isoformat(),
            },
        )

        await db.commit()
        logger.success(
            "Demo data ready — {} resources, ${:,.0f} billed across {} days. Login: {} / {}",
            len(resources),
            total,
            HISTORY_DAYS,
            DEMO_EMAIL,
            DEMO_PASSWORD,
        )


async def _seed_accounts(db, org_id: uuid.UUID) -> dict[CloudProvider, CloudAccount]:
    now = datetime.now(UTC)
    blueprint = [
        (CloudProvider.AZURE, "Acme Azure Subscription", "11111111-2222-3333-4444-555555555555", 2),
        (CloudProvider.AWS, "Acme AWS Production", "123456789012", 5),
        (CloudProvider.GCP, "Acme GCP Analytics", "acme-analytics-prod", 3),
    ]
    accounts: dict[CloudProvider, CloudAccount] = {}
    for provider, name, ident, mins_ago in blueprint:
        acc = CloudAccount(
            organization_id=org_id,
            provider=provider,
            account_identifier=ident,
            display_name=name,
            credentials_enc=encrypt_credential({"simulated": True}),
            status=CloudAccountStatus.ACTIVE,
            last_synced_at=now - timedelta(minutes=mins_ago),
        )
        db.add(acc)
        accounts[provider] = acc
    await db.flush()
    return accounts


async def _seed_resources(
    db, accounts: dict[CloudProvider, CloudAccount]
) -> dict[str, tuple[Resource, FleetResource]]:
    """Materialise the simulated fleet as Resource rows."""
    index: dict[str, tuple[Resource, FleetResource]] = {}
    now = datetime.now(UTC)
    for provider_key, provider in _PROVIDERS.items():
        account = accounts[provider]
        for sim in fleet_for(provider_key):
            res = Resource(
                organization_id=account.organization_id,
                cloud_account_id=account.id,
                provider_resource_id=f"{provider_key}://acme/{sim.name}",
                name=sim.name,
                service=sim.service,
                region=sim.region,
                sku=sim.sku,
                # A node pool bills its node count; storage bills GB, not instances.
                node_count=int(sim.quantity) if sim.sku else 1,
                tags_json={
                    "env": "dev" if sim.profile.value == "dev" else "prod",
                    "owner": "acme",
                    "profile": sim.profile.value,
                },
                is_active=True,
                last_seen_at=now,
            )
            db.add(res)
            index[sim.name] = (res, sim)
    await db.flush()
    return index


async def _seed_billing(
    db,
    accounts: dict[CloudProvider, CloudAccount],
    resources: dict[str, tuple[Resource, FleetResource]],
) -> float:
    """Write 90 days of billing, priced from the published rate card.

    A day on which a resource did not run (dev machines at the weekend) produces no
    billing row at all, which is how the providers actually bill — and it is what
    gives the weekday/weekend shape in the cost charts.
    """
    today = date.today()
    total = 0.0
    for res, sim in resources.values():
        account = accounts[_PROVIDERS[sim.provider]]
        label = _service_label(sim.service)
        for day, cost in daily_costs(sim, today, days=HISTORY_DAYS):
            if cost <= 0:
                continue
            total += cost
            db.add(
                BillingEntry(
                    organization_id=account.organization_id,
                    cloud_account_id=account.id,
                    resource_id=res.id,
                    usage_date=day,
                    service=label,
                    cost_usd=Decimal(str(round(cost, 4))),
                    raw_currency="USD",
                    raw_amount=Decimal(str(round(cost, 4))),
                )
            )
    await db.flush()
    logger.info("Seeded billing: ${:,.2f} across {} days", total, HISTORY_DAYS)
    return total


async def _seed_metrics(db, resources: dict[str, tuple[Resource, FleetResource]]) -> None:
    today = date.today()
    count = 0
    for res, sim in resources.values():
        for metric_name, ts, value, unit in metric_samples(sim, today):
            db.add(
                MetricSample(
                    resource_id=res.id,
                    metric_name=metric_name,
                    timestamp=ts,
                    value=value,
                    unit=unit,
                )
            )
            count += 1
        await db.flush()
    logger.info("Seeded {} metric samples", count)


async def _run_agents(db, org_id: uuid.UUID) -> None:
    """Run the real agents over the seeded estate.

    This is what fills the recommendations page. Nothing here is a canned finding:
    if RightSizingAgent flags ``vm-analytics-01``, it is because the P95 of its
    seeded metrics genuinely sits below the threshold, and the saving it quotes is
    the real delta between two published rates.
    """
    for agent in (CostAgent(), RightSizingAgent(), ForecastAgent()):
        # Each agent runs inside a savepoint. A failure (Prophet is heavy and can be
        # absent) must roll back only that agent's work — rolling back the outer
        # transaction would discard the entire seeded estate along with it.
        try:
            async with db.begin_nested():
                created = await agent.run_with_logging(org_id, db)
            logger.info("{} produced {} recommendations", agent.name, created)
        except Exception as exc:  # pragma: no cover - Prophet is optional locally
            logger.warning("{} failed during seed, continuing: {}", agent.name, exc)
    await db.flush()


async def _seed_chat(db, org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Seed chat history whose figures are computed from the simulated estate.

    The answers quote the same numbers the rest of the platform would, because they
    are derived from the same engine rather than transcribed.
    """
    today = date.today()
    aks = engine.events_for("aks-prod-cluster")[0]
    aks_res = next(r for r in fleet_for("azure") if r.name == "aks-prod-cluster")
    spike_day = today - timedelta(days=aks.days_ago)
    spike_cost = engine.daily_cost(aks_res, spike_day, today)
    normal_cost = engine.daily_cost(aks_res, today - timedelta(days=1), today)
    uplift = (spike_cost - normal_cost) / normal_cost * 100 if normal_cost else 0.0
    nodes = int(aks_res.quantity)
    scaled = int(aks_res.quantity * aks.quantity_factor)

    sessions = [
        (
            "AKS Optimization",
            "Is my Azure AKS cluster correctly sized?",
            f"aks-prod-cluster runs {nodes} x {aks_res.sku} nodes and holds a P95 CPU "
            f"near 70%, so it is sized about right. The cluster to look at is "
            f"aks-analytics, which sits well under the utilization thresholds and is a "
            f"genuine downsize candidate — see the pending rightsizing recommendation "
            f"for the exact saving, which is computed from the published Azure rate "
            f"card. [1][2]",
            [
                {"source": "Azure Monitor · aks-prod-cluster", "section": None, "url": None},
                {"source": "AKS Best Practices Guide", "section": "§4.2", "url": None},
            ],
        ),
        (
            "Cost Anomaly Investigation",
            "Why did my Azure costs spike last month?",
            f"On {spike_day.isoformat()}, aks-prod-cluster cost ${spike_cost:,.0f} for the "
            f"day against a normal ${normal_cost:,.0f} — about {uplift:.0f}% higher. "
            f"{aks.cause} The cluster ran {scaled} nodes instead of {nodes} for "
            f"{aks.duration_days} days. The extra cost is simply "
            f"{scaled - nodes} additional {aks_res.sku} nodes at the West Europe "
            f"on-demand rate. [1]",
            [{"source": "CostAgent · anomaly detection", "section": None, "url": None}],
        ),
        (
            "Budget Forecast",
            "What is driving my cloud spend?",
            "The largest line items are Kubernetes and Database compute. The clearest "
            "savings available are the underutilized resources the RightSizingAgent has "
            "flagged, plus the dev and staging machines that currently bill 12 hours a "
            "day on weekdays — switching those off out of hours is the cheapest win. "
            "Every figure quoted is derived from the provider's published rate card. [1]",
            [{"source": "ForecastAgent · Prophet model", "section": None, "url": None}],
        ),
    ]
    base = datetime.now(UTC) - timedelta(days=3)
    for i, (title, question, answer, citations) in enumerate(sessions):
        session = ChatSession(
            organization_id=org_id,
            user_id=user_id,
            title=title,
            created_at=base + timedelta(hours=i * 6),
        )
        db.add(session)
        await db.flush()
        db.add(ChatMessage(session_id=session.id, role=MessageRole.USER, content=question))
        db.add(
            ChatMessage(
                session_id=session.id,
                role=MessageRole.ASSISTANT,
                content=answer,
                citations_json=citations,
            )
        )
    await db.flush()


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
