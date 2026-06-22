"""Shared schema primitives."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class APISchema(BaseModel):
    """Base schema. ``extra='forbid'`` rejects unknown fields (strict input)."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ResponseSchema(BaseModel):
    """Base for responses — permissive on attribute mapping, not strict on extras."""

    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(ResponseSchema, Generic[T]):
    """Envelope for paginated list endpoints."""

    items: list[T]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    has_next: bool


class MessageResponse(ResponseSchema):
    """Generic success message."""

    message: str
