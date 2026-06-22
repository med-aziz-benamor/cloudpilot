"""RAG engine — ChromaDB vector store + nomic-embed-text embeddings + retrieval.

Uses an in-process LRU cache (100 entries) over query results. Falls back to an
in-memory store when ChromaDB is unreachable so the demo never hard-fails.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from loguru import logger

from cloudpilot.ai.llm import LLMClient
from cloudpilot.config import settings


class RAGEngine:
    """Thin wrapper over a ChromaDB collection with embedding + retrieval helpers."""

    def __init__(self) -> None:
        self.llm = LLMClient()
        self._collection = None
        self._memory_store: list[dict[str, Any]] = []

    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        try:
            import chromadb

            client = chromadb.HttpClient(
                host=settings.CHROMADB_HOST, port=settings.CHROMADB_PORT
            )
            self._collection = client.get_or_create_collection(
                name=settings.CHROMADB_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            return self._collection
        except Exception as exc:
            logger.warning("ChromaDB unavailable, using in-memory store: {}", exc)
            return None

    async def add_documents(self, chunks: list[dict[str, Any]]) -> int:
        """Embed and store chunks. Each chunk: {text, source, section, provider, url}."""
        collection = self._get_collection()
        ids, docs, metadatas, embeddings = [], [], [], []
        for i, chunk in enumerate(chunks):
            emb = await self.llm.embed(chunk["text"])
            ids.append(chunk.get("id", f"chunk-{i}-{hash(chunk['text']) & 0xffffffff}"))
            docs.append(chunk["text"])
            metadatas.append(
                {
                    "source": chunk.get("source", "unknown"),
                    "section": chunk.get("section", ""),
                    "provider": chunk.get("provider") or "",
                    "url": chunk.get("url") or "",
                }
            )
            embeddings.append(emb)

        if collection is not None:
            collection.upsert(
                ids=ids, documents=docs, metadatas=metadatas, embeddings=embeddings
            )
        else:
            for cid, doc, md, emb in zip(ids, docs, metadatas, embeddings, strict=True):
                self._memory_store.append(
                    {"id": cid, "text": doc, "meta": md, "embedding": emb}
                )
        logger.info("RAG: stored {} chunks", len(ids))
        return len(ids)

    async def retrieve(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Return the top-k most similar chunks for a query."""
        cached = _cached_retrieve(query, k)
        if cached is not None:
            return cached

        query_emb = await self.llm.embed(query)
        collection = self._get_collection()
        results: list[dict[str, Any]] = []

        if collection is not None:
            try:
                res = collection.query(query_embeddings=[query_emb], n_results=k)
                docs = res.get("documents", [[]])[0]
                metas = res.get("metadatas", [[]])[0]
                for text, md in zip(docs, metas, strict=False):
                    results.append({"text": text, **md})
            except Exception as exc:
                logger.warning("Chroma query failed: {}", exc)

        if not results and self._memory_store:
            results = self._memory_score(query_emb, k)

        _store_in_cache(query, k, results)
        return results

    def _memory_score(self, query_emb: list[float], k: int) -> list[dict[str, Any]]:
        def cosine(a: list[float], b: list[float]) -> float:
            num = sum(x * y for x, y in zip(a, b, strict=False))
            da = sum(x * x for x in a) ** 0.5 or 1.0
            db = sum(y * y for y in b) ** 0.5 or 1.0
            return num / (da * db)

        ranked = sorted(
            self._memory_store,
            key=lambda c: cosine(query_emb, c["embedding"]),
            reverse=True,
        )
        return [{"text": c["text"], **c["meta"]} for c in ranked[:k]]

    async def count(self) -> int:
        collection = self._get_collection()
        if collection is not None:
            try:
                return collection.count()
            except Exception:  # pragma: no cover
                pass
        return len(self._memory_store)


# Module-level LRU cache (keyed by query+k) — 100 entries per the caching strategy.
_cache: dict[tuple[str, int], list[dict[str, Any]]] = {}


@lru_cache(maxsize=1)
def _engine_singleton() -> RAGEngine:
    return RAGEngine()


def get_rag_engine() -> RAGEngine:
    """Return the shared RAG engine singleton."""
    return _engine_singleton()


def _cached_retrieve(query: str, k: int) -> list[dict[str, Any]] | None:
    return _cache.get((query, k))


def _store_in_cache(query: str, k: int, value: list[dict[str, Any]]) -> None:
    if len(_cache) >= 100:
        _cache.pop(next(iter(_cache)))
    _cache[(query, k)] = value
