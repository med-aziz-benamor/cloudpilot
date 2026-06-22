"""Cloud Advisor chat endpoints — sessions and messages."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.api.deps import client_ip, get_db, require_permission
from cloudpilot.core import rate_limit
from cloudpilot.models.user import User
from cloudpilot.schemas.chat import (
    ChatMessageResponse,
    ChatSessionDetailResponse,
    ChatSessionResponse,
    CreateSessionRequest,
    SendMessageRequest,
)
from cloudpilot.schemas.common import MessageResponse
from cloudpilot.services.chat_service import ChatService

router = APIRouter()


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(
    user: User = Depends(require_permission("chat.use")),
    db: AsyncSession = Depends(get_db),
) -> list[ChatSessionResponse]:
    return await ChatService(db, user.organization_id, user.id).list_sessions()


@router.post(
    "/sessions",
    response_model=ChatSessionDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    payload: CreateSessionRequest,
    user: User = Depends(require_permission("chat.use")),
    db: AsyncSession = Depends(get_db),
) -> ChatSessionDetailResponse:
    svc = ChatService(db, user.organization_id, user.id)
    session = await svc.create_session(payload.title)
    if payload.first_message:
        await svc.send_message(session.id, payload.first_message)
    return await svc.get_session_detail(session.id)


@router.get("/sessions/{session_id}", response_model=ChatSessionDetailResponse)
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(require_permission("chat.use")),
    db: AsyncSession = Depends(get_db),
) -> ChatSessionDetailResponse:
    return await ChatService(db, user.organization_id, user.id).get_session_detail(
        session_id
    )


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(require_permission("chat.use")),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await ChatService(db, user.organization_id, user.id).delete_session(session_id)
    return MessageResponse(message="Session deleted.")


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
async def send_message(
    session_id: uuid.UUID,
    payload: SendMessageRequest,
    request: Request,
    user: User = Depends(require_permission("chat.use")),
    db: AsyncSession = Depends(get_db),
) -> ChatMessageResponse:
    # Chat is rate-limited to 100 req/min per user.
    await rate_limit.check_rate_limit(f"chat:{user.id}", 100, 60)
    svc = ChatService(db, user.organization_id, user.id)
    return await svc.send_message(session_id, payload.content)
