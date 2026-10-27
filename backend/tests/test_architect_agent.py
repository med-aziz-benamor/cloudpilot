"""Tests for the Cloud Advisor's crash-on-null-answer fix.

Covers two layers on purpose: LLMClient.generate() itself must never hand back
a falsy answer (so every caller is protected, not just this one), and
ArchitectAgent._build_citations() must tolerate None regardless, as a second
line of defense at the exact site that used to crash."""

from __future__ import annotations

import pytest

from cloudpilot.ai.architect_agent import ArchitectAgent
from cloudpilot.ai.llm import LLMClient


async def test_generate_falls_back_when_the_provider_returns_null_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tool-calling-capable model answering with `content: null` (its normal
    way of asking to call a tool we don't execute) must not propagate None."""
    client = LLMClient()

    async def _returns_none(_messages: object, _tools: object = None) -> None:
        return None

    monkeypatch.setattr(client, "_ollama_generate", _returns_none)
    monkeypatch.setattr(client, "_openai_generate", _returns_none)

    answer = await client.generate([{"role": "user", "content": "USER QUESTION:\nhi"}])

    assert isinstance(answer, str)
    assert answer  # the fallback message, never None/empty


def test_build_citations_tolerates_a_none_answer() -> None:
    agent = ArchitectAgent.__new__(ArchitectAgent)  # skip __init__ (no LLM/RAG needed)
    # No [n] markers in a None answer, so `used` is empty and every doc is
    # included (matches the "no markers cited" behavior for a real string).
    citations = agent._build_citations(None, [{"section": "Azure pricing"}])
    assert citations == [{"source": "Azure pricing", "section": "Azure pricing", "url": None}]


def test_build_citations_tolerates_an_empty_answer_with_no_docs() -> None:
    agent = ArchitectAgent.__new__(ArchitectAgent)
    assert agent._build_citations(None, []) == []
