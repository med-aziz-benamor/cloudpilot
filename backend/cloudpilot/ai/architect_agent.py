"""ArchitectAgent — RAG-powered Cloud Advisor (on-demand).

Runs per user chat message:
1. Retrieve top-5 docs from ChromaDB for the question.
2. Resolve any referenced resources and assemble live infrastructure context
   (a hand-rolled lookup, logged as a "tool_calls" trace for the chat UI —
   this is not LLM tool-calling; the LLM never chooses these calls itself).
3. Build the prompt and call the LLM.
4. Parse the answer and extract citations.
5. Return the answer + citations + the trace from step 2 to the chat service.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.ai.base_agent import AgentBase
from cloudpilot.ai.llm import LLMClient
from cloudpilot.ai.rag.engine import get_rag_engine
from cloudpilot.ai.rag.prompts import build_messages
from cloudpilot.models.billing_entry import BillingEntry
from cloudpilot.models.cloud_account import CloudAccount
from cloudpilot.models.recommendation import AgentType
from cloudpilot.models.resource import Resource


class ArchitectAgent(AgentBase):
    name = "ArchitectAgent"
    description = "Answers infrastructure questions via retrieval-augmented generation."
    agent_type = AgentType.ARCHITECT

    def __init__(self) -> None:
        self.llm = LLMClient()
        self.rag = get_rag_engine()

    async def run(self, organization_id: uuid.UUID, db: AsyncSession) -> int:
        # ArchitectAgent is on-demand only; scheduled runs are a no-op.
        return 0

    async def trigger(
        self, organization_id: uuid.UUID, db: AsyncSession, payload: dict[str, Any]
    ) -> dict[str, Any]:
        question: str = payload["question"]
        history: list[dict[str, str]] = payload.get("history", [])

        docs = await self.rag.retrieve(question, k=5)
        live_data, tool_calls = await self._gather_live_context(
            db, organization_id, question
        )

        messages = build_messages(question, docs, live_data, history)
        answer = await self.llm.generate(messages)

        citations = self._build_citations(answer, docs)
        logger.info(
            "ArchitectAgent answered org={} (docs={}, tools={})",
            organization_id,
            len(docs),
            len(tool_calls),
        )
        return {
            "content": answer,
            "citations": citations,
            "tool_calls": tool_calls,
        }

    async def _gather_live_context(
        self, db: AsyncSession, organization_id: uuid.UUID, question: str
    ) -> tuple[str, list[dict]]:
        """Resolve referenced resources and produce a live-data summary + tool trace."""
        tool_calls: list[dict] = []
        parts: list[str] = []

        account_ids = (
            (await db.execute(
                select(CloudAccount.id).where(
                    CloudAccount.organization_id == organization_id
                )
            )).scalars().all()
        )
        if not account_ids:
            return "No connected cloud accounts.", tool_calls

        # If the question references a resource name, surface its details.
        tokens = re.findall(r"[a-zA-Z0-9\-_]{4,}", question.lower())
        if tokens:
            res = (
                await db.execute(
                    select(Resource)
                    .where(Resource.cloud_account_id.in_(account_ids))
                    .where(
                        func.lower(Resource.name).in_(tokens)
                        | func.lower(Resource.service).in_(tokens)
                    )
                    .limit(5)
                )
            ).scalars().all()
            for r in res:
                parts.append(
                    f"Resource {r.name} ({r.service}, {r.region}, SKU {r.sku})."
                )
                tool_calls.append(
                    {
                        "tool": "search_resources",
                        "args": {"query": r.name},
                        "result": {"service": r.service, "region": r.region, "sku": r.sku},
                    }
                )

        # Always include a high-level billing summary as grounding.
        total = (
            await db.execute(
                select(func.coalesce(func.sum(BillingEntry.cost_usd), 0)).where(
                    BillingEntry.cloud_account_id.in_(account_ids)
                )
            )
        ).scalar_one()
        parts.append(f"Total recorded spend across all accounts: ${float(total):,.0f}.")
        tool_calls.append(
            {
                "tool": "get_billing_summary",
                "args": {"provider": "all", "days": 90},
                "result": {"total_usd": round(float(total), 2)},
            }
        )

        return "\n".join(parts), tool_calls

    def _build_citations(self, answer: str | None, docs: list[dict]) -> list[dict]:
        """Map [n] markers in the answer back to retrieved document metadata."""
        used = {int(n) for n in re.findall(r"\[(\d+)\]", answer or "")}
        citations: list[dict] = []
        for i, doc in enumerate(docs, start=1):
            if not used or i in used:
                citations.append(
                    {
                        "source": doc.get("section") or doc.get("source", "source"),
                        "section": doc.get("section"),
                        "url": doc.get("url") or None,
                    }
                )
        # If the model cited nothing, still attach the top doc for transparency.
        return citations[:5] if citations else (
            [{"source": docs[0].get("section", "source"), "section": None, "url": None}]
            if docs
            else []
        )
