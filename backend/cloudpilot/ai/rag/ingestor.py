"""Knowledge-base ingestor — loads cloud cost-optimization docs into ChromaDB.

For the v1 demo the knowledge base is bootstrapped from a curated, embedded set of
Azure / AWS / GCP / FinOps best-practice snippets (so the platform works fully
offline with no document downloads). Chunking uses an 800-char window with 120-char
overlap, mirroring the EchoLearn pipeline.

Run once at startup (if the collection is empty):

    python -m cloudpilot.ai.rag.ingestor --source all
"""

from __future__ import annotations

import argparse
import asyncio

from loguru import logger

from cloudpilot.ai.rag.engine import get_rag_engine

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

# Curated knowledge base. Each entry becomes one or more chunks.
KNOWLEDGE_BASE: list[dict[str, str]] = [
    {
        "source": "azure_docs",
        "provider": "azure",
        "section": "AKS Best Practices / Node Pool Sizing §4.2",
        "text": (
            "For Azure Kubernetes Service, right-size node pools by tracking P95 CPU "
            "and memory utilization over at least 14 days. If P95 CPU stays below 40% "
            "and P95 memory below 60%, the pool is over-provisioned. Downsize the VM "
            "SKU one tier (for example Standard_D4s_v3 to Standard_D2s_v3) or reduce "
            "the node count. Enable the cluster autoscaler with conservative min/max "
            "bounds to prevent runaway scale-out events that spike compute cost."
        ),
    },
    {
        "source": "azure_docs",
        "provider": "azure",
        "section": "Cost Management / Anomaly Detection",
        "text": (
            "Azure Cost Management surfaces anomalies by comparing daily spend against "
            "a rolling baseline. A spike beyond two standard deviations typically "
            "indicates a misconfiguration: an autoscaler event, an orphaned disk, or a "
            "forgotten test environment. Investigate the top resources contributing to "
            "the delta and confirm whether the increase is expected before acting."
        ),
    },
    {
        "source": "aws_docs",
        "provider": "aws",
        "section": "EC2 Right Sizing",
        "text": (
            "AWS Compute Optimizer recommends downsizing EC2 instances whose maximum "
            "CPU and memory utilization remain low across the observation window. "
            "Moving from m5.xlarge to m5.large halves vCPU and memory and roughly "
            "halves the hourly cost. Validate that the workload does not have periodic "
            "bursts before committing to a smaller instance type."
        ),
    },
    {
        "source": "aws_docs",
        "provider": "aws",
        "section": "RDS Cost Optimization",
        "text": (
            "Sudden RDS cost increases are often caused by changes to backup retention, "
            "storage autoscaling, or a switch to provisioned IOPS. Review the RDS "
            "events log and the storage and backup configuration when an anomaly is "
            "detected. Consider Reserved Instances for steady-state database workloads."
        ),
    },
    {
        "source": "gcp_docs",
        "provider": "gcp",
        "section": "Compute Engine Recommendations",
        "text": (
            "GCP's Recommender analyzes 8 days of metrics to suggest machine-type "
            "changes for Compute Engine VMs. For predictable workloads, committed use "
            "discounts reduce cost by up to 57%. Avoid downsizing VMs that handle burst "
            "traffic, as throttling can degrade user experience."
        ),
    },
    {
        "source": "finops_foundation",
        "provider": None,
        "section": "FinOps Framework / Inform Phase",
        "text": (
            "The FinOps lifecycle has three phases: Inform, Optimize, Operate. The "
            "Inform phase establishes visibility through shared dashboards and "
            "allocation. Roughly 32% of cloud spend is wasted on idle or oversized "
            "resources; unified multi-cloud visibility is the prerequisite for "
            "capturing those savings. Forecasting and anomaly detection turn reactive "
            "billing into proactive cost governance."
        ),
    },
    {
        "source": "finops_foundation",
        "provider": None,
        "section": "FinOps Framework / Optimize Phase",
        "text": (
            "In the Optimize phase, teams act on recommendations: rightsizing, "
            "scheduling non-production resources off-hours, purchasing commitments, and "
            "eliminating waste. Each recommendation should carry an estimated saving "
            "and a confidence score so owners can prioritize high-impact, high-"
            "confidence actions first."
        ),
    },
]


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping character windows."""
    if len(text) <= size:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += size - overlap
    return chunks


async def ingest(source: str = "all") -> int:
    """Ingest the knowledge base into ChromaDB. Returns the number of chunks stored."""
    engine = get_rag_engine()
    existing = await engine.count()
    if existing > 0:
        logger.info("RAG collection already populated ({} chunks); skipping.", existing)
        return existing

    chunks: list[dict] = []
    for doc in KNOWLEDGE_BASE:
        if source != "all" and doc["source"] != source:
            continue
        for i, piece in enumerate(chunk_text(doc["text"])):
            chunks.append(
                {
                    "id": f"{doc['source']}-{doc['section']}-{i}".replace(" ", "_"),
                    "text": piece,
                    "source": doc["source"],
                    "section": doc["section"],
                    "provider": doc.get("provider"),
                    "url": None,
                }
            )
    stored = await engine.add_documents(chunks)
    logger.info("RAG ingestion complete: {} chunks", stored)
    return stored


def main() -> None:
    parser = argparse.ArgumentParser(description="CloudPilot RAG ingestor")
    parser.add_argument("--source", default="all")
    args = parser.parse_args()
    asyncio.run(ingest(args.source))


if __name__ == "__main__":
    main()
