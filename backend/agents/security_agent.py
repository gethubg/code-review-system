from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import structlog
from langchain_core.tools import Tool

from .base_agent import AgentFinding, AgentResult, BaseReviewAgent

log = structlog.get_logger()

_MAX_READ_BYTES = 32_768

# Patterns that signal hardcoded secrets
_SECRET_PATTERNS = [
    r'(?i)(api_key|apikey|secret_key|secretkey|access_token|auth_token|private_key)\s*=\s*["\'][^"\']{8,}["\']',
    r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']',
    r'(?i)aws_secret_access_key\s*=\s*["\'][^"\']+["\']',
    r'(?i)AKIA[0-9A-Z]{16}',  # AWS access key ID
    r'(?i)sk-[a-zA-Z0-9]{32,}',  # OpenAI key pattern
    r'(?i)ghp_[a-zA-Z0-9]{36}',  # GitHub PAT
    r'(?i)xox[baprs]-[0-9A-Za-z\-]{10,}',  # Slack token
]

_WEAK_CRYPTO = ["md5", "sha1", "des", "rc4", "3des", "blowfish"]


class SecurityAgent(BaseReviewAgent):
    """Performs OWASP Top 10 2021 security analysis."""

    def agent_type(self) -> str:
        return "security"

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _build_tools(self) -> list[Tool]:
        return [
            Tool(
                name="read_file_contents",
                func=self._tool_read_file,
                description=(
                    "Read a source file's contents. "
                    "Input: absolute or relative file path. "
                    "Output: file text (truncated at 32 KB)."
                ),
            ),
            Tool(
                name="grep_in_repo",
                func=self._tool_grep,
                description=(
                    "Search for a regex pattern across the repo. "
                    "Input: '<repo_path>||<pattern>'. "
                    "Output: matching lines with file and line number."
                ),
            ),
            Tool(
                name="run_pip_audit",
                func=self._tool_pip_audit,
                description=(
                    "Run pip-audit on the repository to find vulnerable Python dependencies. "
                    "Input: repo path. "
                    "Output: JSON vulnerability report or error message."
                ),
            ),
            Tool(
                name="run_npm_audit",
                func=self._tool_npm_audit,
                description=(
                    "Run npm audit on the repository to find vulnerable JS dependencies. "
                    "Input: repo path (must contain package.json). "
                    "Output: JSON vulnerability report or error message."
                ),
            ),
            Tool(
                name="get_git_log",
                func=self._tool_git_log,
                description=(
                    "Return recent git commit messages (last 20) for the repo. "
                    "Input: repo path. "
                    "Output: formatted git log."
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
        parts = query.split("||", maxsplit=1)
        if len(parts) != 2:
            return "ERROR: input must be '<repo_path>||<pattern>'"
        repo_path, pattern = parts[0].strip(), parts[1].strip()
        try:
            result = subprocess.run(
                ["grep", "-rn", "--include=*.py", "--include=*.js",
                 "--include=*.ts", "--include=*.java", "--include=*.go",
                 "--include=*.rb", "--include=*.php", "--include=*.cs",
                 "-E", pattern, repo_path],
                capture_output=True, text=True, timeout=20,
            )
            output = result.stdout or "(no matches)"
            if len(output) > 8000:
                output = output[:8000] + "\n... [truncated]"
            return output
        except subprocess.TimeoutExpired:
            return "ERROR: grep timed out"
        except FileNotFoundError:
            return "ERROR: grep not available"
        except Exception as exc:
            return f"ERROR: {exc}"

    @staticmethod
    def _tool_pip_audit(repo_path: str) -> str:
        base = Path(repo_path.strip())
        req_file = base / "requirements.txt"
        pyproject = base / "pyproject.toml"

        args = ["pip-audit", "--format", "json"]
        if req_file.exists():
            args += ["-r", str(req_file)]
        elif pyproject.exists():
            args += [str(pyproject)]
        else:
            return '{"info": "No requirements.txt or pyproject.toml found; skipping pip-audit."}'

        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=60)
            output = result.stdout or result.stderr
            if len(output) > 16000:
                output = output[:16000] + "\n... [truncated]"
            return output or '{"vulnerabilities": []}'
        except FileNotFoundError:
            return '{"info": "pip-audit not installed; skipping."}'
        except subprocess.TimeoutExpired:
            return '{"error": "pip-audit timed out"}'
        except Exception as exc:
            return f'{{"error": "{exc}"}}'

    @staticmethod
    def _tool_npm_audit(repo_path: str) -> str:
        base = Path(repo_path.strip())
        pkg = base / "package.json"
        if not pkg.exists():
            return '{"info": "No package.json found; skipping npm audit."}'
        try:
            result = subprocess.run(
                ["npm", "audit", "--json"],
                capture_output=True, text=True, timeout=60, cwd=str(base),
            )
            output = result.stdout or result.stderr
            if len(output) > 16000:
                output = output[:16000] + "\n... [truncated]"
            return output or '{"vulnerabilities": {}}'
        except FileNotFoundError:
            return '{"info": "npm not installed; skipping."}'
        except subprocess.TimeoutExpired:
            return '{"error": "npm audit timed out"}'
        except Exception as exc:
            return f'{{"error": "{exc}"}}'

    @staticmethod
    def _tool_git_log(repo_path: str) -> str:
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-20"],
                capture_output=True, text=True, timeout=10, cwd=repo_path.strip(),
            )
            return result.stdout or "(no git history)"
        except Exception as exc:
            return f"ERROR: {exc}"

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _system_prompt(self) -> str:
        secret_patterns_str = "\n".join(f"  - {p}" for p in _SECRET_PATTERNS)
        weak_crypto_str = ", ".join(_WEAK_CRYPTO)
        return (
            "You are an expert application security engineer performing a comprehensive security review "
            "of a code repository against OWASP Top 10 2021.\n\n"
            "Check for each of the following OWASP categories:\n"
            "A01 – Broken Access Control: missing authorization checks, insecure direct object references, "
            "CORS misconfigurations, privilege escalation paths.\n"
            "A02 – Cryptographic Failures: plaintext transmission of sensitive data, weak algorithms "
            f"({weak_crypto_str}), hardcoded keys, insufficient key lengths.\n"
            "A03 – Injection: SQL injection (string concatenation in queries), command injection "
            "(os.system, subprocess with shell=True), LDAP injection, XSS, template injection.\n"
            "A04 – Insecure Design: missing threat model protections, insecure business logic.\n"
            "A05 – Security Misconfiguration: debug mode in production, default credentials, "
            "verbose error messages exposing stack traces, overly permissive CORS.\n"
            "A06 – Vulnerable and Outdated Components: use run_pip_audit and run_npm_audit to identify "
            "known CVEs in dependencies.\n"
            "A07 – Identification and Authentication Failures: weak password policies, missing MFA, "
            "insecure session management, JWT algorithm confusion (alg:none).\n"
            "A08 – Software and Data Integrity Failures: unverified downloads, missing SRI hashes, "
            "insecure deserialization (pickle.loads on untrusted data, yaml.load without Loader).\n"
            "A09 – Security Logging and Monitoring Failures: missing audit logs for auth events, "
            "sensitive data logged in plaintext.\n"
            "A10 – Server-Side Request Forgery: user-controlled URLs fetched server-side without validation.\n\n"
            "Additionally check for:\n"
            "- Hardcoded secrets using these patterns:\n"
            f"{secret_patterns_str}\n"
            "- Path traversal: user input used in file paths without sanitization.\n"
            "- Insecure deserialization: pickle, marshal, yaml.load (without SafeLoader).\n"
            "- Weak random: random.random() used for security-sensitive operations.\n\n"
            "Instructions:\n"
            "- Use grep_in_repo to search for dangerous patterns.\n"
            "- Use read_file_contents to inspect flagged files in detail.\n"
            "- Use run_pip_audit and run_npm_audit for dependency vulnerabilities.\n"
            "- Always include CWE IDs (e.g. CWE-89 for SQL injection).\n"
            "- Provide file_path, line numbers, and the exact vulnerable code snippet.\n"
            "- Provide a concrete remediation in the suggestion field.\n"
            "- Severity: critical for RCE/auth bypass, high for injection/data exposure, "
            "medium for misconfig, low for defense-in-depth gaps.\n\n"
            "Your Final Answer MUST be a valid JSON array of finding objects with keys: "
            "title, description, severity (critical|high|medium|low|info), "
            "file_path, line_start, line_end, code_snippet, suggestion, cwe_id. "
            "Use null for missing fields. Return [] if no issues found."
        )
