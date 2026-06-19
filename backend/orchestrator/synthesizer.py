"""synthesizer.py — merges, de-duplicates, and scores findings from all agents.

The Synthesizer is called as a plain LangGraph node (no LLM needed — it is
pure Python business logic).  It receives the fully-populated ReviewState and
returns a dict of updates that LangGraph merges back into the state.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from .state import ReviewState

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Severity ordering (higher index = more severe)
# ---------------------------------------------------------------------------
_SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

_SEVERITY_UP: dict[str, str] = {
    "info": "low",
    "low": "medium",
    "medium": "high",
    "high": "critical",
    "critical": "critical",  # already at max
}

_VERDICT_EMOJI: dict[str, str] = {
    "NOT PRODUCTION READY": "🔴",
    "NEEDS IMPROVEMENT": "🟡",
    "PRODUCTION READY": "🟢",
}


class Synthesizer:
    """Merge, de-duplicate, promote severity, score, and render the final report."""

    # ------------------------------------------------------------------
    # LangGraph node entry-point
    # ------------------------------------------------------------------

    async def synthesize(self, state: ReviewState) -> dict:
        """Called by the LangGraph synthesize_node.

        Returns a partial state dict consumed by operator.add / plain assignment.
        """
        run_id = state.get("run_id", "unknown")
        log.info("synthesizer.start", run_id=run_id)

        # 1. Collect raw findings from all three agents
        raw: list[dict] = []
        for field in ("bug_findings", "security_findings", "coverage_findings"):
            raw.extend(state.get(field) or [])  # type: ignore[arg-type]

        log.info(
            "synthesizer.raw_findings",
            run_id=run_id,
            total=len(raw),
            bug=len(state.get("bug_findings") or []),
            security=len(state.get("security_findings") or []),
            coverage=len(state.get("coverage_findings") or []),
        )

        # 2. Normalize / coerce field types
        normalized = [_normalize_finding(f) for f in raw]

        # 3. De-duplicate
        unique = self._deduplicate(normalized)
        log.info(
            "synthesizer.after_dedup",
            run_id=run_id,
            before=len(normalized),
            after=len(unique),
        )

        # 4. Cross-agent severity promotion
        promoted = self._promote_severity(unique)

        # 5. Sort: CRITICAL first
        promoted.sort(key=lambda f: _SEVERITY_RANK.get(f.get("severity", "info"), 0), reverse=True)

        # 6. Score
        score, verdict = self.calculate_score(promoted)

        # 7. Render Markdown
        repo_metadata = state.get("repo_metadata") or {}
        markdown = self._render_markdown(run_id, repo_metadata, promoted, score, verdict)

        # 8. Structured JSON report
        report_json = self._build_report_json(
            run_id=run_id,
            repo_metadata=repo_metadata,
            findings=promoted,
            score=score,
            verdict=verdict,
            raw_counts={
                "bug": len(state.get("bug_findings") or []),
                "security": len(state.get("security_findings") or []),
                "coverage": len(state.get("coverage_findings") or []),
            },
        )

        log.info(
            "synthesizer.complete",
            run_id=run_id,
            findings=len(promoted),
            score=score,
            verdict=verdict,
        )

        return {
            "all_findings": promoted,
            "production_score": score,
            "production_verdict": verdict,
            "report_markdown": markdown,
            "report_json": report_json,
            "progress_messages": [
                f"Synthesis complete: {len(promoted)} findings, score {score:.1f}/100 — {verdict}"
            ],
        }

    # ------------------------------------------------------------------
    # De-duplication
    # ------------------------------------------------------------------

    def _deduplicate(self, findings: list[dict]) -> list[dict]:
        """Remove near-duplicate findings.

        Two findings are considered duplicates when they share:
        - the same file_path (or both lack one), AND
        - overlapping line ranges (within ±5 lines), AND
        - similar title/description text (>60 % token overlap).
        """
        unique: list[dict] = []
        for candidate in findings:
            if not _is_duplicate(candidate, unique):
                unique.append(candidate)
        return unique

    # ------------------------------------------------------------------
    # Severity promotion
    # ------------------------------------------------------------------

    def _promote_severity(self, findings: list[dict]) -> list[dict]:
        """Upgrade severity by one level for areas flagged by 2+ agents.

        A "same area" is defined as same file_path and overlapping line ranges
        (within ±10 lines of each other).
        """
        promoted: list[dict] = []
        for idx, finding in enumerate(findings):
            peers = [
                other for j, other in enumerate(findings)
                if j != idx and _same_area(finding, other)
            ]
            agents_involved: set[str] = {finding.get("agent_type", "unknown")} | {
                p.get("agent_type", "unknown") for p in peers
            }
            if len(agents_involved) >= 2:
                current_sev = finding.get("severity", "info")
                new_sev = _SEVERITY_UP.get(current_sev, current_sev)
                if new_sev != current_sev:
                    log.debug(
                        "synthesizer.promote_severity",
                        file=finding.get("file_path"),
                        from_sev=current_sev,
                        to_sev=new_sev,
                        agents=sorted(agents_involved),
                    )
                    finding = {**finding, "severity": new_sev, "promoted": True}
            promoted.append(finding)
        return promoted

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def calculate_score(self, findings: list[dict]) -> tuple[float, str]:
        """Compute a 0–100 production-readiness score and a verdict string.

        Scoring rules
        -------------
        - Base score: 100
        - Any CRITICAL *security* finding: cap score at 30 (applied last)
        - Each CRITICAL finding:   -15
        - Each HIGH finding:       -8
        - Each MEDIUM finding:     -3
        - Each LOW finding:        -1
        - Score floor: 0

        Verdicts
        --------
        - 0–49:   "NOT PRODUCTION READY"
        - 50–74:  "NEEDS IMPROVEMENT"
        - 75–100: "PRODUCTION READY"
        """
        score: float = 100.0
        has_critical_security = False

        for f in findings:
            sev = f.get("severity", "info")
            agent = f.get("agent_type", "")
            if sev == "critical":
                score -= 15.0
                if agent == "security":
                    has_critical_security = True
            elif sev == "high":
                score -= 8.0
            elif sev == "medium":
                score -= 3.0
            elif sev == "low":
                score -= 1.0

        score = max(0.0, score)

        if has_critical_security:
            score = min(score, 30.0)

        if score >= 75:
            verdict = "PRODUCTION READY"
        elif score >= 50:
            verdict = "NEEDS IMPROVEMENT"
        else:
            verdict = "NOT PRODUCTION READY"

        return round(score, 1), verdict

    # ------------------------------------------------------------------
    # Markdown rendering
    # ------------------------------------------------------------------

    def _render_markdown(
        self,
        run_id: str,
        repo_metadata: dict,
        findings: list[dict],
        score: float,
        verdict: str,
    ) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        repo_name = repo_metadata.get("name", "Unknown Repository")
        repo_url = repo_metadata.get("url", "")
        branch = repo_metadata.get("default_branch", "HEAD")
        last_commit = repo_metadata.get("last_commit", {})
        commit_sha = last_commit.get("sha", "")
        commit_msg = last_commit.get("message", "")
        languages = repo_metadata.get("languages", {})
        total_files = repo_metadata.get("total_files", 0)

        emoji = _VERDICT_EMOJI.get(verdict, "⚪")

        # Counts by severity
        sev_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        agent_counts: dict[str, int] = {"bug": 0, "security": 0, "coverage": 0}
        for f in findings:
            sev = f.get("severity", "info")
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
            agent = f.get("agent_type", "")
            if agent in agent_counts:
                agent_counts[agent] += 1

        lines: list[str] = []

        # ---- Header ----
        lines += [
            f"# Code Review Report — {repo_name}",
            "",
            f"**Run ID:** `{run_id}`  ",
            f"**Date:** {now}  ",
        ]
        if repo_url:
            lines.append(f"**Repository:** {repo_url}  ")
        lines += [
            f"**Branch:** `{branch}`  ",
        ]
        if commit_sha:
            lines.append(f"**Commit:** `{commit_sha}` — {commit_msg}  ")
        lines.append("")

        # ---- Verdict banner ----
        lines += [
            "---",
            "",
            f"## {emoji} Production Verdict: {verdict}",
            "",
            f"**Production Readiness Score: {score:.1f} / 100**",
            "",
        ]

        # ---- Summary table ----
        lines += [
            "### Finding Summary",
            "",
            "| Severity | Count |",
            "|----------|-------|",
            f"| 🔴 Critical | {sev_counts['critical']} |",
            f"| 🟠 High | {sev_counts['high']} |",
            f"| 🟡 Medium | {sev_counts['medium']} |",
            f"| 🔵 Low | {sev_counts['low']} |",
            f"| ⚪ Info | {sev_counts['info']} |",
            f"| **Total** | **{len(findings)}** |",
            "",
            "### Findings by Agent",
            "",
            "| Agent | Findings |",
            "|-------|----------|",
            f"| Bug Detector | {agent_counts['bug']} |",
            f"| Security Scanner | {agent_counts['security']} |",
            f"| Coverage Analyst | {agent_counts['coverage']} |",
            "",
        ]

        # ---- Repository info ----
        if languages or total_files:
            lines += [
                "### Repository Info",
                "",
                f"- **Total source files:** {total_files}",
            ]
            if languages:
                lang_str = ", ".join(
                    f"`{ext}` ({count})"
                    for ext, count in sorted(languages.items(), key=lambda x: -x[1])[:8]
                )
                lines.append(f"- **Languages:** {lang_str}")
            lines.append("")

        lines.append("---")
        lines.append("")

        # ---- Findings sections grouped by severity ----
        severity_order = ["critical", "high", "medium", "low", "info"]
        severity_labels = {
            "critical": "🔴 Critical Findings",
            "high": "🟠 High Severity Findings",
            "medium": "🟡 Medium Severity Findings",
            "low": "🔵 Low Severity Findings",
            "info": "⚪ Informational Findings",
        }

        for sev in severity_order:
            sev_findings = [f for f in findings if f.get("severity") == sev]
            if not sev_findings:
                continue

            lines += [f"## {severity_labels[sev]}", ""]

            for i, finding in enumerate(sev_findings, start=1):
                title = finding.get("title", "Untitled Finding")
                agent = finding.get("agent_type", "unknown").title()
                file_path = finding.get("file_path") or ""
                line_start = finding.get("line_start")
                line_end = finding.get("line_end")
                description = finding.get("description", "")
                code_snippet = finding.get("code_snippet") or ""
                suggestion = finding.get("suggestion") or ""
                cwe_id = finding.get("cwe_id") or ""
                promoted = finding.get("promoted", False)

                # Location string
                location = ""
                if file_path:
                    location = f"`{file_path}`"
                    if line_start is not None:
                        location += f" line {line_start}"
                        if line_end is not None and line_end != line_start:
                            location += f"–{line_end}"

                promoted_badge = " ⬆️ *severity promoted (corroborated by multiple agents)*" if promoted else ""

                lines += [f"### {i}. {title}"]
                lines += [f"**Agent:** {agent} | **Severity:** `{sev.upper()}`{promoted_badge}"]
                if cwe_id:
                    lines.append(f"**CWE:** [{cwe_id}](https://cwe.mitre.org/data/definitions/{cwe_id.replace('CWE-', '')}.html)")
                if location:
                    lines.append(f"**Location:** {location}")
                lines.append("")
                if description:
                    lines += [description, ""]
                if code_snippet:
                    lang = _guess_lang_from_path(file_path)
                    lines += [f"```{lang}", code_snippet.strip(), "```", ""]
                if suggestion:
                    lines += ["**Suggestion:**", "", suggestion, ""]
                lines.append("---")
                lines.append("")

        if not findings:
            lines += [
                "## No Issues Found",
                "",
                "All three agents completed their analysis and found no issues.",
                "This repository appears to be in excellent shape.",
                "",
                "---",
                "",
            ]

        # ---- Footer ----
        lines += [
            "## Report Footer",
            "",
            f"Generated by **AI Code Review System** on {now}  ",
            f"Run ID: `{run_id}`  ",
            "Agents: Bug Detector · Security Scanner · Coverage Analyst  ",
            "Scoring: Base 100; CRITICAL −15, HIGH −8, MEDIUM −3, LOW −1; "
            "critical security finding caps score at 30.",
            "",
        ]

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Structured JSON report
    # ------------------------------------------------------------------

    def _build_report_json(
        self,
        run_id: str,
        repo_metadata: dict,
        findings: list[dict],
        score: float,
        verdict: str,
        raw_counts: dict[str, int],
    ) -> dict:
        sev_counts: dict[str, int] = {}
        for f in findings:
            sev = f.get("severity", "info")
            sev_counts[sev] = sev_counts.get(sev, 0) + 1

        return {
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "repository": repo_metadata,
            "score": score,
            "verdict": verdict,
            "finding_counts": {
                "total": len(findings),
                "by_severity": sev_counts,
                "by_agent": raw_counts,
            },
            "findings": findings,
        }


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _normalize_finding(f: dict) -> dict:
    """Coerce field types and ensure required keys exist."""
    sev = str(f.get("severity", "info")).lower()
    if sev not in _SEVERITY_RANK:
        sev = "info"

    return {
        "title": str(f.get("title") or "Untitled"),
        "description": str(f.get("description") or ""),
        "severity": sev,
        "file_path": f.get("file_path") or None,
        "line_start": _to_int(f.get("line_start")),
        "line_end": _to_int(f.get("line_end")),
        "code_snippet": f.get("code_snippet") or None,
        "suggestion": f.get("suggestion") or None,
        "cwe_id": f.get("cwe_id") or None,
        "agent_type": str(f.get("agent_type") or "unknown"),
        "promoted": bool(f.get("promoted", False)),
    }


def _to_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _token_set(text: str) -> set[str]:
    """Return a set of lowercase alphanumeric tokens from *text*."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _token_overlap_ratio(a: str, b: str) -> float:
    """Jaccard similarity between two strings' token sets."""
    set_a = _token_set(a)
    set_b = _token_set(b)
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def _same_area(a: dict, b: dict) -> bool:
    """True when two findings refer to the same file region (within ±10 lines)."""
    if a.get("file_path") != b.get("file_path"):
        return False
    a_start = a.get("line_start")
    b_start = b.get("line_start")
    if a_start is None or b_start is None:
        # Without line numbers, treat same-file findings as same area
        return a.get("file_path") is not None
    return abs(a_start - b_start) <= 10


def _is_duplicate(candidate: dict, existing: list[dict]) -> bool:
    """Return True if *candidate* is substantially similar to any finding in *existing*."""
    c_file = candidate.get("file_path")
    c_start = candidate.get("line_start")
    c_title = candidate.get("title", "")
    c_desc = candidate.get("description", "")

    for e in existing:
        e_file = e.get("file_path")
        e_start = e.get("line_start")

        # Files must match (or both be None)
        if c_file != e_file:
            continue

        # Line proximity check (within ±5 lines)
        if c_start is not None and e_start is not None:
            if abs(c_start - e_start) > 5:
                continue

        # Text similarity check
        title_sim = _token_overlap_ratio(c_title, e.get("title", ""))
        desc_sim = _token_overlap_ratio(c_desc, e.get("description", ""))
        combined = (title_sim + desc_sim) / 2.0

        if combined >= 0.60:
            return True

    return False


def _guess_lang_from_path(file_path: str | None) -> str:
    """Return a fenced-code-block language hint from a file extension."""
    if not file_path:
        return ""
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".cpp": "cpp",
        ".c": "c",
        ".cs": "csharp",
        ".rb": "ruby",
        ".php": "php",
        ".sh": "bash",
        ".sql": "sql",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
    }
    suffix = file_path[file_path.rfind("."):].lower() if "." in file_path else ""
    return ext_map.get(suffix, "")
