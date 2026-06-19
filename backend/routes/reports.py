from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.report.scorer import agent_summary, severity_summary
from backend.storage import database as db
from backend.storage.models import AgentType, Severity

log = structlog.get_logger(__name__)

router = APIRouter(tags=["reports"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ReportMetaResponse(BaseModel):
    id: str
    run_id: str
    markdown_path: str
    json_path: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReportSummaryResponse(BaseModel):
    score: float
    verdict: str
    finding_counts_by_severity: dict[str, int]
    finding_counts_by_agent: dict[str, int]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/reports/{run_id}", response_model=ReportMetaResponse)
async def get_report_meta(run_id: str) -> ReportMetaResponse:
    report = await db.get_report_by_run(run_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"No report found for run {run_id!r}. The review may still be in progress.",
        )
    return ReportMetaResponse.from_orm(report)


@router.get("/reports/{run_id}/download")
async def download_report(run_id: str, format: str = "markdown") -> FileResponse:
    """Download the report in the requested format.

    Query param ``format`` accepts ``json`` or ``markdown`` (default).
    """
    report = await db.get_report_by_run(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No report found for run {run_id!r}")

    if format == "json":
        import os
        if not os.path.exists(report.json_path):
            raise HTTPException(status_code=404, detail="JSON report file not found on disk")
        return FileResponse(
            path=report.json_path,
            media_type="application/json",
            filename=f"code-review-{run_id}.json",
        )

    # default: markdown
    import os
    if not os.path.exists(report.markdown_path):
        raise HTTPException(status_code=404, detail="Markdown report file not found on disk")
    return FileResponse(
        path=report.markdown_path,
        media_type="text/markdown",
        filename=f"code-review-{run_id}.md",
    )


@router.get("/reports/{run_id}/download/json")
async def download_json_report(run_id: str) -> FileResponse:
    return await download_report(run_id, format="json")


@router.get("/reports/{run_id}/download/markdown")
async def download_markdown_report(run_id: str) -> FileResponse:
    return await download_report(run_id, format="markdown")


@router.get("/reports/{run_id}/summary", response_model=ReportSummaryResponse)
async def get_report_summary(run_id: str) -> ReportSummaryResponse:
    run = await db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    if run.production_score is None:
        raise HTTPException(
            status_code=409,
            detail=f"Run {run_id!r} has not completed yet (status: {run.status})",
        )

    # Fetch all findings for aggregation
    all_findings = await db.get_findings_by_run(run_id, limit=10_000)
    findings_dicts = [
        {"severity": f.severity.value, "agent": f.agent.value}
        for f in all_findings
    ]

    sev_counts = severity_summary(findings_dicts)
    agent_counts = agent_summary(findings_dicts)

    return ReportSummaryResponse(
        score=run.production_score,
        verdict=run.production_verdict or "UNKNOWN",
        finding_counts_by_severity=sev_counts,
        finding_counts_by_agent=agent_counts,
    )
