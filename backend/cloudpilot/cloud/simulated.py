"""The simulated data source shared by all three provider adapters.

Before this existed, each adapter carried its own ``_mock_*`` generators, and they
disagreed with the seeder *and* with each other: the seeder created ``vm-analytics-01``
while the Azure adapter invented ``virtual-machine-00``, and billing was a flat
``rng.uniform(120, 380)`` per service per day. A sync after a seed therefore replaced
a coherent estate with unrelated noise.

Now every path — seeder and adapter sync alike — reads the same fleet from
:mod:`cloudpilot.simulation` and prices it from the same published rate card, so a
sync is idempotent against a seed: the natural keys line up and the numbers agree.
"""

from __future__ import annotations

from datetime import date, timedelta

from cloudpilot.cloud.base import BillingEntryDTO, MetricSampleDTO, ResourceDTO
from cloudpilot.simulation import daily_cost, fleet_for, metric_samples
from cloudpilot.simulation.fleet import FleetResource


#: The natural key both the seeder and the adapters use for a simulated resource.
def resource_id_for(resource: FleetResource) -> str:
    return f"{resource.provider}://acme/{resource.name}"


#: Service label as it appears on the bill (mirrors the seeder's mapping).
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


def service_label(service: str) -> str:
    return _SERVICE_LABELS.get(service, service.replace("_", " ").title())


def simulated_resources(provider: str) -> list[ResourceDTO]:
    """The provider's slice of the simulated fleet, as adapter DTOs."""
    return [
        ResourceDTO(
            provider_resource_id=resource_id_for(r),
            name=r.name,
            service=r.service,
            region=r.region,
            sku=r.sku,
            node_count=int(r.quantity) if r.sku else 1,
            tags={
                "env": "dev" if r.profile.value == "dev" else "prod",
                "owner": "acme",
                "profile": r.profile.value,
            },
        )
        for r in fleet_for(provider)
    ]


def simulated_billing(provider: str, start: date, end: date) -> list[BillingEntryDTO]:
    """Daily billing for a provider over ``[start, end]``, priced from the rate card.

    A resource that did not run on a given day (a dev box at the weekend) yields no
    row, matching how providers actually bill.
    """
    today = date.today()
    out: list[BillingEntryDTO] = []
    for resource in fleet_for(provider):
        label = service_label(resource.service)
        day = start
        while day <= end:
            cost = daily_cost(resource, day, today)
            if cost > 0:
                out.append(
                    BillingEntryDTO(
                        usage_date=day,
                        service=label,
                        cost_usd=round(cost, 4),
                        raw_amount=round(cost, 4),
                        provider_resource_id=resource_id_for(resource),
                    )
                )
            day += timedelta(days=1)
    return out


def simulated_metrics(
    provider: str, provider_resource_id: str, metric: str, days: int
) -> list[MetricSampleDTO]:
    """CPU/RAM samples for one simulated resource."""
    today = date.today()
    match = next(
        (r for r in fleet_for(provider) if resource_id_for(r) == provider_resource_id),
        None,
    )
    if match is None:
        return []
    return [
        MetricSampleDTO(metric_name=name, timestamp=ts, value=value, unit=unit)
        for name, ts, value, unit in metric_samples(match, today, days=days)
        if name == metric
    ]
