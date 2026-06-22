"""Cloud provider integration layer (read-only adapters)."""

from cloudpilot.cloud.base import (
    BillingEntryDTO,
    CloudProviderAdapter,
    MetricSampleDTO,
    ResourceDTO,
    get_adapter,
)

__all__ = [
    "BillingEntryDTO",
    "CloudProviderAdapter",
    "MetricSampleDTO",
    "ResourceDTO",
    "get_adapter",
]
