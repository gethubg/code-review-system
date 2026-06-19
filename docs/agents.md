# Agents

The system has three specialist review agents and one synthesizer. All agents extend `BaseReviewAgent` and are executed in parallel by the LangGraph orchestrator.

---

## BaseReviewAgent

**File:** `backend/agents/base_agent.py`

Abstract base class that handles:
- LLM initialization (`ChatOpenAI`, GPT-4o by default)
- Tool binding via `create_react_agent` from `langgraph.prebuilt`
- ReAct execution loop (reason → tool call → observe → repeat)
- JSON output parsing from the agent's final message
- Severity normalisation and Pydantic validation of each finding
- Graceful fallback to empty results on LLM errors

### Output schema

```python
class AgentFinding(BaseModel):
    title: str
    description: str
    severity: str        # "critical" | "high" | "medium" | "low" | "info"
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    code_snippet: str | None = None
    suggestion: str | None = None
    cwe_id: str | None = None

class AgentResult(BaseModel):
    agent_type: str
    findings: list[AgentFinding]
    summary: str
    files_analyzed: int
    duration_seconds: float
```

Agents are instructed to return a JSON array as their final message. The base class extracts the first `[...]` block, parses it, and validates each element against `AgentFinding`.

### Peer findings (A2A)

Each `analyze()` call accepts an optional `peer_findings` list. This is populated from sibling agents' outputs via the LangGraph state. When peer findings are present, the agent is instructed to:
- Elevate severity if the same file/region is flagged by another agent
- Note corroborating evidence in its descriptions

---

## Bug Agent

**File:** `backend/agents/bug_agent.py`  
**State key:** `bug_findings`

### What it detects

| Category | Examples |
|---|---|
| Logic errors | Off-by-one, incorrect conditionals, wrong operator |
| Null/None dereferences | Missing null checks before attribute access |
| Resource leaks | Unclosed files, DB connections, sockets |
| Dead code | Unreachable branches, unused variables, imports |
| Anti-patterns | God classes, magic numbers, deep nesting (>4 levels) |
| Error handling | Bare `except`, swallowed exceptions, no logging |
| Type mismatches | Implicit coercions, missing type annotations on public APIs |
| Infinite loop risk | While loops without guaranteed exit condition |
| Deprecated APIs | Usage of deprecated stdlib or library APIs |

### Tools

- `read_file_contents` — read any source file
- `grep_in_repo` — search for patterns across the codebase
- `list_files` — enumerate files by extension
- `get_file_stats` — summary stats (total lines, languages)

### Severity guide

| Severity | When assigned |
|---|---|
| `critical` | Bug causes data corruption or system crash |
| `high` | Bug breaks a core feature or causes incorrect behavior |
| `medium` | Bug may cause issues in edge cases |
| `low` | Code smell, style issue, minor anti-pattern |

---

## Security Agent

**File:** `backend/agents/security_agent.py`  
**State key:** `security_findings`

### What it detects

Covers **OWASP Top 10 (2021)**:

| OWASP ID | Category | What we check |
|---|---|---|
| A01 | Broken Access Control | Missing auth checks, IDOR patterns, path traversal |
| A02 | Cryptographic Failures | Hardcoded secrets, weak algos (MD5, SHA1, DES), HTTP instead of HTTPS |
| A03 | Injection | SQL injection, command injection, LDAP injection, XSS |
| A04 | Insecure Design | Missing input validation, no rate limiting |
| A05 | Security Misconfiguration | Debug mode on, default creds, permissive CORS |
| A06 | Vulnerable Components | Outdated deps flagged by pip-audit / npm audit |
| A07 | Auth Failures | Weak passwords, no session expiry, JWT issues |
| A08 | Software Integrity Failures | Unverified downloads, missing integrity checks |
| A09 | Logging Failures | Sensitive data in logs, missing audit logs |
| A10 | SSRF | Unvalidated URLs passed to HTTP clients |

Also detects:
- **Hardcoded secrets** — API keys, passwords, tokens via regex patterns
- **Insecure deserialization** — `pickle.loads`, `yaml.load` without `Loader`
- **Path traversal** — unsanitized file paths from user input
- **Weak random** — `random` module used for security-sensitive values

Findings include a `cwe_id` field (e.g. `CWE-89` for SQL injection).

### Tools

- `read_file_contents`, `grep_in_repo`, `list_files`
- `get_git_log` — check commit history for secrets accidentally committed
- `run_pip_audit` — scan Python dependencies for known CVEs
- `run_npm_audit` — scan Node.js dependencies for known CVEs

### Severity guide

| Severity | When assigned |
|---|---|
| `critical` | Direct exploit path: RCE, SQLi with data exfil, auth bypass |
| `high` | Significant vulnerability requiring auth or specific conditions |
| `medium` | Defense-in-depth issue, hardcoded non-production secret |
| `low` | Best-practice deviation, minor misconfiguration |

---

## Coverage Agent

**File:** `backend/agents/coverage_agent.py`  
**State key:** `coverage_findings`

### What it detects

| Category | Examples |
|---|---|
| Missing unit tests | Public functions/methods with no corresponding test |
| Missing error path tests | Exception-raising code with no test for the error case |
| Missing edge case tests | Boundary values, empty inputs, None inputs not tested |
| Poor assertion quality | Tests with no assertions, or only `assert True` |
| Missing integration tests | DB operations, HTTP clients, file I/O not tested |
| Mocking gaps | External dependencies called without mocking in tests |
| Test naming conventions | Unclear test names that don't describe the behavior |

### Suggestion format

The Coverage Agent provides concrete test stubs in its `suggestion` field:

```python
# Example suggestion for a missing test
def test_calculate_discount_with_zero_price():
    """Edge case: zero price should return zero discount."""
    result = calculate_discount(price=0, percent=10)
    assert result == 0

def test_calculate_discount_raises_on_negative_price():
    """Negative price is invalid input."""
    with pytest.raises(ValueError, match="price must be non-negative"):
        calculate_discount(price=-1, percent=10)
```

### Tools

- `read_file_contents`, `grep_in_repo`, `list_files`

### Severity guide

| Severity | When assigned |
|---|---|
| `high` | Core business logic or security-sensitive function has zero tests |
| `medium` | Public API function has no error path or edge case tests |
| `low` | Test exists but lacks meaningful assertions or edge coverage |

---

## Synthesizer

**File:** `backend/orchestrator/synthesizer.py`

The Synthesizer is a LangGraph node (not an LLM agent) that post-processes all agent outputs deterministically.

### Steps

1. **Collect** — gather all findings from `bug_findings`, `security_findings`, `coverage_findings`
2. **Normalize** — coerce severity to valid enum, strip invalid fields, set defaults
3. **Deduplicate** — remove findings where same `file_path` + nearby line + similar title (Jaccard similarity threshold)
4. **Promote severity** — if 2+ agents flag the same file region, upgrade the severity one level
5. **Sort** — CRITICAL first, then HIGH, MEDIUM, LOW, INFO
6. **Score** — calculate production score 0–100 (see [scoring.md](scoring.md))
7. **Render** — produce Markdown report and structured JSON report
8. **Return** — emit `all_findings`, `production_score`, `production_verdict`, `report_markdown`, `report_json` into state

### Deduplication logic

Two findings are considered duplicates when:
- Same `file_path` (or both have no file path)
- Line numbers within 5 lines of each other
- Title Jaccard similarity > 0.5 (word overlap)

When a duplicate is found, the one with the higher severity is kept.

### Severity promotion

If findings from two or more different agents overlap (same file, lines within 10 of each other), the highest severity among them is promoted one level (e.g. `medium` → `high`). This is flagged with `"promoted": true` in the finding.
