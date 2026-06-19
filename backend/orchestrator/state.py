from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class ReviewState(TypedDict):
    # ---------------------------------------------------------------------------
    # Input — supplied by the caller before graph execution
    # ---------------------------------------------------------------------------
    run_id: str
    git_url: str

    # Set by ingest_node after cloning; passed to agents and synthesizer
    repo_path: str
    repo_metadata: dict

    # OpenAI credentials forwarded to each agent/embedder
    openai_api_key: str
    openai_model: str  # e.g. "gpt-4o"

    # ---------------------------------------------------------------------------
    # Ingestion outputs
    # ---------------------------------------------------------------------------
    chunks: list[dict]      # raw chunk dicts from CodeChunker (no embeddings)
    files_analyzed: int     # number of unique source files chunked

    # ---------------------------------------------------------------------------
    # Per-agent findings
    # operator.add merges lists from parallel fan-in branches so that every
    # agent's output is appended rather than overwritten.
    # ---------------------------------------------------------------------------
    bug_findings: Annotated[list, operator.add]
    security_findings: Annotated[list, operator.add]
    coverage_findings: Annotated[list, operator.add]

    # ---------------------------------------------------------------------------
    # Synthesizer outputs
    # ---------------------------------------------------------------------------
    all_findings: list[dict]        # de-duplicated, severity-promoted findings
    production_score: float         # 0-100
    production_verdict: str         # "NOT PRODUCTION READY" | "NEEDS IMPROVEMENT" | "PRODUCTION READY"
    report_markdown: str            # full Markdown report
    report_json: dict               # structured report as a dict

    # ---------------------------------------------------------------------------
    # Progress & error tracking
    # operator.add lets every node append its own messages without overwriting.
    # ---------------------------------------------------------------------------
    progress_messages: Annotated[list[str], operator.add]
    error: str | None
