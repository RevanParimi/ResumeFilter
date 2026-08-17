"""Data Engineering domain model — the second domain (FR-18).

Proves the plug-in architecture: one module, one ``@register_domain``, zero
graph changes. Encodes how a senior data engineer reasons about whether a
claim COHERES with the tooling, scale, and operational discipline the work
would actually have required.

Three seed rules: batch ETL, streaming, warehouse/modeling.
"""

from __future__ import annotations

from typing import Optional

from app.domains.base import DomainModel, Rule, register_domain
from app.domains.rules import SignalRule, present as _present_kw
from app.schemas.claims import CandidateContext

# Claim-type vocabulary owned by this domain.
CLAIM_TYPES = [
    "etl_pipeline",
    "streaming",
    "warehouse_modeling",
    "orchestration",
    "data_quality",
    "generic",
]

# Distributed / heavy-data tooling: if someone claims massive scale, at least
# one of these (or an equivalent) should be named somewhere.
_DISTRIBUTED_TOOLING = (
    "spark", "flink", "hadoop", "hive", "presto", "trino", "databricks",
    "emr", "dataproc", "bigquery", "snowflake", "redshift", "clickhouse",
    "kafka", "kinesis", "beam", "dask", "ray",
)
_SCALE_TELLS = (
    "petabyte", "pb of", "billions of rows", "billions of records",
    "trillions", "billions of events",
)


def _scale_without_tooling(
    hay: str, ctx: CandidateContext
) -> Optional[tuple[float, str, list[str]]]:
    """Massive-scale claims with no distributed tooling named are a strong tell."""
    if _present_kw(hay, _SCALE_TELLS) and not _present_kw(hay, _DISTRIBUTED_TOOLING):
        return (
            -0.30,
            "Claims petabyte/billions-scale processing but names no distributed "
            "engine, warehouse, or broker that would make it possible — a strong "
            "fabrication tell.",
            ["Which engine/cluster processed that volume, what was the cluster size, "
             "and what did a typical run cost?"],
        )
    return None


RULES: list[Rule] = [
    SignalRule(
        id="data_eng.etl_pipeline.coherence",
        claim_types=("etl_pipeline",),
        description="A real batch ETL pipeline implies stated volume, named tooling, "
        "an incremental/backfill strategy, and monitoring.",
        categories={
            "data_volume": (
                "gb", "tb", "terabyte", "gigabyte", "rows", "records", "events",
                "tables", "files", "daily", "hourly",
            ),
            "named_tooling": (
                "spark", "airflow", "dbt", "dagster", "prefect", "glue", "emr",
                "databricks", "fivetran", "python", "sql", "pandas",
            ),
            "incremental_backfill": (
                "incremental", "backfill", "cdc", "change data capture", "upsert",
                "merge", "partition", "watermark", "idempotent",
            ),
            "monitoring_slas": (
                "monitor", "alert", "sla", "data quality", "great expectations",
                "freshness", "lineage", "observability", "on-call",
            ),
        },
        probes={
            "data_volume": "How much data per run (rows/GB) and how long did a run take?",
            "named_tooling": "Which engine and orchestrator ran the pipeline, and why "
            "those?",
            "incremental_backfill": "How did you handle late data, reruns, and "
            "backfills without duplicates?",
            "monitoring_slas": "How did you detect a bad or late load before "
            "downstream consumers did?",
        },
        contradiction=_scale_without_tooling,
    ),
    SignalRule(
        id="data_eng.streaming.coherence",
        claim_types=("streaming",),
        description="Production streaming implies a named broker, a processing "
        "engine, explicit delivery semantics, and lag/throughput handling.",
        categories={
            "broker": (
                "kafka", "kinesis", "pub/sub", "pubsub", "event hubs", "pulsar",
                "rabbitmq", "sqs",
            ),
            "processing_engine": (
                "flink", "spark streaming", "structured streaming", "beam",
                "kafka streams", "ksql", "materialize", "consumer",
            ),
            "delivery_semantics": (
                "exactly-once", "exactly once", "at-least-once", "at least once",
                "idempotent", "dedup", "checkpoint", "offset",
            ),
            "lag_throughput": (
                "lag", "throughput", "events/sec", "events per second", "msg/s",
                "backpressure", "dead-letter", "dlq", "partition",
            ),
        },
        probes={
            "broker": "Which broker, how many partitions, and how did you pick the "
            "partition key?",
            "processing_engine": "What consumed the stream and how was state "
            "checkpointed?",
            "delivery_semantics": "What delivery guarantee did you actually provide, "
            "and how did you handle duplicates?",
            "lag_throughput": "What was steady-state throughput and what happened "
            "when consumers fell behind?",
        },
    ),
    SignalRule(
        id="data_eng.warehouse.coherence",
        claim_types=("warehouse_modeling",),
        description="Warehouse ownership implies a named platform, a modeling "
        "approach, testing in CI, and cost/performance tuning.",
        categories={
            "warehouse_platform": (
                "snowflake", "bigquery", "redshift", "databricks", "synapse",
                "clickhouse", "duckdb", "postgres",
            ),
            "modeling_approach": (
                "star schema", "dimensional", "kimball", "data vault", "dbt",
                "medallion", "marts", "fact table", "dimension",
            ),
            "testing_ci": (
                "dbt test", "tests in ci", "unit test", "data test", "ci/cd",
                "great expectations", "contract", "schema change",
            ),
            "cost_performance": (
                "cost", "spend", "clustering", "partition", "materialized",
                "query performance", "warehouse size", "credits", "optimiz",
            ),
        },
        probes={
            "warehouse_platform": "Which warehouse, what size/tier, and roughly what "
            "was the monthly spend?",
            "modeling_approach": "Walk me through one mart: sources, layers, and the "
            "grain of the main fact table.",
            "testing_ci": "What broke when someone changed an upstream schema — how "
            "was it caught?",
            "cost_performance": "Name one query or model you made cheaper/faster and "
            "how.",
        },
    ),
]


@register_domain
class DataEngDomain(DomainModel):
    key = "data_eng"
    display_name = "Data Engineering"

    @property
    def rules(self) -> list[Rule]:
        return RULES

    @property
    def claim_types(self) -> list[str]:
        return list(CLAIM_TYPES)

    def heuristic_type_hints(self) -> list[tuple[str, tuple[str, ...]]]:
        # Ordered: most specific first (a streaming line often also says
        # "ingestion", so streaming must win over etl_pipeline).
        return [
            ("streaming", ("streaming", "stream processing", "kafka", "kinesis",
                           "flink", "real-time", "real time", "pub/sub", "event-driven")),
            ("warehouse_modeling", ("warehouse", "snowflake", "bigquery", "redshift",
                                    "dbt", "star schema", "dimensional", "data model")),
            ("etl_pipeline", ("etl", "elt", "pipeline", "batch", "ingestion",
                              "data processing", "processed", "spark", "airflow")),
            ("orchestration", ("orchestrat", "dag", "schedule", "dagster", "prefect")),
            ("data_quality", ("data quality", "great expectations", "validation",
                              "lineage", "observability", "freshness")),
        ]

    def extraction_guidance(self) -> str:
        return (
            "You are extracting atomic, checkable data engineering claims from a "
            "resume. For each claim, classify claim_type as one of: "
            f"{', '.join(CLAIM_TYPES)}. Set specificity to 'vague' (no concrete "
            "numbers/names), 'moderate', or 'specific' (named tools, data volumes, "
            "SLAs, costs). If a claim points to a GitHub repo or portfolio URL the "
            "candidate shared, attach it as external_anchor. Also infer "
            "candidate_context: role_title, seniority, years_experience, and "
            "employer_type (tier1_ai_lab | product_company | services_firm | startup | "
            "academia | unknown). Do NOT invent facts not present in the resume."
        )

    def plausibility_system_prompt(self, context: CandidateContext) -> str:
        return (
            "You are a senior data engineer assessing whether a resume claim COHERES "
            "with the tooling, scale, and operational discipline the work would "
            "actually have required. You do NOT keyword-match. You reason about "
            "whether the claim hangs together.\n\n"
            "Candidate context:\n"
            f"  role: {context.role_title or 'unknown'} ({context.seniority or '?'})\n"
            f"  experience: {context.years_experience or '?'} yrs\n"
            f"  employer: {context.employer_name or '?'} "
            f"[{context.employer_type or 'unknown'}]\n\n"
            "For the given claim, decide: what would a genuine version exhibit "
            "(expected_signals)? Which are absent (missing_signals)? Is there a "
            "contradiction with the claimed scale or the candidate's likely access "
            "(e.g. petabyte-scale processing with no distributed engine named)? "
            "Output a coherence score 0..1, a confidence 0..1, and concise "
            "reasoning. Be CONSERVATIVE: when evidence is thin, lower confidence "
            "rather than asserting fabrication. This is advisory input for a human "
            "reviewer, never an automated rejection."
        )

    def probe_guidance(self) -> str:
        return (
            "Write 1-3 targeted follow-up questions that a genuine practitioner "
            "answers instantly but a fabricator cannot survive. Anchor each question "
            "to a specific missing signal (volumes and run times, partitioning and "
            "backfill strategy, delivery semantics, warehouse cost levers, what broke "
            "in production). Avoid yes/no questions and avoid anything answerable by "
            "restating the resume."
        )
