"""AWS adapter — resource inventory, Cost Explorer, CloudWatch via boto3 (read-only).

In **demo mode** the adapter serves the shared fleet simulation: synthetic usage
priced from the AWS Price List. See :mod:`cloudpilot.cloud.simulated`.

In **live mode** EC2 enumeration is real (assume-role via STS with an external id).
Billing and metrics are *not yet implemented* and raise rather than quietly returning
simulated figures — presenting invented costs as a real AWS bill would have the agents
raise anomalies against spend that never happened.
"""

from __future__ import annotations

import asyncio
from datetime import date

from loguru import logger

from cloudpilot.cloud.base import (
    BillingEntryDTO,
    CloudProviderAdapter,
    MetricSampleDTO,
    ResourceDTO,
)
from cloudpilot.cloud.simulated import (
    simulated_billing,
    simulated_metrics,
    simulated_resources,
)
from cloudpilot.models.cloud_account import CloudProvider

_AWS_REGIONS = ["eu-west-1", "us-east-1"]


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
            return simulated_resources("aws")

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
            return simulated_billing("aws", start, end)
        raise NotImplementedError(
            "Live AWS billing is not implemented. Wire the Cost Explorer "
            "get_cost_and_usage() call here. Until then, set DEMO_MODE=true."
        )

    async def get_metrics(
        self, provider_resource_id: str, metric: str, days: int
    ) -> list[MetricSampleDTO]:
        if self.demo_mode:
            return simulated_metrics("aws", provider_resource_id, metric, days)
        raise NotImplementedError(
            "Live AWS metrics are not implemented. Wire CloudWatch get_metric_statistics() "
            "here; simulated utilization must not drive rightsizing advice on real instances."
        )
