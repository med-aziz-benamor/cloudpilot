"""Resource endpoints — list, explorer tree, detail."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.api.deps import get_current_user, get_db
from cloudpilot.models.user import User
from cloudpilot.schemas.resource import (
    ResourceDetailResponse,
    ResourceResponse,
    ResourceTreeNode,
)
from cloudpilot.services.resource_service import ResourceService

router = APIRouter()


@router.get("", response_model=list[ResourceResponse])
async def list_resources(
    provider: str | None = Query(default=None),
    service: str | None = Query(default=None),
    region: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ResourceResponse]:
    svc = ResourceService(db, user.organization_id)
    return await svc.list_resources(provider=provider, service=service, region=region)


@router.get("/tree", response_model=list[ResourceTreeNode])
async def resource_tree(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ResourceTreeNode]:
    svc = ResourceService(db, user.organization_id)
    return await svc.build_tree()


@router.get("/{resource_id}", response_model=ResourceDetailResponse)
async def resource_detail(
    resource_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResourceDetailResponse:
    svc = ResourceService(db, user.organization_id)
    return await svc.get_detail(resource_id)
