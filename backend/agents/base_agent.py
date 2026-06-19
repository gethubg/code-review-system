from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod

import structlog
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, ValidationError

log = structlog.get_logger()


class AgentFinding(BaseModel):
    title: str
    description: str
    severity: str  # critical|high|medium|low|info
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    code_snippet: str | None = None
    suggestion: str | None = None
    cwe_id: str | None = None  # for security findings


class AgentResult(BaseModel):
    agent_type: str
    findings: list[AgentFinding]
    summary: str
    files_analyzed: int
    duration_seconds: float


class BaseReviewAgent(ABC):
    def __init__(
        self,
        openai_api_key: str,
        model: str = "gpt-4o",
        temperature: float = 0.1,
    ) -> None:
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=openai_api_key,
        )
        self.tools: list[BaseTool] = self._build_tools()

    @abstractmethod
    def _build_tools(self) -> list[BaseTool]: ...

    @abstractmethod
    def _system_prompt(self) -> str: ...

    @abstractmethod
    def agent_type(self) -> str: ...

    async def analyze(
        self,
        chunks: list[dict],
        repo_path: str,
        repo_metadata: dict,
        peer_findings: list[AgentFinding] | None = None,
    ) -> AgentResult:
        start = time.monotonic()
        agent_type = self.agent_type()
        log.info("agent.analyze.start", agent_type=agent_type, chunks=len(chunks))

        unique_files: set[str] = {c["file_path"] for c in chunks if "file_path" in c}
        files_analyzed = len(unique_files)

        peer_context = ""
        if peer_findings:
            peer_context = (
                "\n\nFindings from peer agents (use to elevate severity if corroborated):\n"
                + json.dumps([f.model_dump() for f in peer_findings], indent=2)
            )

        file_list = "\n".join(sorted(unique_files)) if unique_files else "(none)"
        question = (
            f"Analyze the repository at path: {repo_path}\n"
            f"Repository metadata: {json.dumps(repo_metadata)}\n"
            f"Files to focus on:\n{file_list}"
            f"{peer_context}\n\n"
            "When you have enough information, return ONLY a JSON array of finding objects "
            "as your final message. Each object must have these fields: "
            "title, description, severity (critical|high|medium|low|info), "
            "file_path, line_start, line_end, code_snippet, suggestion, cwe_id. "
            "Use null for missing optional fields. "
            "If there are no findings, return an empty JSON array []."
        )

        findings: list[AgentFinding] = []
        summary = "Analysis complete."

        try:
            graph = create_react_agent(
                model=self.llm,
                tools=self.tools,
                prompt=self._system_prompt(),
            )
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=question)]},
                config={"recursion_limit": 30},
            )
            # Last message from the agent is the final answer
            messages = result.get("messages", [])
            raw_output = messages[-1].content if messages else ""
            findings = self._parse_findings(raw_output)
            summary = self._build_summary(findings, files_analyzed)
        except Exception as exc:
            log.error("agent.analyze.error", agent_type=agent_type, error=str(exc))
            summary = f"Analysis failed: {exc}"

        duration = time.monotonic() - start
        log.info(
            "agent.analyze.complete",
            agent_type=agent_type,
            findings=len(findings),
            duration=round(duration, 2),
        )
        return AgentResult(
            agent_type=agent_type,
            findings=findings,
            summary=summary,
            files_analyzed=files_analyzed,
            duration_seconds=round(duration, 3),
        )

    def _parse_findings(self, raw_output: str) -> list[AgentFinding]:
        if not raw_output or raw_output.strip() == "[]":
            return []

        # Extract the first JSON array from the output
        match = re.search(r"\[.*\]", raw_output, re.DOTALL)
        if not match:
            log.warning("agent.parse_findings.no_json_array", raw=raw_output[:200])
            return []

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as exc:
            log.warning("agent.parse_findings.json_error", error=str(exc))
            return []

        findings: list[AgentFinding] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            sev = str(item.get("severity", "info")).lower()
            if sev not in {"critical", "high", "medium", "low", "info"}:
                sev = "info"
            item["severity"] = sev
            try:
                findings.append(AgentFinding(**item))
            except (ValidationError, TypeError) as exc:
                log.warning("agent.parse_findings.validation_error", error=str(exc))

        return findings

    def _build_summary(self, findings: list[AgentFinding], files_analyzed: int) -> str:
        if not findings:
            return f"No issues found across {files_analyzed} file(s)."
        counts: dict[str, int] = {}
        for f in findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        parts = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        return f"Found {len(findings)} issue(s) across {files_analyzed} file(s): {parts}."
