"""RAG engine — ChromaDB vector store + nomic-embed-text embeddings + retrieval.

Caches query results in-process, capped at 100 entries with FIFO eviction (not
true LRU — a hit does not refresh an entry's position). Only confident results are
cached; see :meth:`RAGEngine.retrieve`. Falls back to an in-memory store when
ChromaDB is unreachable so the demo never hard-fails.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from loguru import logger

from cloudpilot.ai.llm import LLMClient
from cloudpilot.config import settings

#: Drop retrieved chunks further than this from the query (cosine distance; the
#: collection is created with ``hnsw:space=cosine``).
#:
#: Without it, ``retrieve`` returns the top-k *regardless of how bad k is*, and the
#: chat endpoint renders whatever comes back as citation chips. Asking the Advisor
#: "What is the capital of France?" produced five authoritative-looking sources
#: about AKS node pools.
#:
#: Measured against the seeded corpus (nomic-embed-text), best-match distance by
#: query:
#:
#:     Is my Azure AKS cluster correctly sized?   0.3097
#:     Why did my Azure costs spike last month?   0.2546
#:     How do I reduce S3 storage costs?          0.4231
#:     asdfgh qwerty zxcvbn                       0.5567
#:     What is the capital of France?             0.6587
#:
#: On-domain questions sit well below 0.5 and unrelated ones well above, so 0.55
#: falls in the observed gap. It is deliberately loose: the job is to reject
#: questions the corpus cannot speak to at all, not to fine-tune ranking.
MAX_COSINE_DISTANCE = 0.55


class RAGEngine:
    """Thin wrapper over a ChromaDB collection with embedding + retrieval helpers."""

    def __init__(self) -> None:
        self.llm = LLMClient()
        # chromadb is an optional runtime dependency (the engine degrades to an
        # in-memory store when it is unreachable), so the collection is typed
        # loosely rather than importing chromadb just for an annotation.
        self._collection: Any | None = None
        self._memory_store: list[dict[str, Any]] = []

    def _get_collection(self) -> Any | None:
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
        """Return the top-k most similar chunks for a query.

        Only a *confident* result is cached. Two degraded paths must never be
        memoised, because the cache has no TTL and would serve the degraded answer
        for the rest of the process lifetime:

        * the embedding fell back to the hash stub (Ollama unreachable), so the
          query vector is meaningless and whatever it matched is noise;
        * retrieval produced nothing at all — a Chroma outage and an empty
          collection are indistinguishable here from "no relevant documents", and
          freezing that in means the Advisor answers ungrounded until restart.

        Both used to be cached unconditionally.
        """
        cached = _cached_retrieve(query, k)
        if cached is not None:
            return cached

        query_emb, embedding_ok = await self.llm.embed_with_status(query)
        collection = self._get_collection()
        results: list[dict[str, Any]] = []
        retrieval_ok = True

        if collection is not None:
            try:
                res = collection.query(query_embeddings=[query_emb], n_results=k)
                docs = res.get("documents", [[]])[0]
                metas = res.get("metadatas", [[]])[0]
                dists = (res.get("distances") or [[]])[0]
                for text, md, dist in zip(
                    docs, metas, dists or [0.0] * len(docs), strict=False
                ):
                    if dist > MAX_COSINE_DISTANCE:
                        continue
                    results.append({"text": text, **md})
            except Exception as exc:
                logger.warning("Chroma query failed: {}", exc)
                retrieval_ok = False

        if not results and self._memory_store:
            results = self._memory_score(query_emb, k)

        if embedding_ok and retrieval_ok and results:
            _store_in_cache(query, k, results)
        else:
            logger.debug(
                "RAG: not caching degraded retrieval "
                "(embedding_ok={}, retrieval_ok={}, hits={})",
                embedding_ok,
                retrieval_ok,
                len(results),
            )
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
                total: int = collection.count()
                return total
            except Exception:  # pragma: no cover
                pass
        return len(self._memory_store)

    async def reset(self) -> None:
        """Drop every stored chunk so the corpus can be re-ingested.

        Needed because ingestion is otherwise skip-if-non-empty: without this,
        adding an entry to ``KNOWLEDGE_BASE`` would never reach an environment
        whose collection was already populated by an earlier, smaller corpus.
        Also clears the in-process retrieval cache, which would otherwise keep
        answering from the corpus that was just deleted.
        """
        collection = self._get_collection()
        if collection is not None:
            try:
                import chromadb

                client = chromadb.HttpClient(
                    host=settings.CHROMADB_HOST, port=settings.CHROMADB_PORT
                )
                client.delete_collection(name=settings.CHROMADB_COLLECTION)
                self._collection = None
            except Exception as exc:  # pragma: no cover - resilience
                logger.warning("Could not reset Chroma collection: {}", exc)
        self._memory_store.clear()
        _cache.clear()


# Module-level query cache (keyed by query+k) — 100 entries, FIFO eviction.
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
