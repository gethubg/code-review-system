from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, HttpUrl, model_validator

from backend.storage import database as db
from backend.storage.models import ReviewRun, RunStatus
from backend.ws.progress import push_progress

log = structlog.get_logger(__name__)

router = APIRouter(tags=["review"])

_REPORTS_DIR = os.environ.get("REPORTS_DIR", "./reports")


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ReviewRequest(BaseModel):
    git_url: str


class ReviewRunResponse(BaseModel):
    run_id: str = ""
    id: str = ""
    status: str
    git_url: str
    repo_name: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    production_score: Optional[float] = None
    production_verdict: Optional[str] = None
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def sync_run_id(self) -> "ReviewRunResponse":
        if self.id and not self.run_id:
            self.run_id = self.id
        elif self.run_id and not self.id:
            self.id = self.run_id
        return self


class RunListResponse(BaseModel):
    items: list[ReviewRunResponse]
    total: int
    skip: int
    limit: int


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


def _extract_repo_name(git_url: str) -> str:
    """Derive a human-readable repo name from a git URL."""
    name = git_url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name or git_url


async def _run_review(run_id: str, git_url: str) -> None:
    """Execute the full review pipeline in the background."""
    # Import here to avoid circular imports and defer heavy loading
    from backend.orchestrator.graph import build_graph
    from backend.report.formatter import ReportFormatter
    from backend.storage.database import (
        create_finding,
        create_report,
        update_run,
    )

    try:
        await update_run(run_id, status=RunStatus.RUNNING)
        await push_progress(run_id, "Review started — cloning repository")

        graph = build_graph()

        repo_metadata: dict = {}
        # Final merged findings come from synthesize_node
        synth_findings: list[dict] = []
        synth_score: float = 0.0
        synth_verdict: str = "NOT PRODUCTION READY"
        synth_markdown: str = ""
        synth_json: dict = {}

        openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o")

        initial_state = {
            "run_id": run_id,
            "git_url": git_url,
            "repo_path": "",
            "repo_metadata": {},
            "openai_api_key": openai_api_key,
            "openai_model": openai_model,
            "chunks": [],
            "files_analyzed": 0,
            "bug_findings": [],
            "security_findings": [],
            "coverage_findings": [],
            "all_findings": [],
            "production_score": 0.0,
            "production_verdict": "",
            "report_markdown": "",
            "report_json": {},
            "progress_messages": [f"Starting review for {git_url}"],
            "error": None,
        }

        async for event in graph.astream(initial_state, stream_mode="updates"):
            for node_name, node_output in event.items():
                if node_name == "ingest_node":
                    repo_metadata = node_output.get("repo_metadata", {})
                    file_count = repo_metadata.get("total_files", repo_metadata.get("file_count", 0))
                    await push_progress(run_id, f"Ingestion complete — {file_count} files indexed")

                elif node_name in ("bug_node", "security_node", "coverage_node"):
                    # Each agent stores into its own key; count from that key
                    findings_key = node_name.replace("_node", "_findings")
                    node_findings = node_output.get(findings_key, [])
                    agent_label = node_name.replace("_node", "").capitalize()
                    await push_progress(
                        run_id,
                        f"{agent_label} agent complete — {len(node_findings)} finding(s)",
                    )

                elif node_name == "synthesize_node":
                    # Synthesizer has the merged, deduped, promoted findings
                    synth_findings = node_output.get("all_findings", [])
                    synth_score = node_output.get("production_score", 0.0)
                    synth_verdict = node_output.get("production_verdict", "NOT PRODUCTION READY")
                    synth_markdown = node_output.get("report_markdown", "")
                    synth_json = node_output.get("report_json", {})
                    await push_progress(
                        run_id,
                        f"Synthesis complete — {len(synth_findings)} finding(s), score {synth_score:.1f}/100",
                    )

        # Persist findings to DB
        from backend.storage.models import AgentType, Severity

        for f in synth_findings:
            raw_agent = f.get("agent_type") or f.get("agent", "bug")
            raw_sev = f.get("severity", "low")
            # Coerce to valid enum values
            try:
                agent_enum = AgentType(raw_agent)
            except ValueError:
                agent_enum = AgentType.BUG
            try:
                sev_enum = Severity(raw_sev)
            except ValueError:
                sev_enum = Severity.LOW

            await create_finding(
                run_id=run_id,
                agent=agent_enum,
                severity=sev_enum,
                title=f.get("title", "Untitled finding"),
                description=f.get("description", ""),
                file_path=f.get("file_path"),
                line_start=f.get("line_start"),
                line_end=f.get("line_end"),
                code_snippet=f.get("code_snippet"),
                suggestion=f.get("suggestion"),
                cwe_id=f.get("cwe_id"),
            )

        score = synth_score
        verdict = synth_verdict

        # Build and save report files — prefer synthesizer output, fall back to local build
        formatter = ReportFormatter(_REPORTS_DIR)

        if synth_markdown:
            markdown = synth_markdown
        else:
            markdown = _build_markdown(synth_json)

        report_dict = synth_json if synth_json else {
            "meta": {"run_id": run_id},
            "score": score,
            "verdict": verdict,
            "all_findings": synth_findings,
        }

        md_path = await formatter.save_markdown(run_id, markdown)
        json_path = await formatter.save_json(run_id, report_dict)

        await create_report(run_id=run_id, markdown_path=md_path, json_path=json_path)

        await update_run(
            run_id,
            status=RunStatus.COMPLETED,
            completed_at=datetime.utcnow(),
            production_score=score,
            production_verdict=verdict,
        )

        await push_progress(
            run_id,
            f"Review complete — score {score:.1f}/100 — {verdict}",
            msg_type="complete",
        )
        log.info("review_completed", run_id=run_id, score=score, verdict=verdict)

    except Exception as exc:
        log.exception("review_failed", run_id=run_id, error=str(exc))
        await update_run(
            run_id,
            status=RunStatus.FAILED,
            completed_at=datetime.utcnow(),
            error_message=str(exc),
        )
        await push_progress(run_id, f"Review failed: {exc}", msg_type="error")


def _build_markdown(report: dict) -> str:
    """Convert the structured report dict to a Markdown document."""
    meta = report.get("meta", {})
    repo = report.get("repository", {})
    lines: list[str] = [
        f"# Code Review Report",
        f"",
        f"**Run ID:** {meta.get('run_id')}  ",
        f"**Generated:** {meta.get('generated_at')}  ",
        f"**Repository:** {repo.get('url')}  ",
        f"",
        f"## Score",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Production Score | {report.get('score', 0):.1f} / 100 |",
        f"| Verdict | **{report.get('verdict', 'N/A')}** |",
        f"",
        f"## Finding Counts",
        f"",
    ]

    counts = report.get("findings_by_severity", {})
    lines += [
        "| Severity | Count |",
        "|----------|-------|",
    ]
    for sev, cnt in counts.items():
        lines.append(f"| {sev.upper()} | {cnt} |")

    lines += ["", "## Findings", ""]

    for finding in report.get("all_findings", []):
        loc = ""
        if finding.get("file_path"):
            loc = f"`{finding['file_path']}`"
            if finding.get("line_start"):
                loc += f" line {finding['line_start']}"
        lines += [
            f"### [{finding.get('severity', '').upper()}] {finding.get('title', '')}",
            f"",
            f"**Agent:** {finding.get('agent', '')}  ",
            f"**Location:** {loc or 'N/A'}  ",
            f"",
            finding.get("description", ""),
            f"",
        ]
        if finding.get("suggestion"):
            lines += [f"**Suggestion:** {finding['suggestion']}", ""]
        if finding.get("code_snippet"):
            lines += [f"```\n{finding['code_snippet']}\n```", ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/review", response_model=ReviewRunResponse, status_code=202)
async def create_review(
    body: ReviewRequest,
    background_tasks: BackgroundTasks,
) -> ReviewRun:
    repo_name = _extract_repo_name(body.git_url)
    run = await db.create_run(git_url=body.git_url, repo_name=repo_name)
    background_tasks.add_task(_run_review, run.id, body.git_url)
    log.info("review_queued", run_id=run.id, repo_name=repo_name)
    return run


@router.get("/runs", response_model=RunListResponse)
async def list_runs(skip: int = 0, limit: int = 20) -> RunListResponse:
    if limit > 100:
        limit = 100
    runs, total = await db.list_runs(offset=skip, limit=limit)
    return RunListResponse(
        items=[ReviewRunResponse.from_orm(r) for r in runs],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/runs/{run_id}", response_model=ReviewRunResponse)
async def get_run(run_id: str) -> ReviewRun:
    run = await db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return run
