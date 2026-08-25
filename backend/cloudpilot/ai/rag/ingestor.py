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
from typing import Any, TypedDict

from loguru import logger

from cloudpilot.ai.rag.engine import get_rag_engine

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120


class KnowledgeDoc(TypedDict):
    """One curated knowledge-base entry.

    A TypedDict rather than ``dict[str, str]`` because ``provider`` is
    legitimately None for provider-agnostic FinOps material — the previous
    annotation claimed otherwise and quietly mistyped every such entry.
    """

    source: str
    provider: str | None
    section: str
    text: str


# Curated knowledge base. Each entry becomes one or more chunks.
KNOWLEDGE_BASE: list[KnowledgeDoc] = [
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
    {
        "source": "finops_foundation",
        "provider": None,
        "section": "FinOps Framework / Operate Phase",
        "text": (
            "The Operate phase makes cost a continuous practice rather than a quarterly "
            "cleanup: budgets and alerts are defined per team, anomalies are triaged "
            "like incidents with a named owner, and unit economics (cost per customer, "
            "per request, per environment) replace raw spend as the headline metric. "
            "Rising total spend is not itself a problem if cost per unit of value is "
            "falling; the two must be reported together or optimization work gets "
            "judged against the wrong number."
        ),
    },
    {
        "source": "finops_foundation",
        "provider": None,
        "section": "Budgets and Forecasting",
        "text": (
            "A useful budget is set per team or per environment against a forecast, not "
            "as a single organization-wide number. Compare month-to-date spend against "
            "the same point in the previous month rather than against the full month, "
            "or every budget looks healthy until the final week. Forecast month-end by "
            "projecting the current daily burn rate across the remaining days, and "
            "alert on the projection crossing the budget rather than on the budget "
            "already being spent — by then the overrun is unavoidable. Set the alert "
            "threshold slightly above the budget (for example 110%) so a forecast that "
            "lands a rounding error over does not page anyone."
        ),
    },
    {
        "source": "finops_foundation",
        "provider": None,
        "section": "Tagging and Cost Allocation",
        "text": (
            "Cost allocation depends on consistent tagging: owner, environment, cost "
            "centre and application, applied at creation time and enforced by policy "
            "rather than added retroactively. Untagged resources become unallocatable "
            "spend that no team recognizes as theirs, which is where idle infrastructure "
            "accumulates. Shared costs such as networking, logging and cluster control "
            "planes need an explicit split rule agreed in advance, because arguing about "
            "the allocation method after the invoice arrives is what stalls FinOps "
            "programmes."
        ),
    },
    {
        "source": "finops_foundation",
        "provider": None,
        "section": "Idle and Orphaned Resources",
        "text": (
            "The cheapest savings are resources nobody is using: unattached block "
            "storage volumes left behind after an instance is deleted, unassociated "
            "static IP addresses, idle load balancers with no healthy targets, old disk "
            "snapshots retained indefinitely, and non-production environments running "
            "24/7 when they are only used during working hours. Scheduling development "
            "and staging compute to run only on weekday business hours removes roughly "
            "two thirds of their running hours, and unlike rightsizing it carries no "
            "performance risk."
        ),
    },
    {
        "source": "finops_foundation",
        "provider": None,
        "section": "Commitment Discounts",
        "text": (
            "All three major providers discount steady-state usage in exchange for a "
            "one or three year commitment: AWS Reserved Instances and Savings Plans, "
            "Azure Reservations, and GCP Committed Use Discounts. Longer terms and "
            "larger upfront payments discount more. Commit only to the baseline you are "
            "confident will persist — the floor of your usage over the last several "
            "months — and leave the variable portion on demand, because an unused "
            "commitment is a loss that no later optimization recovers. Rightsize "
            "*before* committing, or the commitment locks in the oversized footprint."
        ),
    },
    {
        "source": "finops_foundation",
        "provider": None,
        "section": "Investigating a Cost Spike",
        "text": (
            "Work a cost spike from the largest contributor down. Establish the exact "
            "day the increase began, then group spend by service and by resource to "
            "find which single resource moved. Distinguish a price change from a usage "
            "change: usage changes are physical and have a cause in the infrastructure "
            "— more nodes, more storage, more data transferred — while a flat "
            "percentage rise across everything usually means a rate or currency change. "
            "The most common causes are an autoscaler scaling out and not back in, a "
            "backup or retention policy change, a log pipeline suddenly ingesting more, "
            "a test environment left running, and cross-region or internet egress from a "
            "newly deployed component."
        ),
    },
    {
        "source": "finops_foundation",
        "provider": None,
        "section": "Rightsizing Method",
        "text": (
            "Rightsize on percentile utilization, not averages: an average hides the "
            "peak that the instance actually has to serve. Use P95 over at least 14 days "
            "so weekly cycles are represented, and check CPU and memory together, since "
            "a memory-bound workload on an idle CPU is not oversized. Move one size at a "
            "time and re-measure. Treat the resulting saving as the genuine difference "
            "between two published rates multiplied by the number of instances or nodes "
            "affected — a per-node delta quoted for a multi-node pool understates the "
            "saving by the node count."
        ),
    },
    {
        "source": "finops_foundation",
        "provider": None,
        "section": "Storage Cost Optimization",
        "text": (
            "Object storage is billed per GB-month plus per-operation and egress "
            "charges, so it must never be priced like compute on an hourly basis. Move "
            "data that is read infrequently to a cooler access tier, but account for the "
            "higher retrieval cost and any minimum storage duration before doing so for "
            "data that is still actively read. Lifecycle rules that expire incomplete "
            "multipart uploads and old non-current versions recover storage that is "
            "invisible in a normal bucket listing. Snapshots are incremental but their "
            "chains are not free; expire them on a schedule."
        ),
    },
    {
        "source": "finops_foundation",
        "provider": None,
        "section": "Network Egress",
        "text": (
            "Data transfer is the cost most often missed at design time. Inbound traffic "
            "is typically free while outbound to the internet is charged per GB, and "
            "cross-region or cross-availability-zone traffic is charged even though it "
            "never leaves the provider. Chatty services split across zones, replicated "
            "databases, and container images pulled from another region on every deploy "
            "are common sources. Co-locate components that talk to each other, cache at "
            "the edge, and prefer private connectivity to a provider's own services over "
            "routing through a public endpoint."
        ),
    },
    {
        "source": "azure_docs",
        "provider": "azure",
        "section": "Reservations and Hybrid Benefit",
        "text": (
            "Azure Reservations apply to a matching VM size family in a region for a one "
            "or three year term, and the discount is applied automatically to any "
            "matching running instance rather than to a specific machine. Azure Hybrid "
            "Benefit separately allows existing Windows Server and SQL Server licences "
            "with Software Assurance to be applied to cloud instances, which is often "
            "the larger saving for Windows estates. Review reservation utilization "
            "regularly: a reservation matching nothing still bills."
        ),
    },
    {
        "source": "azure_docs",
        "provider": "azure",
        "section": "Azure SQL Database Sizing",
        "text": (
            "Azure SQL Database in the vCore model is billed per vCore-hour, so the rate "
            "for a four vCore database is four times the single vCore meter — treating "
            "the meter as a per-instance price understates the bill fourfold. The "
            "serverless tier auto-pauses during inactivity and suits intermittent "
            "development databases, while provisioned compute suits steady production "
            "load. Check whether the storage or the compute tier is the actual cost "
            "driver before resizing, because they scale independently."
        ),
    },
    {
        "source": "aws_docs",
        "provider": "aws",
        "section": "Savings Plans vs Reserved Instances",
        "text": (
            "AWS Savings Plans commit to an hourly dollar amount of compute usage rather "
            "than to a specific instance type. Compute Savings Plans apply across "
            "instance families, regions, EC2, Fargate and Lambda, and are the more "
            "flexible option for a changing estate; EC2 Instance Savings Plans discount "
            "more deeply but pin you to one family in one region. Standard Reserved "
            "Instances discount the most and flex the least. Match the instrument to how "
            "confident you are in the shape of the workload a year from now, not just to "
            "the headline discount."
        ),
    },
    {
        "source": "aws_docs",
        "provider": "aws",
        "section": "EBS and Snapshot Hygiene",
        "text": (
            "Unattached EBS volumes continue to bill at their full provisioned size "
            "regardless of use, and are the single most common source of orphaned AWS "
            "spend after instances are terminated without their volumes. Older gp2 "
            "volumes can usually move to gp3, which decouples IOPS from capacity and is "
            "cheaper per GB at equivalent performance. Provisioned IOPS volumes bill for "
            "the IOPS whether or not they are consumed, so confirm the workload actually "
            "needs them before provisioning."
        ),
    },
    {
        "source": "gcp_docs",
        "provider": "gcp",
        "section": "Committed Use and Sustained Use Discounts",
        "text": (
            "GCP applies sustained use discounts automatically to instances that run for "
            "a large share of the month, with no commitment required, and these stack "
            "with the rest of the pricing model. Committed use discounts require a one or "
            "three year commitment to a quantity of vCPU and memory in a region and "
            "discount further. Because sustained use is automatic, the incremental "
            "benefit of committing is smaller on GCP than the equivalent step on other "
            "providers — model the difference against your actual runtime profile rather "
            "than assuming the headline commitment discount is all incremental."
        ),
    },
    {
        "source": "gcp_docs",
        "provider": "gcp",
        "section": "GKE Cost Controls",
        "text": (
            "In GKE, node auto-provisioning and the cluster autoscaler size the node "
            "pool, but pod resource requests are what actually drive that sizing: "
            "requests set far above real usage keep nodes running for capacity nothing "
            "consumes. Set requests from observed utilization and use limits to contain "
            "outliers. GKE Autopilot bills per pod resource request instead of per node, "
            "which removes the unused-node problem but makes accurate requests matter "
            "even more directly."
        ),
    },
    {
        "source": "finops_foundation",
        "provider": None,
        "section": "Kubernetes Cost Allocation",
        "text": (
            "A Kubernetes cluster arrives on the invoice as a small number of large "
            "compute line items, so cost per team or per service has to be reconstructed "
            "from inside the cluster by attributing node cost to pods by their resource "
            "requests over time, using namespace and labels as the allocation key. The "
            "gap between what pods request and what the nodes actually cost is cluster "
            "idle capacity, and reporting it separately rather than spreading it across "
            "teams is what makes the number actionable — it is the cluster operator's to "
            "fix, not the application team's."
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


def build_chunks(source: str = "all") -> list[dict[str, Any]]:
    """Expand the knowledge base into the chunks that would be stored."""
    chunks: list[dict[str, Any]] = []
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
    return chunks


async def ingest(source: str = "all", force: bool = False) -> int:
    """Ingest the knowledge base into ChromaDB. Returns the number of chunks stored.

    Skips when the collection already holds exactly the corpus we would write.
    It deliberately does *not* skip merely because the collection is non-empty:
    that made the corpus effectively immutable once ingested, so adding an
    entry to ``KNOWLEDGE_BASE`` never reached any environment that had already
    booted once — the corpus sat at its original size indefinitely while the
    source file said otherwise.
    """
    engine = get_rag_engine()
    chunks = build_chunks(source)
    existing = await engine.count()

    if existing and not force:
        if source == "all" and existing != len(chunks):
            logger.info(
                "RAG corpus changed ({} stored, {} expected); re-ingesting.",
                existing,
                len(chunks),
            )
            await engine.reset()
        else:
            logger.info("RAG collection already populated ({} chunks); skipping.", existing)
            return existing
    elif force and existing:
        await engine.reset()

    stored = await engine.add_documents(chunks)
    logger.info("RAG ingestion complete: {} chunks", stored)
    return stored


def main() -> None:
    parser = argparse.ArgumentParser(description="CloudPilot RAG ingestor")
    parser.add_argument("--source", default="all")
    parser.add_argument(
        "--force", action="store_true", help="Drop and re-ingest the whole corpus."
    )
    args = parser.parse_args()
    asyncio.run(ingest(args.source, force=args.force))


if __name__ == "__main__":
    main()
