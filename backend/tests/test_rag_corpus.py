"""The RAG corpus and the ingestion path that keeps it current.

Two things this locks in:

* The corpus is big enough for ``k=5`` retrieval to discriminate. It sat at 7
  chunks since the initial scaffold — with k=5, a query matched most of the
  knowledge base regardless of relevance, which is why the 20 July RAG-quality
  pass concluded corpus size, not the retrieval code, was the real ceiling on
  Advisor answer quality.
* Ingestion notices when the corpus has *changed*, not merely whether the
  collection is empty. The old skip-if-non-empty check made the corpus
  effectively immutable after first boot: adding an entry here would never
  reach an environment that had already ingested once.
"""

from __future__ import annotations

import pytest

from cloudpilot.ai.rag import ingestor
from cloudpilot.ai.rag.ingestor import CHUNK_SIZE, KNOWLEDGE_BASE, build_chunks, ingest


def test_corpus_is_large_enough_for_k5_retrieval() -> None:
    chunks = build_chunks()
    # k=5 against 7 chunks returns most of the corpus for any query. Require a
    # comfortable multiple of k so relevance ranking actually does some work.
    assert len(chunks) >= 20, f"corpus is only {len(chunks)} chunks; k=5 barely discriminates"


def test_every_entry_has_the_metadata_citations_are_built_from() -> None:
    """ArchitectAgent._build_citations renders source/section as the chip text;
    a blank section produces a citation that says nothing."""
    for doc in KNOWLEDGE_BASE:
        assert doc["source"], doc
        assert doc["section"], doc
        assert doc["text"].strip(), doc


def test_all_three_providers_are_represented() -> None:
    providers = {d.get("provider") for d in KNOWLEDGE_BASE}
    assert {"azure", "aws", "gcp"} <= providers


def test_no_entry_silently_splits_mid_sentence_into_a_second_chunk() -> None:
    """Entries are authored to sit inside one chunk window. An entry that spills
    over produces a fragment whose trailing sentence is cut, which then gets
    retrieved and cited on its own."""
    for doc in KNOWLEDGE_BASE:
        assert len(doc["text"]) <= CHUNK_SIZE, (
            f"{doc['section']} is {len(doc['text'])} chars and would be split"
        )


def test_chunk_ids_are_unique() -> None:
    ids = [c["id"] for c in build_chunks()]
    assert len(ids) == len(set(ids))


def test_source_filter_selects_a_subset() -> None:
    azure_only = build_chunks("azure_docs")
    assert azure_only
    assert len(azure_only) < len(build_chunks())
    assert {c["source"] for c in azure_only} == {"azure_docs"}


# ─── Ingestion freshness ───
class _FakeEngine:
    def __init__(self, stored: int) -> None:
        self.stored = stored
        self.reset_called = False
        self.added: list[dict] | None = None

    async def count(self) -> int:
        return self.stored

    async def reset(self) -> None:
        self.reset_called = True
        self.stored = 0

    async def add_documents(self, chunks: list[dict]) -> int:
        self.added = chunks
        return len(chunks)


async def test_ingest_reingests_when_the_corpus_has_grown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact regression: a collection populated by an older, smaller corpus
    must be rebuilt, not skipped."""
    engine = _FakeEngine(stored=7)
    monkeypatch.setattr(ingestor, "get_rag_engine", lambda: engine)

    stored = await ingest("all")

    assert engine.reset_called
    assert stored == len(build_chunks())


async def test_ingest_skips_when_already_current(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _FakeEngine(stored=len(build_chunks()))
    monkeypatch.setattr(ingestor, "get_rag_engine", lambda: engine)

    stored = await ingest("all")

    assert not engine.reset_called
    assert engine.added is None
    assert stored == len(build_chunks())


async def test_ingest_populates_an_empty_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _FakeEngine(stored=0)
    monkeypatch.setattr(ingestor, "get_rag_engine", lambda: engine)

    stored = await ingest("all")

    assert not engine.reset_called  # nothing to drop
    assert stored == len(build_chunks())


async def test_force_rebuilds_even_when_current(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _FakeEngine(stored=len(build_chunks()))
    monkeypatch.setattr(ingestor, "get_rag_engine", lambda: engine)

    stored = await ingest("all", force=True)

    assert engine.reset_called
    assert stored == len(build_chunks())
