"""The simulated Acme Corp fleet.

This is the *physical* description of the demo estate: what runs, how much of it,
and how it behaves. Crucially it carries **no prices** — a resource declares that
it is four ``Standard_D4s_v3`` nodes, and the cost engine derives the bill from the
published rate card. That separation is the whole point: usage is simulated, price
is real, so every dollar CloudPilot reports traces back to a provider's rate card.

Each resource has a :class:`UsageProfile`, which drives both its utilization curve
and its billable hours. The profiles are chosen so the fleet contains the things the
agents are supposed to find:

* ``OVERSIZED``  — low P95 CPU/RAM. RightSizingAgent should flag these.
* ``BURSTY``     — low mean but high P95. RightSizingAgent should *not* flag these;
                   they exist to catch false positives.
* ``DEV``        — idle nights and weekends. The scheduling-savings story.
* ``STEADY``     — healthy production baseline.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class UsageProfile(enum.StrEnum):
    """How a resource behaves over a day and a week."""

    STEADY = "steady"
    OVERSIZED = "oversized"
    BURSTY = "bursty"
    DEV = "dev"
    #: Storage and other quantity-billed resources that simply accumulate.
    STORAGE = "storage"


@dataclass(frozen=True, slots=True)
class FleetResource:
    """One simulated resource.

    ``quantity`` is the physical amount billed: node count for compute (an AKS pool
    of 4 nodes bills 4x the VM rate) and gigabytes for storage. ``price_sku`` is the
    key into the pricing catalog, kept separate from ``sku`` because storage has no
    user-visible SKU but still needs a rate to price against.
    """

    name: str
    provider: str
    service: str
    region: str
    sku: str | None
    price_sku: str
    quantity: float
    profile: UsageProfile
    #: Fractional monthly growth across the 90-day window (storage mostly).
    growth: float = 0.0
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def is_rightsizing_candidate(self) -> bool:
        return self.profile is UsageProfile.OVERSIZED


def _vm(
    name: str,
    provider: str,
    service: str,
    region: str,
    sku: str,
    nodes: float,
    profile: UsageProfile,
    **kw: object,
) -> FleetResource:
    return FleetResource(
        name=name,
        provider=provider,
        service=service,
        region=region,
        sku=sku,
        price_sku=sku,
        quantity=nodes,
        profile=profile,
        **kw,  # type: ignore[arg-type]
    )


def _storage(
    name: str, provider: str, service: str, region: str, price_sku: str, gb: float, growth: float
) -> FleetResource:
    return FleetResource(
        name=name,
        provider=provider,
        service=service,
        region=region,
        sku=None,
        price_sku=price_sku,
        quantity=gb,
        profile=UsageProfile.STORAGE,
        growth=growth,
    )


# ─────────────────────────────────────────────────────────────
# Azure — 22 resources
# ─────────────────────────────────────────────────────────────
AZURE_FLEET: list[FleetResource] = [
    # Three analytics VMs that were sized for a workload that never materialised.
    _vm(
        "vm-analytics-01",
        "azure",
        "virtual_machine",
        "westeurope",
        "Standard_D4s_v3",
        1,
        UsageProfile.OVERSIZED,
    ),
    _vm(
        "vm-analytics-02",
        "azure",
        "virtual_machine",
        "westeurope",
        "Standard_D4s_v3",
        1,
        UsageProfile.OVERSIZED,
    ),
    _vm(
        "vm-analytics-03",
        "azure",
        "virtual_machine",
        "northeurope",
        "Standard_D4s_v3",
        1,
        UsageProfile.OVERSIZED,
    ),
    _vm(
        "vm-api-01",
        "azure",
        "virtual_machine",
        "westeurope",
        "Standard_D2s_v3",
        1,
        UsageProfile.STEADY,
    ),
    _vm(
        "vm-api-02",
        "azure",
        "virtual_machine",
        "westeurope",
        "Standard_D2s_v3",
        1,
        UsageProfile.STEADY,
    ),
    _vm(
        "vm-batch-01",
        "azure",
        "virtual_machine",
        "northeurope",
        "Standard_D8s_v3",
        1,
        UsageProfile.BURSTY,
    ),
    _vm(
        "vm-dev-01",
        "azure",
        "virtual_machine",
        "westeurope",
        "Standard_D2s_v3",
        1,
        UsageProfile.DEV,
    ),
    _vm(
        "vm-jenkins-01",
        "azure",
        "virtual_machine",
        "westeurope",
        "Standard_D4s_v3",
        1,
        UsageProfile.DEV,
    ),
    # AKS node pools. quantity = node count, so the autoscaler event is physical.
    _vm(
        "aks-prod-cluster",
        "azure",
        "aks_cluster",
        "westeurope",
        "Standard_D4s_v3",
        4,
        UsageProfile.STEADY,
    ),
    _vm(
        "aks-staging", "azure", "aks_cluster", "westeurope", "Standard_D2s_v3", 3, UsageProfile.DEV
    ),
    _vm("aks-dev", "azure", "aks_cluster", "northeurope", "Standard_D2s_v3", 2, UsageProfile.DEV),
    _vm(
        "aks-analytics",
        "azure",
        "aks_cluster",
        "westeurope",
        "Standard_D4s_v3",
        3,
        UsageProfile.OVERSIZED,
    ),
    _vm("sql-orders", "azure", "azure_sql", "westeurope", "GP_Gen5_4", 1, UsageProfile.STEADY),
    _vm("sql-billing", "azure", "azure_sql", "westeurope", "GP_Gen5_4", 1, UsageProfile.STEADY),
    _vm(
        "sql-reporting", "azure", "azure_sql", "northeurope", "GP_Gen5_4", 1, UsageProfile.OVERSIZED
    ),
    _storage("blob-archive-01", "azure", "blob_storage", "westeurope", "blob_hot_lrs", 6_200, 0.06),
    _storage("blob-media-01", "azure", "blob_storage", "westeurope", "blob_hot_lrs", 4_800, 0.04),
    _storage(
        "blob-backups-01", "azure", "blob_storage", "northeurope", "blob_hot_lrs", 4_100, 0.09
    ),
    _storage("blob-logs-01", "azure", "blob_storage", "westeurope", "blob_hot_lrs", 5_600, 0.14),
    _vm("app-web-01", "azure", "app_service", "westeurope", "P1v3", 2, UsageProfile.STEADY),
    _vm("app-admin-01", "azure", "app_service", "westeurope", "P1v3", 1, UsageProfile.DEV),
    _vm("redis-session-01", "azure", "redis_cache", "westeurope", "C1", 1, UsageProfile.STEADY),
]

# ─────────────────────────────────────────────────────────────
# AWS — 18 resources
# ─────────────────────────────────────────────────────────────
AWS_FLEET: list[FleetResource] = [
    _vm("ec2-bastion-01", "aws", "ec2_instance", "eu-west-1", "t3.medium", 1, UsageProfile.STEADY),
    _vm("ec2-api-01", "aws", "ec2_instance", "eu-west-1", "m5.large", 1, UsageProfile.STEADY),
    _vm(
        "ec2-worker-01", "aws", "ec2_instance", "eu-west-1", "m5.xlarge", 1, UsageProfile.OVERSIZED
    ),
    _vm(
        "ec2-worker-02", "aws", "ec2_instance", "eu-west-1", "m5.xlarge", 1, UsageProfile.OVERSIZED
    ),
    _vm("ec2-api-02", "aws", "ec2_instance", "eu-west-1", "m5.large", 1, UsageProfile.STEADY),
    _vm("ec2-ci-01", "aws", "ec2_instance", "eu-west-1", "t3.medium", 1, UsageProfile.DEV),
    # rds-production carries the second anomaly (a Multi-AZ failover).
    _vm(
        "rds-production", "aws", "rds_instance", "eu-west-1", "db.m5.large", 1, UsageProfile.STEADY
    ),
    _vm(
        "rds-analytics",
        "aws",
        "rds_instance",
        "eu-west-1",
        "db.m5.xlarge",
        1,
        UsageProfile.OVERSIZED,
    ),
    _vm("rds-staging", "aws", "rds_instance", "eu-west-1", "db.m5.large", 1, UsageProfile.DEV),
    _vm(
        "rds-archive", "aws", "rds_instance", "eu-west-1", "db.m5.xlarge", 1, UsageProfile.OVERSIZED
    ),
    _storage("s3-assets-01", "aws", "s3_bucket", "eu-west-1", "s3_standard", 2_400, 0.05),
    _storage("s3-datalake-01", "aws", "s3_bucket", "eu-west-1", "s3_standard", 3_900, 0.11),
    _storage("s3-backups-01", "aws", "s3_bucket", "eu-west-1", "s3_standard", 2_100, 0.07),
    _storage("s3-logs-01", "aws", "s3_bucket", "eu-west-1", "s3_standard", 1_500, 0.18),
    _vm(
        "elasticache-01",
        "aws",
        "elasticache",
        "eu-west-1",
        "cache.m5.large",
        1,
        UsageProfile.STEADY,
    ),
    _vm(
        "elasticache-02",
        "aws",
        "elasticache",
        "eu-west-1",
        "cache.m5.xlarge",
        1,
        UsageProfile.OVERSIZED,
    ),
    _storage("cloudfront-cdn", "aws", "cloudfront", "eu-west-1", "s3_standard", 900, 0.03),
    _storage("lambda-artifacts", "aws", "lambda_function", "eu-west-1", "s3_standard", 300, 0.02),
]

# ─────────────────────────────────────────────────────────────
# GCP — 10 resources
# ─────────────────────────────────────────────────────────────
GCP_FLEET: list[FleetResource] = [
    _vm(
        "gce-etl-01",
        "gcp",
        "compute_engine",
        "europe-west1",
        "n2-standard-4",
        1,
        UsageProfile.STEADY,
    ),
    _vm(
        "gce-etl-02",
        "gcp",
        "compute_engine",
        "europe-west1",
        "n2-standard-4",
        1,
        UsageProfile.BURSTY,
    ),
    _vm(
        "gce-api-01",
        "gcp",
        "compute_engine",
        "europe-west1",
        "n2-standard-2",
        1,
        UsageProfile.STEADY,
    ),
    _vm(
        "gce-dev-01", "gcp", "compute_engine", "europe-west1", "n2-standard-2", 1, UsageProfile.DEV
    ),
    _storage(
        "gcs-datalake-01", "gcp", "cloud_storage", "europe-west1", "gcs_standard", 3_100, 0.09
    ),
    _storage("gcs-exports-01", "gcp", "cloud_storage", "europe-west1", "gcs_standard", 2_200, 0.05),
    _storage("gcs-archive-01", "gcp", "cloud_storage", "europe-west1", "gcs_standard", 1_800, 0.03),
    _vm(
        "sql-analytics-01",
        "gcp",
        "cloud_sql",
        "europe-west1",
        "db-n1-standard-2",
        1,
        UsageProfile.STEADY,
    ),
    _vm(
        "sql-events-01",
        "gcp",
        "cloud_sql",
        "europe-west1",
        "db-n1-standard-2",
        1,
        UsageProfile.OVERSIZED,
    ),
    _vm(
        "gke-analytics",
        "gcp",
        "gke_cluster",
        "europe-west1",
        "n2-standard-4",
        4,
        UsageProfile.STEADY,
    ),
]

FLEET: list[FleetResource] = [*AZURE_FLEET, *AWS_FLEET, *GCP_FLEET]


def fleet_for(provider: str) -> list[FleetResource]:
    """Return the simulated resources belonging to one provider."""
    return [r for r in FLEET if r.provider == provider]


def by_name(name: str) -> FleetResource:
    """Look up one fleet resource by name."""
    for resource in FLEET:
        if resource.name == name:
            return resource
    raise KeyError(name)
