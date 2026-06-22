"""Chat service — Cloud Advisor sessions and messages backed by ArchitectAgent."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.ai.architect_agent import ArchitectAgent
from cloudpilot.models.chat_message import ChatMessage, MessageRole
from cloudpilot.models.chat_session import ChatSession
from cloudpilot.schemas.chat import (
    ChatMessageResponse,
    ChatSessionDetailResponse,
    ChatSessionResponse,
)

_architect = ArchitectAgent()


class ChatService:
    def __init__(
        self, db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        self.db = db
        self.org_id = organization_id
        self.user_id = user_id

    async def list_sessions(self) -> list[ChatSessionResponse]:
        rows = (
            await self.db.execute(
                select(ChatSession)
                .where(
                    ChatSession.user_id == self.user_id,
                    ChatSession.is_archived.is_(False),
                )
                .order_by(ChatSession.created_at.desc())
            )
        ).scalars().all()
        out: list[ChatSessionResponse] = []
        for s in rows:
            count = (
                await self.db.execute(
                    select(func.count(ChatMessage.id)).where(
                        ChatMessage.session_id == s.id
                    )
                )
            ).scalar_one()
            out.append(
                ChatSessionResponse(
                    id=s.id,
                    title=s.title,
                    is_archived=s.is_archived,
                    created_at=s.created_at,
                    message_count=int(count),
                )
            )
        return out

    async def create_session(self, title: str) -> ChatSession:
        session = ChatSession(
            organization_id=self.org_id, user_id=self.user_id, title=title
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def get_session_detail(
        self, session_id: uuid.UUID
    ) -> ChatSessionDetailResponse:
        session = await self._owned_session(session_id)
        messages = (
            await self.db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session.id)
                .order_by(ChatMessage.created_at)
            )
        ).scalars().all()
        return ChatSessionDetailResponse(
            id=session.id,
            title=session.title,
            is_archived=session.is_archived,
            created_at=session.created_at,
            message_count=len(messages),
            messages=[ChatMessageResponse.model_validate(m) for m in messages],
        )

    async def delete_session(self, session_id: uuid.UUID) -> None:
        session = await self._owned_session(session_id)
        await self.db.delete(session)
        await self.db.flush()

    async def send_message(
        self, session_id: uuid.UUID, content: str
    ) -> ChatMessageResponse:
        session = await self._owned_session(session_id)

        user_msg = ChatMessage(
            session_id=session.id, role=MessageRole.USER, content=content
        )
        self.db.add(user_msg)
        await self.db.flush()

        # Build short history for context (last 6 messages).
        history_rows = (
            await self.db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session.id)
                .order_by(ChatMessage.created_at.desc())
                .limit(6)
            )
        ).scalars().all()
        history = [
            {"role": m.role.value, "content": m.content}
            for m in reversed(history_rows)
            if m.role != MessageRole.SYSTEM
        ][:-1]  # exclude the just-added user message (re-added by the agent prompt)

        result = await _architect.trigger(
            self.org_id, self.db, {"question": content, "history": history}
        )

        assistant_msg = ChatMessage(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content=result["content"],
            citations_json=result.get("citations") or None,
            tool_calls_json=result.get("tool_calls") or None,
        )
        self.db.add(assistant_msg)

        # Auto-title the session from the first user message.
        if session.title == "New Conversation":
            session.title = content[:60]

        await self.db.flush()
        return ChatMessageResponse.model_validate(assistant_msg)

    async def _owned_session(self, session_id: uuid.UUID) -> ChatSession:
        session = await self.db.get(ChatSession, session_id)
        if (
            session is None
            or session.user_id != self.user_id
            or session.organization_id != self.org_id
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found.")
        return session
