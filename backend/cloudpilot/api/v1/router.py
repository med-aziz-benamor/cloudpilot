"""Master v1 router — mounts every feature router under /api/v1."""

from __future__ import annotations

from fastapi import APIRouter

from cloudpilot.api.v1 import (
    admin,
    auth,
    chat,
    cloud_accounts,
    costs,
    forecast,
    pricing,
    recommendations,
    resources,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    cloud_accounts.router, prefix="/cloud-accounts", tags=["cloud-accounts"]
)
api_router.include_router(resources.router, prefix="/resources", tags=["resources"])
api_router.include_router(costs.router, prefix="/costs", tags=["costs"])
api_router.include_router(
    recommendations.router, prefix="/recommendations", tags=["recommendations"]
)
api_router.include_router(forecast.router, prefix="/forecast", tags=["forecast"])
api_router.include_router(pricing.router, prefix="/pricing", tags=["pricing"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
