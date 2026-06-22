"""Cloud Advisor chat schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from cloudpilot.models.chat_message import MessageRole
from cloudpilot.schemas.common import APISchema, ResponseSchema


class Citation(ResponseSchema):
    source: str
    section: str | None = None
    url: str | None = None


class ToolCall(ResponseSchema):
    tool: str
    args: dict
    result: dict | None = None


class ChatMessageResponse(ResponseSchema):
    id: uuid.UUID
    role: MessageRole
    content: str
    citations: list[Citation] = Field(default_factory=list, alias="citations_json")
    tool_calls: list[ToolCall] = Field(default_factory=list, alias="tool_calls_json")
    tokens_used: int | None = None
    created_at: datetime


class ChatSessionResponse(ResponseSchema):
    id: uuid.UUID
    title: str
    is_archived: bool
    created_at: datetime
    message_count: int = 0


class ChatSessionDetailResponse(ChatSessionResponse):
    messages: list[ChatMessageResponse] = []


class SendMessageRequest(APISchema):
    content: str = Field(min_length=1, max_length=4000)


class CreateSessionRequest(APISchema):
    title: str = Field(default="New Conversation", max_length=255)
    first_message: str | None = Field(default=None, max_length=4000)
