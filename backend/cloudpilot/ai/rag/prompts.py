"""System prompts and prompt construction for the Cloud Advisor (ArchitectAgent)."""

from __future__ import annotations

SYSTEM_PROMPT = """You are CloudPilot's infrastructure advisor.

Answer the user's question about THEIR cloud infrastructure (Azure, AWS, GCP).
Rules:
- Cite sources inline using [1], [2] notation that map to the provided documents.
- ALWAYS prefer the user's actual live data over generic documentation.
- Be concise, specific, and quantitative. Use real numbers when available.
- If you don't have the data to answer, say so plainly. Never guess or invent figures.
- Keep answers under ~250 words unless asked for detail.
"""

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_resource_metrics",
            "description": "Get recent CPU/RAM/network metrics for a resource.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_id": {"type": "string"},
                    "metric": {"type": "string"},
                    "days": {"type": "integer"},
                },
                "required": ["resource_id", "metric"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_billing_summary",
            "description": "Get a billing summary for a provider over N days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "days": {"type": "integer"},
                },
                "required": ["provider"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_resources",
            "description": "Search resources by name or service.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]


def build_messages(
    question: str,
    retrieved_docs: list[dict],
    live_data: str | None = None,
    history: list[dict] | None = None,
) -> list[dict[str, str]]:
    """Assemble the chat message list sent to the LLM."""
    context_blocks = []
    for i, doc in enumerate(retrieved_docs, start=1):
        src = doc.get("source", "unknown")
        section = doc.get("section", "")
        context_blocks.append(f"[{i}] ({src} · {section})\n{doc.get('text', '')}")
    context = "\n\n".join(context_blocks) if context_blocks else "No documents retrieved."

    user_content = (
        f"CONTEXT DOCUMENTS:\n{context}\n\n"
        f"LIVE INFRASTRUCTURE DATA:\n{live_data or 'None provided.'}\n\n"
        f"USER QUESTION:\n{question}"
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_content})
    return messages
