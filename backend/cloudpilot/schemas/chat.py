"""Cloud Advisor chat schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, field_validator

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
    # `validation_alias`, not `alias`: this only remaps the ORM attribute name
    # on the way *in*. A plain `alias` also renames the field on the way out —
    # FastAPI serializes by alias by default — so the API was sending
    # `citations_json`/`tool_calls_json` as the JSON keys while the frontend
    # (correctly, per the TS types) reads `citations`/`tool_calls`, which were
    # therefore always `undefined` on every assistant message with a reply.
    citations: list[Citation] = Field(default_factory=list, validation_alias="citations_json")
    tool_calls: list[ToolCall] = Field(default_factory=list, validation_alias="tool_calls_json")
    tokens_used: int | None = None
    created_at: datetime

    @field_validator("citations", "tool_calls", mode="before")
    @classmethod
    def _null_to_empty_list(cls, value: object) -> object:
        # The ORM column is nullable (NULL for every user message, and for
        # any assistant message with nothing to cite) — `default_factory`
        # only fills in a *missing* field, not one that's explicitly None, so
        # without this every session containing such a message 500s on GET.
        return [] if value is None else value


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
