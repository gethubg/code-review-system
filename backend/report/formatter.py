from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiofiles
import structlog

log = structlog.get_logger(__name__)


class ReportFormatter:
    """Persists review reports to the filesystem as JSON and Markdown files."""

    def __init__(self, reports_dir: str) -> None:
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Save helpers
    # ------------------------------------------------------------------

    async def save_markdown(self, run_id: str, markdown: str) -> str:
        """Write *markdown* to ``<reports_dir>/<run_id>.md`` and return the path."""
        path = self.reports_dir / f"{run_id}.md"
        async with aiofiles.open(path, "w", encoding="utf-8") as fh:
            await fh.write(markdown)
        log.info("markdown_report_saved", run_id=run_id, path=str(path))
        return str(path)

    async def save_json(self, run_id: str, report_dict: dict) -> str:
        """Write *report_dict* as indented JSON and return the path."""
        path = self.reports_dir / f"{run_id}.json"
        async with aiofiles.open(path, "w", encoding="utf-8") as fh:
            await fh.write(json.dumps(report_dict, indent=2, default=str))
        log.info("json_report_saved", run_id=run_id, path=str(path))
        return str(path)

    # ------------------------------------------------------------------
    # Report construction
    # ------------------------------------------------------------------

    def build_json_report(
        self,
        run_id: str,
        repo_metadata: dict,
        findings: list[dict],
        score: float,
        verdict: str,
        run: Any,  # ReviewRun ORM object — avoid circular import
    ) -> dict:
        """Build a fully structured JSON report dictionary."""
        from backend.report.scorer import agent_summary, severity_summary

        sev_counts = severity_summary(findings)
        ag_counts = agent_summary(findings)

        # Group findings by severity
        by_severity: dict[str, list[dict]] = {
            "critical": [],
            "high": [],
            "medium": [],
            "low": [],
            "info": [],
        }
        for f in findings:
            key = f.get("severity", "info").lower()
            by_severity.setdefault(key, []).append(f)

        # Group findings by agent
        by_agent: dict[str, list[dict]] = {}
        for f in findings:
            key = f.get("agent", "unknown").lower()
            by_agent.setdefault(key, []).append(f)

        report: dict = {
            "meta": {
                "run_id": run_id,
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
                "tool": "Code Review System",
                "version": "0.1.0",
            },
            "repository": {
                "url": getattr(run, "git_url", repo_metadata.get("url", "")),
                "name": getattr(run, "repo_name", repo_metadata.get("name", "")),
                "file_count": repo_metadata.get("file_count", 0),
                "language_breakdown": repo_metadata.get("language_breakdown", {}),
            },
            "score": round(score, 2),
            "verdict": verdict,
            "findings_by_severity": sev_counts,
            "findings_by_agent": ag_counts,
            "all_findings": findings,
            "findings_detail": {
                "by_severity": by_severity,
                "by_agent": by_agent,
            },
        }

        return report
