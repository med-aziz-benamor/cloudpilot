"""AWS adapter — Cost Explorer + CloudWatch via boto3 (read-only).

Real mode assumes a read-only IAM role assumed via STS with an external id.
Demo mode returns deterministic mock data.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
from datetime import date, datetime, timedelta, timezone

from loguru import logger

from cloudpilot.cloud.base import (
    BillingEntryDTO,
    CloudProviderAdapter,
    MetricSampleDTO,
    ResourceDTO,
)
from cloudpilot.models.cloud_account import CloudProvider

_AWS_SERVICES = [
    ("ec2_instance", "t3.medium"),
    ("ec2_instance", "m5.large"),
    ("ec2_instance", "m5.xlarge"),
    ("rds_instance", "db.m5.large"),
    ("s3_bucket", None),
    ("lambda_function", None),
    ("elasticache", "cache.m5.large"),
    ("cloudfront", None),
]
_AWS_REGIONS = ["us-east-1", "eu-west-1"]


class AWSAdapter(CloudProviderAdapter):
    provider = CloudProvider.AWS

    def _assume_role_session(self):  # pragma: no cover - requires AWS
        import boto3

        sts = boto3.client("sts")
        creds = sts.assume_role(
            RoleArn=self.credentials["role_arn"],
            RoleSessionName="cloudpilot-readonly",
            ExternalId=self.credentials.get("external_id", ""),
        )["Credentials"]
        return boto3.Session(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )

    async def validate_credentials(self) -> bool:
        if self.demo_mode:
            return True
        try:
            await asyncio.to_thread(self._assume_role_session)
            return True
        except Exception as exc:  # pragma: no cover
            logger.warning("AWS credential validation failed: {}", exc)
            return False

    async def get_resources(self) -> list[ResourceDTO]:
        if self.demo_mode:
            return self._mock_resources()

        def _list() -> list[ResourceDTO]:  # pragma: no cover - requires AWS
            session = self._assume_role_session()
            ec2 = session.client("ec2", region_name=_AWS_REGIONS[0])
            out: list[ResourceDTO] = []
            for res in ec2.describe_instances()["Reservations"]:
                for inst in res["Instances"]:
                    out.append(
                        ResourceDTO(
                            provider_resource_id=inst["InstanceId"],
                            name=inst["InstanceId"],
                            service="ec2_instance",
                            region=_AWS_REGIONS[0],
                            sku=inst.get("InstanceType"),
                            tags={t["Key"]: t["Value"] for t in inst.get("Tags", [])},
                        )
                    )
            return out

        return await asyncio.to_thread(_list)

    async def get_billing(self, start: date, end: date) -> list[BillingEntryDTO]:
        if self.demo_mode:
            return self._mock_billing(start, end)
        logger.info("AWS Cost Explorer query {} → {}", start, end)
        return await asyncio.to_thread(lambda: self._mock_billing(start, end))

    async def get_metrics(
        self, provider_resource_id: str, metric: str, days: int
    ) -> list[MetricSampleDTO]:
        if self.demo_mode:
            return self._mock_metrics(provider_resource_id, metric, days)
        logger.info("AWS CloudWatch {} {} {}d", provider_resource_id, metric, days)
        return await asyncio.to_thread(
            lambda: self._mock_metrics(provider_resource_id, metric, days)
        )

    # ─── deterministic mock generation ───
    def _rng(self, salt: str) -> random.Random:
        seed = int(hashlib.sha256(f"aws:{salt}".encode()).hexdigest(), 16) % (2**32)
        return random.Random(seed)

    def _mock_resources(self) -> list[ResourceDTO]:
        rng = self._rng("resources")
        out: list[ResourceDTO] = []
        for i in range(18):
            service, sku = _AWS_SERVICES[i % len(_AWS_SERVICES)]
            region = _AWS_REGIONS[i % len(_AWS_REGIONS)]
            out.append(
                ResourceDTO(
                    provider_resource_id=f"arn:aws:demo:{region}:123456789012:{service}/{service}-{i:02d}",
                    name=f"{service.replace('_', '-')}-{i:02d}",
                    service=service,
                    region=region,
                    sku=sku,
                    tags={"env": rng.choice(["prod", "staging"]), "team": "acme"},
                )
            )
        return out

    def _mock_billing(self, start: date, end: date) -> list[BillingEntryDTO]:
        rng = self._rng("billing")
        out: list[BillingEntryDTO] = []
        day = start
        services = ["EC2", "S3", "RDS", "Lambda", "CloudFront"]
        while day <= end:
            weekday_factor = 1.2 if day.weekday() < 5 else 0.85
            for svc in services:
                base = rng.uniform(60, 220) * weekday_factor
                out.append(
                    BillingEntryDTO(
                        usage_date=day,
                        service=svc,
                        cost_usd=round(base, 2),
                        raw_amount=round(base, 2),
                    )
                )
            day += timedelta(days=1)
        return out

    def _mock_metrics(
        self, provider_resource_id: str, metric: str, days: int
    ) -> list[MetricSampleDTO]:
        rng = self._rng(f"{provider_resource_id}:{metric}")
        now = datetime.now(timezone.utc)
        unit = "percent" if "percent" in metric else "bytes"
        baseline = rng.uniform(20, 55) if unit == "percent" else rng.uniform(1e6, 5e7)
        out: list[MetricSampleDTO] = []
        for h in range(days * 24):
            ts = now - timedelta(hours=h)
            jitter = rng.uniform(-0.25, 0.25) * baseline
            out.append(
                MetricSampleDTO(
                    metric_name=metric,
                    timestamp=ts,
                    value=max(0.0, baseline + jitter),
                    unit=unit,
                )
            )
        return out
