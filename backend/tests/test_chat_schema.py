"""ChatMessageResponse must survive real data shapes and serialize the field
names the frontend actually reads.

Found via a live browser smoke test (not static review): every chat session
with an existing reply 500'd on GET, and even once that was fixed, the Chat
Advisor crashed client-side on every assistant message. Two independent bugs:

1. `citations_json`/`tool_calls_json` are nullable ORM columns — NULL for
   every user message, and for any assistant message with nothing to cite —
   but the response schema's `default_factory=list` only applies when the
   field is *absent*, not when it's explicitly `None`. Fixed with a
   `field_validator(mode="before")` coercing `None` -> `[]`.
2. The schema used a plain `alias="citations_json"` to read the ORM
   attribute name. FastAPI serializes response models by alias by default,
   so the API was sending `citations_json`/`tool_calls_json` as the actual
   JSON keys, while the frontend (correctly, per its TS types) reads
   `citations`/`tool_calls` — meaning those were `undefined` in the browser
   on every single assistant reply. Fixed by using `validation_alias`
   (input-only) instead of `alias` (input and output).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from cloudpilot.schemas.chat import ChatMessageResponse


def _row(citations_json: object, tool_calls_json: object) -> dict:
    return {
        "id": uuid4(),
        "role": "assistant",
        "content": "hello",
        "citations_json": citations_json,
        "tool_calls_json": tool_calls_json,
        "tokens_used": None,
        "created_at": datetime.now(UTC),
    }


def test_null_citations_and_tool_calls_become_empty_lists() -> None:
    resp = ChatMessageResponse.model_validate(_row(None, None))
    assert resp.citations == []
    assert resp.tool_calls == []


def test_real_citations_and_tool_calls_survive() -> None:
    resp = ChatMessageResponse.model_validate(
        _row(
            [{"source": "Azure Monitor", "section": None, "url": None}],
            [{"tool": "get_billing_summary", "args": {}, "result": None}],
        )
    )
    assert resp.citations[0].source == "Azure Monitor"
    assert resp.tool_calls[0].tool == "get_billing_summary"


def test_json_output_uses_the_frontend_field_names_not_the_orm_column_names() -> None:
    """The exact regression: the API must emit `citations`/`tool_calls`, not
    `citations_json`/`tool_calls_json` — the frontend's ChatMessage type only
    ever reads the former."""
    resp = ChatMessageResponse.model_validate(_row([], []))
    dumped = resp.model_dump(mode="json", by_alias=True)
    assert "citations" in dumped
    assert "tool_calls" in dumped
    assert "citations_json" not in dumped
    assert "tool_calls_json" not in dumped
