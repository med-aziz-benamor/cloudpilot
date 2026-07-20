"""The RAG query cache must never memoise a degraded retrieval.

The cache has no TTL and lives for the process lifetime, so anything cached during
a transient outage is served as fresh until the container restarts. Two paths used
to be cached unconditionally: a hash-fallback embedding (Ollama down) and an empty
result (Chroma down, or an un-ingested collection).
"""

from __future__ import annotations

import pytest

from cloudpilot.ai.rag import engine as rag_engine
from cloudpilot.ai.rag.engine import RAGEngine


@pytest.fixture(autouse=True)
def _clear_cache():
    rag_engine._cache.clear()
    yield
    rag_engine._cache.clear()


class _FakeCollection:
    """Stands in for a Chroma collection."""

    def __init__(
        self,
        docs: list[str] | None = None,
        raises: bool = False,
        distances: list[float] | None = None,
    ) -> None:
        self._docs = docs or []
        self._raises = raises
        self._distances = distances
        self.queries = 0

    def query(self, query_embeddings, n_results):  # noqa: ARG002
        self.queries += 1
        if self._raises:
            raise RuntimeError("chroma unavailable")
        out = {
            "documents": [self._docs],
            "metadatas": [[{"source": "doc", "section": "s", "provider": "", "url": ""}]
                          * len(self._docs)],
        }
        if self._distances is not None:
            out["distances"] = [self._distances]
        return out


def _engine(collection, *, embedding_ok: bool = True) -> RAGEngine:
    eng = RAGEngine()
    eng._collection = collection
    eng._get_collection = lambda: collection  # type: ignore[method-assign]

    async def fake_embed_with_status(text: str) -> tuple[list[float], bool]:
        return [0.1, 0.2, 0.3], embedding_ok

    eng.llm.embed_with_status = fake_embed_with_status  # type: ignore[method-assign]
    return eng


async def test_good_retrieval_is_cached() -> None:
    col = _FakeCollection(docs=["chunk one"])
    eng = _engine(col)

    first = await eng.retrieve("how big is my cluster", k=5)
    second = await eng.retrieve("how big is my cluster", k=5)

    assert first == second
    assert [d["text"] for d in first] == ["chunk one"]
    assert col.queries == 1, "second call should have been served from cache"


async def test_failed_chroma_query_is_not_cached() -> None:
    """A Chroma outage must not freeze an empty answer into the cache."""
    col = _FakeCollection(raises=True)
    eng = _engine(col)

    assert await eng.retrieve("q", k=5) == []
    assert ("q", 5) not in rag_engine._cache

    # Chroma recovers — the next call must hit it again, not serve the empty result.
    recovered = _FakeCollection(docs=["real chunk"])
    eng._get_collection = lambda: recovered  # type: ignore[method-assign]
    results = await eng.retrieve("q", k=5)
    assert [d["text"] for d in results] == ["real chunk"]


async def test_hash_fallback_embedding_is_not_cached() -> None:
    """If the embedding is the hash stub, whatever it matched is noise."""
    col = _FakeCollection(docs=["arbitrary match"])
    eng = _engine(col, embedding_ok=False)

    results = await eng.retrieve("q", k=5)
    assert results, "the degraded result is still returned to the caller"
    assert ("q", 5) not in rag_engine._cache, "but it must not be memoised"


async def test_empty_result_is_not_cached() -> None:
    """An un-ingested collection looks identical to an outage — do not memoise it."""
    col = _FakeCollection(docs=[])
    eng = _engine(col)

    assert await eng.retrieve("q", k=5) == []
    assert ("q", 5) not in rag_engine._cache


async def test_cache_is_keyed_by_k() -> None:
    col = _FakeCollection(docs=["chunk one"])
    eng = _engine(col)

    await eng.retrieve("q", k=5)
    await eng.retrieve("q", k=3)
    assert col.queries == 2
    assert ("q", 5) in rag_engine._cache
    assert ("q", 3) in rag_engine._cache


async def test_irrelevant_chunks_are_dropped() -> None:
    """An off-domain question must not come back with confident citations.

    Distances here bracket MAX_COSINE_DISTANCE: two plausible matches and two that
    are further away than anything on-domain was measured to be.
    """
    col = _FakeCollection(
        docs=["relevant a", "relevant b", "unrelated c", "unrelated d"],
        distances=[0.31, 0.42, 0.66, 0.71],
    )
    eng = _engine(col)

    results = await eng.retrieve("what is the capital of france", k=5)
    assert [d["text"] for d in results] == ["relevant a", "relevant b"]


async def test_all_chunks_beyond_threshold_yields_no_sources() -> None:
    """If nothing is close enough, return nothing rather than the least-bad chunk."""
    col = _FakeCollection(
        docs=["unrelated a", "unrelated b"], distances=[0.66, 0.71]
    )
    eng = _engine(col)

    assert await eng.retrieve("what is the capital of france", k=5) == []
    # And an empty result is never cached, so ingesting the missing docs fixes it.
    assert ("what is the capital of france", 5) not in rag_engine._cache


async def test_on_domain_distances_are_kept() -> None:
    col = _FakeCollection(
        docs=["aks sizing", "cost anomalies"], distances=[0.2546, 0.3097]
    )
    eng = _engine(col)

    results = await eng.retrieve("is my aks cluster sized right", k=5)
    assert len(results) == 2


async def test_missing_distances_are_treated_as_relevant() -> None:
    """Back-compat: a store that reports no distances must not silently return zero."""
    col = _FakeCollection(docs=["a", "b"])  # no distances key
    eng = _engine(col)

    assert len(await eng.retrieve("q", k=5)) == 2


async def test_cache_evicts_at_100_entries() -> None:
    col = _FakeCollection(docs=["chunk"])
    eng = _engine(col)

    for i in range(105):
        await eng.retrieve(f"query-{i}", k=5)

    assert len(rag_engine._cache) <= 100
    # FIFO: the earliest queries are the ones dropped.
    assert ("query-0", 5) not in rag_engine._cache
    assert ("query-104", 5) in rag_engine._cache
