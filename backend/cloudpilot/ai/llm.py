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
        vector, _ = await self.embed_with_status(text)
        return vector

    async def embed_with_status(self, text: str) -> tuple[list[float], bool]:
        """Embed ``text``, reporting whether the vector is real.

        Returns ``(vector, is_real)``. On failure the hash fallback keeps the demo
        working offline, but the vector is meaningless for similarity — it exists so
        callers do not crash, not so they can trust the result. Any caller that
        *caches* what it derives from an embedding must check the flag, or a
        transient Ollama outage gets frozen into that cache for the process
        lifetime. See ``rag.engine.retrieve``.
        """
        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                    json={"model": settings.OLLAMA_EMBED_MODEL, "prompt": text},
                )
                resp.raise_for_status()
                return resp.json()["embedding"], True
        except Exception as exc:
            logger.warning("Embedding failed, using hash fallback: {}", exc)
            return self._hash_embedding(text), False

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
        """Answer shown when the LLM is unreachable.

        This is *not* a model answer, and it must never be mistaken for one. Two rules:

        * It says so, first thing. A canned paragraph dressed up as a grounded answer
          (with a citation chip attached) is worse than an honest error.
        * It never echoes the prompt back. The last ``user`` message is the fully
          assembled prompt — context documents, live infrastructure data and all — not
          the question the user typed, so quoting it leaked the entire prompt into the
          chat window.
        """
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        # Recover the real question from the assembled prompt (see rag/prompts.py).
        marker = "USER QUESTION:"
        question = last.rsplit(marker, 1)[-1].strip() if marker in last else last.strip()
        return (
            "⚠️ The local language model is unavailable, so this is not a generated "
            "answer.\n\n"
            f'Your question — "{question[:180]}" — was not sent to a model. '
            "The retrieved source documents are listed below and may still be useful. "
            "Start Ollama (and confirm OLLAMA_MODEL matches a pulled model) to get a "
            "real answer."
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
