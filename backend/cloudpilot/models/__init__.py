"""ORM models. Importing this package registers every model on ``Base.metadata``."""

from cloudpilot.models.agent_run_log import AgentRunLog, AgentRunStatus
from cloudpilot.models.audit_log import AuditLog
from cloudpilot.models.billing_entry import BillingEntry
from cloudpilot.models.chat_message import ChatMessage, MessageRole
from cloudpilot.models.chat_session import ChatSession
from cloudpilot.models.cloud_account import CloudAccount, CloudAccountStatus, CloudProvider
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

__all__ = [
    "AgentRunLog",
    "AgentRunStatus",
    "AgentType",
    "AuditLog",
    "BillingEntry",
    "ChatMessage",
    "ChatSession",
    "CloudAccount",
    "CloudAccountStatus",
    "CloudProvider",
    "ForecastSnapshot",
    "MessageRole",
    "MetricSample",
    "Organization",
    "OrgPlan",
    "Recommendation",
    "RecommendationStatus",
    "Resource",
    "User",
    "UserRole",
]
