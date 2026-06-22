"""Tests for agent algorithms that can run without a database."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from cloudpilot.ai.cost_agent import CostAgent
from cloudpilot.ai.rag.ingestor import chunk_text
from cloudpilot.core.audit import GENESIS_SIGNATURE, compute_signature


def test_cost_agent_detects_spike(anomaly_series: list[float]) -> None:
    agent = CostAgent()
    dates = [date.today() - timedelta(days=len(anomaly_series) - i)
             for i in range(len(anomaly_series))]
    flagged = agent._detect(dates, np.array(anomaly_series, dtype=float))
    # The final element (the 6x spike) must be flagged.
    assert (len(anomaly_series) - 1) in flagged


def test_cost_agent_no_false_positive_on_flat() -> None:
    agent = CostAgent()
    flat = np.array([100.0] * 30, dtype=float)
    dates = [date.today() - timedelta(days=30 - i) for i in range(30)]
    flagged = agent._detect(dates, flat)
    assert flagged == []


def test_chunk_text_overlap() -> None:
    text = "x" * 2000
    chunks = chunk_text(text, size=800, overlap=120)
    assert len(chunks) >= 3
    assert all(len(c) <= 800 for c in chunks)


def test_audit_hash_chain_links() -> None:
    row1 = {"event": "a"}
    sig1 = compute_signature(GENESIS_SIGNATURE, row1)
    sig2 = compute_signature(sig1, {"event": "b"})
    # Deterministic and chained.
    assert sig1 == compute_signature(GENESIS_SIGNATURE, row1)
    assert sig2 != sig1
    assert len(sig1) == 64
