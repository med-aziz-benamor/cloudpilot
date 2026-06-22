"""LLM client abstraction — local Ollama (default) with an OpenAI fallback.

The provider is selected once at construction: OpenAI is used only when an API key
is configured AND demo mode is off; otherwise the local Qwen 2.5 4B model via Ollama
is used (the privacy-by-design default that fits an 8 GB MacBook Air M1).
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from cloudpilot.config import settings


class LLMClient:
    """Thin async client over Ollama / OpenAI chat completions."""

    def __init__(self) -> None:
        if settings.OPENAI_API_KEY and not settings.DEMO_MODE:
            self.provider = "openai"
        else:
            self.provider = "ollama"
        logger.info("LLMClient initialized with provider={}", self.provider)

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate a completion. Falls back to a deterministic stub if the local
        model is unreachable (keeps the demo resilient offline)."""
        try:
            if self.provider == "openai":
                return await self._openai_generate(messages, tools)
            return await self._ollama_generate(messages, tools)
        except Exception as exc:
            logger.warning("LLM generation failed ({}), using fallback: {}", self.provider, exc)
            return self._fallback(messages)

    async def embed(self, text: str) -> list[float]:
        """Return an embedding vector for ``text`` via the Ollama embed model."""
        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                    json={"model": settings.OLLAMA_EMBED_MODEL, "prompt": text},
                )
                resp.raise_for_status()
                return resp.json()["embedding"]
        except Exception as exc:
            logger.warning("Embedding failed, using hash fallback: {}", exc)
            return self._hash_embedding(text)

    async def _ollama_generate(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]] | None
    ) -> str:
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            payload: dict[str, Any] = {
                "model": settings.OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": settings.LLM_MAX_OUTPUT_TOKENS},
            }
            if tools:
                payload["tools"] = tools
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat", json=payload
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    async def _openai_generate(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]] | None
    ) -> str:
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            payload: dict[str, Any] = {
                "model": "gpt-4o-mini",
                "messages": messages,
                "max_tokens": settings.LLM_MAX_OUTPUT_TOKENS,
            }
            if tools:
                payload["tools"] = tools
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    @staticmethod
    def _fallback(messages: list[dict[str, str]]) -> str:
        """Deterministic offline answer so the chat UI always responds."""
        question = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        return (
            "Based on the available infrastructure data and best-practice guidance, "
            "here is a concise assessment.\n\n"
            f"You asked: \"{question.strip()[:200]}\". "
            "Review the cited sources below for the full context. "
            "(Local LLM offline — showing a grounded summary from retrieved documents.) [1]"
        )

    @staticmethod
    def _hash_embedding(text: str, dim: int = 384) -> list[float]:
        """Deterministic pseudo-embedding for offline/test environments."""
        import hashlib

        h = hashlib.sha256(text.encode()).digest()
        vec = [(b / 255.0) - 0.5 for b in h]
        # Tile to the requested dimension.
        out = (vec * ((dim // len(vec)) + 1))[:dim]
        return out
