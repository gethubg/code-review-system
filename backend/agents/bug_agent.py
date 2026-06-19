from __future__ import annotations

import os
import subprocess
from pathlib import Path

import structlog
from langchain_core.tools import Tool

from .base_agent import AgentFinding, AgentResult, BaseReviewAgent

log = structlog.get_logger()

_MAX_READ_BYTES = 32_768  # 32 KB per file read to avoid token overflow
_MAX_CHUNKS = 50


class BugAgent(BaseReviewAgent):
    """Detects bugs, anti-patterns, and code quality issues."""

    def agent_type(self) -> str:
        return "bug"

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _build_tools(self) -> list[Tool]:
        return [
            Tool(
                name="read_file_contents",
                func=self._tool_read_file,
                description=(
                    "Read the contents of a file. "
                    "Input: absolute or relative file path. "
                    "Output: file text (truncated at 32 KB)."
                ),
            ),
            Tool(
                name="grep_in_repo",
                func=self._tool_grep,
                description=(
                    "Search for a regex pattern in the repository. "
                    "Input: '<repo_path>||<pattern>' "
                    "(pipe-separated repo path and grep pattern). "
                    "Output: matching lines with filenames."
                ),
            ),
            Tool(
                name="list_files",
                func=self._tool_list_files,
                description=(
                    "List source files in a directory (recursive). "
                    "Input: directory path. "
                    "Output: newline-separated list of file paths."
                ),
            ),
            Tool(
                name="get_file_stats",
                func=self._tool_file_stats,
                description=(
                    "Return line count and size in bytes for a file. "
                    "Input: file path. "
                    "Output: JSON-like string with stats."
                ),
            ),
        ]

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    @staticmethod
    def _tool_read_file(file_path: str) -> str:
        path = Path(file_path.strip())
        if not path.exists():
            return f"ERROR: file not found: {file_path}"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            if len(text) > _MAX_READ_BYTES:
                text = text[:_MAX_READ_BYTES] + "\n... [truncated]"
            return text
        except Exception as exc:
            return f"ERROR reading file: {exc}"

    @staticmethod
    def _tool_grep(query: str) -> str:
        parts = query.split("||", maxsplit=1)
        if len(parts) != 2:
            return "ERROR: input must be '<repo_path>||<pattern>'"
        repo_path, pattern = parts[0].strip(), parts[1].strip()
        try:
            result = subprocess.run(
                ["grep", "-rn", "--include=*.py", "--include=*.js",
                 "--include=*.ts", "--include=*.java", "--include=*.go",
                 "-E", pattern, repo_path],
                capture_output=True, text=True, timeout=15,
            )
            output = result.stdout or "(no matches)"
            if len(output) > 8000:
                output = output[:8000] + "\n... [truncated]"
            return output
        except subprocess.TimeoutExpired:
            return "ERROR: grep timed out"
        except FileNotFoundError:
            return "ERROR: grep not found on system"
        except Exception as exc:
            return f"ERROR: {exc}"

    @staticmethod
    def _tool_list_files(directory: str) -> str:
        base = Path(directory.strip())
        if not base.exists():
            return f"ERROR: directory not found: {directory}"
        try:
            extensions = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go",
                          ".rb", ".rs", ".cpp", ".c", ".h", ".cs"}
            files = [
                str(p)
                for p in sorted(base.rglob("*"))
                if p.is_file() and p.suffix in extensions
                and not any(part.startswith(".") for part in p.parts)
                and "node_modules" not in p.parts
                and "__pycache__" not in p.parts
            ]
            return "\n".join(files[:500]) or "(no source files found)"
        except Exception as exc:
            return f"ERROR: {exc}"

    @staticmethod
    def _tool_file_stats(file_path: str) -> str:
        path = Path(file_path.strip())
        if not path.exists():
            return f"ERROR: file not found: {file_path}"
        try:
            size = path.stat().st_size
            lines = path.read_text(encoding="utf-8", errors="replace").count("\n")
            return f'{{"file": "{path}", "lines": {lines}, "size_bytes": {size}}}'
        except Exception as exc:
            return f"ERROR: {exc}"

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _system_prompt(self) -> str:
        return (
            "You are an expert software engineer performing a thorough bug review of a code repository. "
            "Your task is to identify bugs, anti-patterns, and code quality issues.\n\n"
            "Focus on the following categories:\n"
            "1. Null/None pointer dereferences — accessing attributes or calling methods on potentially null values\n"
            "2. Off-by-one errors — incorrect loop bounds, index calculations, slice operations\n"
            "3. Resource leaks — files, sockets, database connections not properly closed\n"
            "4. Infinite loops — loops with missing or unreachable exit conditions\n"
            "5. Incorrect error handling — bare except clauses, swallowed exceptions, missing error propagation\n"
            "6. Type mismatches — implicit conversions, wrong type assumptions\n"
            "7. Dead code — unreachable statements, unused imports, unused variables\n"
            "8. Anti-patterns — god classes (>500 lines), magic numbers, deep nesting (>4 levels), "
            "long parameter lists (>5 params), feature envy\n"
            "9. Deprecated API usage — calls to deprecated stdlib or third-party methods\n"
            "10. Concurrency issues — race conditions, missing locks, improper thread sharing\n\n"
            "Instructions:\n"
            "- Use the list_files tool to enumerate source files in the repository.\n"
            "- Use read_file_contents to read up to 50 of the most relevant files.\n"
            "- Use grep_in_repo to search for specific patterns (e.g. bare except, TODO, FIXME, magic numbers).\n"
            "- Use get_file_stats to identify unusually large files (potential god classes).\n"
            "- Be specific: always provide file_path, line numbers, and a code snippet.\n"
            "- Provide a concrete actionable suggestion for each finding.\n"
            "- Only report genuine issues, not style preferences.\n"
            "- If you find no issues, return an empty JSON array.\n\n"
            "Your Final Answer MUST be a valid JSON array of finding objects. "
            "Each object must have these exact keys: "
            "title, description, severity (critical|high|medium|low|info), "
            "file_path, line_start, line_end, code_snippet, suggestion, cwe_id. "
            "Set cwe_id to null for bug findings. "
            "Use null for any fields you cannot determine."
        )

    # ------------------------------------------------------------------
    # Override analyze to cap chunks
    # ------------------------------------------------------------------

    async def analyze(
        self,
        chunks: list[dict],
        repo_path: str,
        repo_metadata: dict,
        peer_findings: list[AgentFinding] | None = None,
    ) -> AgentResult:
        capped = chunks[:_MAX_CHUNKS]
        return await super().analyze(capped, repo_path, repo_metadata, peer_findings)
