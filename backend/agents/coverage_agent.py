from __future__ import annotations

import re
from pathlib import Path

import structlog
from langchain_core.tools import Tool

from .base_agent import AgentFinding, AgentResult, BaseReviewAgent

log = structlog.get_logger()

_MAX_READ_BYTES = 32_768

# Common test file naming conventions
_TEST_FILE_PATTERNS = [
    r"test_.*\.py$",
    r".*_test\.py$",
    r".*\.test\.[jt]sx?$",
    r".*\.spec\.[jt]sx?$",
    r"Test.*\.java$",
    r".*_test\.go$",
    r".*_spec\.rb$",
]

# Heuristics for source files (not test files)
_SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rb", ".cs", ".rs"}
_TEST_DIR_NAMES = {"tests", "test", "spec", "__tests__", "test_", "specs"}


def _is_test_file(path: Path) -> bool:
    name = path.name
    parts_lower = {p.lower() for p in path.parts}
    if parts_lower & _TEST_DIR_NAMES:
        return True
    return any(re.match(pat, name, re.IGNORECASE) for pat in _TEST_FILE_PATTERNS)


def _is_source_file(path: Path) -> bool:
    return path.suffix in _SOURCE_EXTENSIONS and not _is_test_file(path)


class CoverageAgent(BaseReviewAgent):
    """Identifies missing test coverage and suggests concrete test stubs."""

    def agent_type(self) -> str:
        return "coverage"

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _build_tools(self) -> list[Tool]:
        return [
            Tool(
                name="read_file_contents",
                func=self._tool_read_file,
                description=(
                    "Read a source file's full contents. "
                    "Input: file path. "
                    "Output: file text (truncated at 32 KB)."
                ),
            ),
            Tool(
                name="grep_in_repo",
                func=self._tool_grep,
                description=(
                    "Search for a regex pattern across the repository. "
                    "Input: '<repo_path>||<pattern>'. "
                    "Output: matching lines with file and line number."
                ),
            ),
            Tool(
                name="list_files",
                func=self._tool_list_files,
                description=(
                    "List all source and test files in a directory recursively. "
                    "Input: directory path. "
                    "Output: JSON with 'source_files' and 'test_files' lists."
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
            return f"ERROR: {exc}"

    @staticmethod
    def _tool_grep(query: str) -> str:
        import subprocess

        parts = query.split("||", maxsplit=1)
        if len(parts) != 2:
            return "ERROR: input must be '<repo_path>||<pattern>'"
        repo_path, pattern = parts[0].strip(), parts[1].strip()
        try:
            result = subprocess.run(
                ["grep", "-rn",
                 "--include=*.py", "--include=*.js", "--include=*.ts",
                 "--include=*.java", "--include=*.go", "--include=*.rb",
                 "--include=*.cs", "--include=*.rs",
                 "-E", pattern, repo_path],
                capture_output=True, text=True, timeout=15,
            )
            output = result.stdout or "(no matches)"
            if len(output) > 8000:
                output = output[:8000] + "\n... [truncated]"
            return output
        except Exception as exc:
            return f"ERROR: {exc}"

    @staticmethod
    def _tool_list_files(directory: str) -> str:
        import json as _json

        base = Path(directory.strip())
        if not base.exists():
            return f"ERROR: directory not found: {directory}"
        try:
            source_files: list[str] = []
            test_files: list[str] = []
            for p in sorted(base.rglob("*")):
                if not p.is_file():
                    continue
                if p.suffix not in _SOURCE_EXTENSIONS:
                    continue
                if any(part.startswith(".") for part in p.parts):
                    continue
                if "node_modules" in p.parts or "__pycache__" in p.parts:
                    continue
                if _is_test_file(p):
                    test_files.append(str(p))
                else:
                    source_files.append(str(p))
            return _json.dumps(
                {
                    "source_files": source_files[:300],
                    "test_files": test_files[:300],
                    "source_count": len(source_files),
                    "test_count": len(test_files),
                },
                indent=2,
            )
        except Exception as exc:
            return f"ERROR: {exc}"

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _system_prompt(self) -> str:
        return (
            "You are an expert software engineer specialising in test quality and coverage analysis. "
            "Your task is to review a code repository and identify gaps in test coverage.\n\n"
            "Step 1 — Map the codebase:\n"
            "  - Use list_files to discover source files and test files.\n"
            "  - Note the ratio of source to test files. A healthy ratio is roughly 1:1 or better.\n\n"
            "Step 2 — Identify untested public APIs:\n"
            "  - Read source files and identify public functions, methods, and classes.\n"
            "  - Use grep_in_repo to check whether corresponding test cases exist.\n"
            "  - For Python: grep for 'def test_<function_name>' or 'class Test<ClassName>'.\n"
            "  - For JS/TS: grep for 'describe.*<ClassName>' or 'it.*<function_name>'.\n"
            "  - For Java: grep for '@Test' and the method name in test files.\n\n"
            "Step 3 — Identify missing edge case and error path tests:\n"
            "  - Look for try/except, if/else, switch, and conditional branches in source files.\n"
            "  - Check whether test files cover negative paths, empty inputs, boundary values.\n"
            "  - Use grep_in_repo to check for 'pytest.raises', 'assertRaises', 'expect.*toThrow', etc.\n\n"
            "Step 4 — Check test quality:\n"
            "  - Flag tests with no assertions (missing assert/expect statements).\n"
            "  - Flag tests that mock everything and assert nothing meaningful.\n"
            "  - Flag external dependencies (HTTP calls, DB queries) that are not mocked.\n"
            "  - Check for missing integration tests on database operations or external API calls.\n\n"
            "Step 5 — Suggest concrete test stubs:\n"
            "  - For each missing test, provide a concrete test code snippet in the suggestion field.\n"
            "  - Match the language and testing framework already used in the repo.\n"
            "  - Include meaningful assertions, not just 'assert True'.\n"
            "  - Show how to mock external dependencies where needed.\n\n"
            "Severity guidelines:\n"
            "  - high: core business logic or public API with zero tests.\n"
            "  - medium: important utility or helper function with no tests; missing error path coverage.\n"
            "  - low: minor helper or private function with no tests; assertion quality issues.\n"
            "  - info: test naming convention violations; missing docstrings in test files.\n\n"
            "Your Final Answer MUST be a valid JSON array of finding objects with keys: "
            "title, description, severity (critical|high|medium|low|info), "
            "file_path, line_start, line_end, code_snippet, suggestion, cwe_id. "
            "Set cwe_id to null for all coverage findings. "
            "The suggestion field should contain an actual test code snippet when applicable. "
            "Use null for fields you cannot determine. Return [] if coverage is adequate."
        )
