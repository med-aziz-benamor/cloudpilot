"""Rich demo-data seeder.

Creates the full "Acme Corp" demo tenant so the platform is immediately interactive
with no cloud credentials:

* 1 organization (Acme Corp, pro plan)
* 1 admin user (demo@cloudpilot.dev / demo1234)
* 3 cloud accounts (Azure, AWS, GCP)
* 50 resources across the three providers
* 90 days of billing entries with weekday peaks, weekend dips, a growth trend,
  and two deliberate anomalies for the CostAgent to catch
* 14 days of CPU/RAM metrics per sized resource (with rightsizing candidates)
* 8 pre-generated recommendations (cost / rightsizing / forecast / architect)
* 3 chat sessions with realistic Q&A history
* A forecast snapshot projecting a July budget overrun

Run with:  python -m cloudpilot.utils.mock_data
Idempotent: re-running drops and recreates the demo organization.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from loguru import logger
from sqlalchemy import delete, select

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
from cloudpilot.models.forecast_snapshot import ForecastSnapshot
from cloudpilot.models.metric_sample import MetricSample
from cloudpilot.models.organization import Organization, OrgPlan
from cloudpilot.models.recommendation import (
    AgentType,
    Recommendation,
    RecommendationStatus,
)
from cloudpilot.models.resource import Resource
from cloudpilot.models.user import User, UserRole

RNG = random.Random(2026)

DEMO_EMAIL = "demo@cloudpilot.dev"
DEMO_PASSWORD = "demo1234"

# Resource blueprints: (service, sku, base_monthly_cost, is_rightsizing_candidate)
AZURE_RESOURCES = [
    ("virtual_machine", "Standard_D4s_v3", 280, True),   # analytics 01
    ("virtual_machine", "Standard_D4s_v3", 280, True),   # analytics 02
    ("virtual_machine", "Standard_D4s_v3", 280, True),   # analytics 03
    ("virtual_machine", "Standard_D2s_v3", 140, False),
    ("virtual_machine", "Standard_D2s_v3", 140, False),
    ("virtual_machine", "Standard_D8s_v3", 560, False),
    ("virtual_machine", "Standard_D2s_v3", 140, False),
    ("virtual_machine", "Standard_D4s_v3", 280, False),
    ("aks_cluster", "Standard_D4s_v3", 820, False),      # aks-prod
    ("aks_cluster", "Standard_D2s_v3", 410, False),      # aks-staging
    ("aks_cluster", "Standard_D2s_v3", 380, False),      # aks-dev
    ("aks_cluster", "Standard_D4s_v3", 600, False),      # aks-analytics
    ("azure_sql", "GP_Gen5_4", 540, False),
    ("azure_sql", "GP_Gen5_4", 520, False),
    ("azure_sql", "GP_Gen5_4", 500, False),
    ("blob_storage", None, 120, False),
    ("blob_storage", None, 95, False),
    ("blob_storage", None, 80, False),
    ("blob_storage", None, 110, False),
    ("app_service", "P1v3", 105, False),
    ("app_service", "P1v3", 105, False),
    ("redis_cache", "C1", 40, False),
]
AWS_RESOURCES = [
    ("ec2_instance", "t3.medium", 30, False),
    ("ec2_instance", "m5.large", 70, False),
    ("ec2_instance", "m5.xlarge", 140, True),            # worker 01
    ("ec2_instance", "m5.xlarge", 140, True),            # worker 02
    ("ec2_instance", "m5.large", 70, False),
    ("ec2_instance", "t3.medium", 30, False),
    ("rds_instance", "db.m5.large", 125, False),         # db.production (anomaly)
    ("rds_instance", "db.m5.large", 120, False),
    ("rds_instance", "db.m5.large", 118, False),
    ("rds_instance", "db.m5.large", 122, False),
    ("s3_bucket", None, 60, False),
    ("s3_bucket", None, 45, False),
    ("s3_bucket", None, 52, False),
    ("lambda_function", None, 18, False),
    ("lambda_function", None, 12, False),
    ("elasticache", "cache.m5.large", 110, False),
    ("elasticache", "cache.m5.large", 105, False),
    ("cloudfront", None, 35, False),
]
GCP_RESOURCES = [
    ("compute_engine", "n2-standard-4", 140, False),
    ("compute_engine", "n2-standard-4", 135, False),     # burst VM (rejected rec)
    ("compute_engine", "n2-standard-2", 70, False),
    ("compute_engine", "n2-standard-2", 68, False),
    ("cloud_storage", None, 55, False),
    ("cloud_storage", None, 48, False),
    ("cloud_storage", None, 40, False),
    ("cloud_sql", "db-n1-standard-2", 95, False),
    ("cloud_sql", "db-n1-standard-2", 92, False),
    ("gke_cluster", "n2-standard-4", 280, False),
]


async def _reset_existing(db) -> None:
    existing = (
        await db.execute(select(Organization).where(Organization.name == "Acme Corp"))
    ).scalars().all()
    for org in existing:
        # Audit log is not FK-bound; clear it explicitly.
        await db.execute(delete_audit(org.id))
        await db.delete(org)
    await db.flush()


def delete_audit(org_id: uuid.UUID):
    from cloudpilot.models.audit_log import AuditLog

    return delete(AuditLog).where(AuditLog.organization_id == org_id)


def _provider_resources(provider: CloudProvider):
    return {
        CloudProvider.AZURE: AZURE_RESOURCES,
        CloudProvider.AWS: AWS_RESOURCES,
        CloudProvider.GCP: GCP_RESOURCES,
    }[provider]


def _resource_name(provider: CloudProvider, service: str, idx: int) -> str:
    if provider == CloudProvider.AZURE and service == "virtual_machine" and idx < 3:
        return f"vm-analytics-{idx + 1:02d}"
    if provider == CloudProvider.AZURE and service == "aks_cluster":
        names = ["aks-prod-cluster", "aks-staging", "aks-dev", "aks-analytics"]
        return names[idx % len(names)]
    if provider == CloudProvider.AWS and service == "ec2_instance" and idx in (2, 3):
        return f"ec2-worker-{idx - 1:02d}"
    if provider == CloudProvider.AWS and service == "rds_instance" and idx == 0:
        return "rds-production"
    short = service.replace("_", "-")
    return f"{short}-{idx + 1:02d}"


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        logger.info("Seeding CloudPilot demo data…")
        await _reset_existing(db)

        org = Organization(name="Acme Corp", plan=OrgPlan.PRO)
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
        resource_index = await _seed_resources(db, accounts)
        await _seed_billing(db, accounts, resource_index)
        await _seed_metrics(db, resource_index)
        await _seed_recommendations(db, org.id, accounts, resource_index)
        await _seed_chat(db, org.id, user.id)
        await _seed_forecast(db, org.id)

        await write_audit(
            db,
            organization_id=org.id,
            actor_user_id=user.id,
            event_type="demo.seeded",
            payload={"resources": len(resource_index)},
        )

        await db.commit()
        logger.success(
            "Demo data ready — login: {} / {}", DEMO_EMAIL, DEMO_PASSWORD
        )


async def _seed_accounts(db, org_id: uuid.UUID) -> dict[CloudProvider, CloudAccount]:
    now = datetime.now(timezone.utc)
    blueprint = [
        (CloudProvider.AZURE, "Acme Azure Subscription",
         "11111111-2222-3333-4444-555555555555", 2),
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
            credentials_enc=encrypt_credential({"demo": True}),
            status=CloudAccountStatus.ACTIVE,
            last_synced_at=now - timedelta(minutes=mins_ago),
        )
        db.add(acc)
        accounts[provider] = acc
    await db.flush()
    return accounts


async def _seed_resources(
    db, accounts: dict[CloudProvider, CloudAccount]
) -> dict[str, tuple[Resource, float, bool]]:
    """Returns name → (resource, base_monthly_cost, is_rightsizing_candidate)."""
    index: dict[str, tuple[Resource, float, bool]] = {}
    region_by_provider = {
        CloudProvider.AZURE: ["eastus", "westeurope", "northeurope"],
        CloudProvider.AWS: ["us-east-1", "eu-west-1"],
        CloudProvider.GCP: ["us-central1", "europe-west1"],
    }
    now = datetime.now(timezone.utc)
    for provider, account in accounts.items():
        regions = region_by_provider[provider]
        for i, (service, sku, base_cost, rightsize) in enumerate(
            _provider_resources(provider)
        ):
            name = _resource_name(provider, service, i)
            res = Resource(
                cloud_account_id=account.id,
                provider_resource_id=f"{provider.value}://acme/{name}",
                name=name,
                service=service,
                region=regions[i % len(regions)],
                sku=sku,
                tags_json={"env": "prod" if i % 2 == 0 else "staging", "owner": "acme"},
                is_active=True,
                last_seen_at=now,
            )
            db.add(res)
            index[name] = (res, float(base_cost), rightsize)
    await db.flush()
    return index


async def _seed_billing(
    db,
    accounts: dict[CloudProvider, CloudAccount],
    resource_index: dict[str, tuple[Resource, float, bool]],
) -> None:
    today = date.today()
    start = today - timedelta(days=89)

    # Map resources to their account + per-day base cost.
    res_by_account: dict[uuid.UUID, list[tuple[Resource, float]]] = {}
    for res, base_cost, _ in resource_index.values():
        res_by_account.setdefault(res.cloud_account_id, []).append(
            (res, base_cost / 30.0)
        )

    # Identify anomaly targets.
    aks_prod = resource_index["aks-prod-cluster"][0]
    rds_prod = resource_index["rds-production"][0]
    anomaly1_start = today - timedelta(days=45)  # Azure compute +340% for 3 days
    anomaly2_start = today - timedelta(days=12)  # AWS RDS +180% for 2 days

    day = start
    while day <= today:
        day_offset = (day - start).days
        growth = 1.0 + 0.08 * (day_offset / 89.0)  # 8% growth across window
        weekday_factor = 1.2 if day.weekday() < 5 else 0.85
        month_end_factor = 1.15 if day.day >= 27 else 1.0
        daily_factor = growth * weekday_factor * month_end_factor

        for account in accounts.values():
            for res, daily_base in res_by_account.get(account.id, []):
                cost = daily_base * daily_factor * RNG.uniform(0.92, 1.08)

                # Inject anomalies.
                if res.id == aks_prod.id and anomaly1_start <= day < anomaly1_start + timedelta(days=3):
                    cost *= 4.4  # +340%
                if res.id == rds_prod.id and anomaly2_start <= day < anomaly2_start + timedelta(days=2):
                    cost *= 2.8  # +180%

                service_label = _billing_service_label(account.provider, res.service)
                db.add(
                    BillingEntry(
                        cloud_account_id=account.id,
                        resource_id=res.id,
                        usage_date=day,
                        service=service_label,
                        cost_usd=Decimal(str(round(cost, 4))),
                        raw_currency="USD",
                        raw_amount=Decimal(str(round(cost, 4))),
                    )
                )
        day += timedelta(days=1)
    await db.flush()


def _billing_service_label(provider: CloudProvider, service: str) -> str:
    mapping = {
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
    return mapping.get(service, service.title())


async def _seed_metrics(
    db, resource_index: dict[str, tuple[Resource, float, bool]]
) -> None:
    now = datetime.now(timezone.utc)
    for res, _, rightsize in resource_index.values():
        if not res.sku:
            continue
        # Rightsizing candidates run cold; others run healthy.
        cpu_base = RNG.uniform(14, 28) if rightsize else RNG.uniform(45, 70)
        mem_base = RNG.uniform(25, 38) if rightsize else RNG.uniform(50, 72)
        for h in range(14 * 24):
            ts = now - timedelta(hours=h)
            db.add(
                MetricSample(
                    resource_id=res.id,
                    metric_name="cpu_percent",
                    timestamp=ts,
                    value=max(1.0, cpu_base + RNG.uniform(-8, 8)),
                    unit="percent",
                )
            )
            db.add(
                MetricSample(
                    resource_id=res.id,
                    metric_name="memory_percent",
                    timestamp=ts,
                    value=max(1.0, mem_base + RNG.uniform(-10, 10)),
                    unit="percent",
                )
            )
        await db.flush()


async def _seed_recommendations(
    db,
    org_id: uuid.UUID,
    accounts: dict[CloudProvider, CloudAccount],
    resource_index: dict[str, tuple[Resource, float, bool]],
) -> None:
    azure = accounts[CloudProvider.AZURE]
    aws = accounts[CloudProvider.AWS]
    gcp = accounts[CloudProvider.GCP]

    def rid(name: str) -> uuid.UUID:
        return resource_index[name][0].id

    recs = [
        # CostAgent (3)
        Recommendation(
            organization_id=org_id, cloud_account_id=azure.id, agent=AgentType.COST,
            title="Unusual spend on Azure Compute — East US",
            description="AKS cluster aks-prod-cluster exceeded its 30-day baseline by 342%.",
            estimated_saving_usd=Decimal("2400.00"), confidence=0.91,
            status=RecommendationStatus.PENDING,
            affected_resource_ids=[rid("aks-prod-cluster")],
            metadata_json={"service": "Kubernetes", "provider": "azure",
                           "expected_cost": 645, "actual_cost": 2847,
                           "delta_usd": 2202, "z_score": 3.2,
                           "anomaly_date": (date.today() - timedelta(days=45)).isoformat()},
        ),
        Recommendation(
            organization_id=org_id, cloud_account_id=aws.id, agent=AgentType.COST,
            title="Anomalous RDS billing increase — us-east-1",
            description="RDS rds-production showed a 180% cost increase over 2 days.",
            estimated_saving_usd=Decimal("890.00"), confidence=0.78,
            status=RecommendationStatus.PENDING,
            affected_resource_ids=[rid("rds-production")],
            metadata_json={"service": "RDS", "provider": "aws",
                           "expected_cost": 495, "actual_cost": 1386,
                           "delta_usd": 891, "z_score": 2.4,
                           "anomaly_date": (date.today() - timedelta(days=12)).isoformat()},
        ),
        Recommendation(
            organization_id=org_id, cloud_account_id=azure.id, agent=AgentType.COST,
            title="Monthly storage cost spike in Azure Blob — West Europe",
            description="Blob storage growth exceeded the expected trend; already reviewed.",
            estimated_saving_usd=Decimal("340.00"), confidence=0.85,
            status=RecommendationStatus.ACCEPTED,
            metadata_json={"service": "Storage", "provider": "azure"},
        ),
        # RightSizingAgent (3)
        Recommendation(
            organization_id=org_id, cloud_account_id=azure.id, agent=AgentType.RIGHTSIZING,
            title="3 underutilized Azure VMs in East US",
            description="Standard_D4s_v3 running at P95 CPU 18%, P95 RAM 31%. "
                        "Recommend downsizing to Standard_D2s_v3.",
            estimated_saving_usd=Decimal("485.00"), confidence=0.88,
            status=RecommendationStatus.PENDING,
            affected_resource_ids=[rid("vm-analytics-01"), rid("vm-analytics-02"),
                                   rid("vm-analytics-03")],
            metadata_json={"current_sku": "Standard_D4s_v3", "target_sku": "Standard_D2s_v3",
                           "p95_cpu": 18, "p95_mem": 31},
        ),
        Recommendation(
            organization_id=org_id, cloud_account_id=aws.id, agent=AgentType.RIGHTSIZING,
            title="2 oversized EC2 instances — m5.xlarge → m5.large",
            description="Two workers run consistently below 35% CPU. Downsize one tier.",
            estimated_saving_usd=Decimal("210.00"), confidence=0.82,
            status=RecommendationStatus.PENDING,
            affected_resource_ids=[rid("ec2-worker-01"), rid("ec2-worker-02")],
            metadata_json={"current_sku": "m5.xlarge", "target_sku": "m5.large",
                           "p95_cpu": 24, "p95_mem": 33},
        ),
        Recommendation(
            organization_id=org_id, cloud_account_id=gcp.id, agent=AgentType.RIGHTSIZING,
            title="GCP VM downsize candidate — n2-standard-4",
            description="Flagged as a downsize candidate but rejected: handles burst traffic.",
            estimated_saving_usd=Decimal("120.00"), confidence=0.74,
            status=RecommendationStatus.REJECTED,
            affected_resource_ids=[rid("compute-engine-02")],
            metadata_json={"current_sku": "n2-standard-4", "target_sku": "n2-standard-2"},
        ),
        # ForecastAgent (1)
        Recommendation(
            organization_id=org_id, agent=AgentType.FORECAST,
            title="Projected budget overrun for July 2026",
            description="At current burn rate, July spend projects to $51,200 "
                        "(14% over the $45,000 budget).",
            estimated_saving_usd=None, confidence=0.87,
            status=RecommendationStatus.PENDING,
            metadata_json={"current_mtd": 23400, "projected_month_end": 51200,
                           "budget": 45000, "overrun_pct": 14},
        ),
        # ArchitectAgent (1)
        Recommendation(
            organization_id=org_id, cloud_account_id=azure.id, agent=AgentType.ARCHITECT,
            title="AKS cluster node pool sizing review",
            description="aks-prod-cluster runs at avg 28% CPU, 41% RAM over 7 days. "
                        "Standard_D4s_v3 x3 → Standard_D2s_v3 x3 recommended.",
            estimated_saving_usd=Decimal("340.00"), confidence=0.79,
            status=RecommendationStatus.PENDING,
            affected_resource_ids=[rid("aks-prod-cluster")],
            metadata_json={"citations": ["Azure Monitor metrics", "AKS Best Practices §4.2"]},
        ),
    ]
    db.add_all(recs)
    await db.flush()


async def _seed_chat(db, org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    sessions = [
        (
            "AKS Optimization",
            "Is my Azure AKS cluster correctly sized?",
            "Based on the last 7 days, aks-prod-cluster (Standard_D4s_v3 x 3) runs at "
            "average 28% CPU and 41% RAM. This indicates over-provisioning. Recommended "
            "action: downsize to Standard_D2s_v3 x 3 — estimated saving of $340/month. [1][2]",
            [{"source": "Azure Monitor · aks-prod-cluster", "section": None, "url": None},
             {"source": "AKS Best Practices Guide", "section": "§4.2", "url": None}],
        ),
        (
            "Cost Anomaly Investigation",
            "Why did my Azure costs spike 2 weeks ago?",
            "The spike was traced to aks-prod-cluster in East US. Azure Compute spent "
            "$2,847 that day versus a 30-day baseline of $645 — a 342% increase. The root "
            "cause appears to be a node pool autoscaler event that provisioned 8 additional "
            "nodes. It has since resolved; a recommendation is pending to review autoscaler "
            "max settings. [1]",
            [{"source": "CostAgent · anomaly detection", "section": None, "url": None}],
        ),
        (
            "Budget Forecast",
            "Will I stay within my July budget of $45,000?",
            "Based on the ForecastAgent's Prophet model trained on 90 days of data, July "
            "2026 is projected to reach $51,200 (80% CI: $48,900–$53,500) — 14% above your "
            "$45,000 budget. Primary driver: 8% MoM growth compounded by the AKS node pool "
            "issue. Accepting the rightsizing recommendations could bring the projection to "
            "approximately $47,800. [1]",
            [{"source": "ForecastAgent · Prophet model", "section": None, "url": None}],
        ),
    ]
    base = datetime.now(timezone.utc) - timedelta(days=3)
    for i, (title, q, a, citations) in enumerate(sessions):
        session = ChatSession(
            organization_id=org_id, user_id=user_id, title=title,
            created_at=base + timedelta(hours=i * 6),
        )
        db.add(session)
        await db.flush()
        db.add(ChatMessage(session_id=session.id, role=MessageRole.USER, content=q))
        db.add(
            ChatMessage(
                session_id=session.id, role=MessageRole.ASSISTANT, content=a,
                citations_json=citations, tokens_used=RNG.randint(180, 320),
            )
        )
    await db.flush()


async def _seed_forecast(db, org_id: uuid.UUID) -> None:
    today = date.today()
    for horizon in (30, 60, 90):
        dates, yhat, lower, upper, trend = [], [], [], [], []
        base = 1550.0  # ~$46.5k/month daily
        for d in range(horizon):
            day = today + timedelta(days=d + 1)
            growth = base * (1 + 0.0026 * d)
            weekend = 0.86 if day.weekday() >= 5 else 1.12
            val = growth * weekend
            dates.append(day.isoformat())
            yhat.append(round(val, 2))
            lower.append(round(val * 0.94, 2))
            upper.append(round(val * 1.06, 2))
            trend.append(round(growth, 2))
        db.add(
            ForecastSnapshot(
                organization_id=org_id,
                snapshot_date=today,
                horizon_days=horizon,
                forecast_json={
                    "dates": dates, "yhat": yhat, "yhat_lower": lower,
                    "yhat_upper": upper, "trend": trend,
                },
            )
        )
    await db.flush()


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
