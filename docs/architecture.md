# Architecture

## Overview

The Code Review System is a multi-agent AI pipeline built on LangGraph. A single Git URL enters the system and a structured, scored report exits. Everything between those two points is orchestrated as a compiled state machine with parallel agent execution.

---

## Data Flow

```
Git URL
  │
  ▼
┌─────────────────────────────┐
│         ingest_node          │
│  clone → chunk → embed      │
│  GitLoader + LlamaIndex      │
│  CodeSplitter + Pinecone     │
└──────────────┬──────────────┘
               │ Send (parallel fan-out)
       ┌───────┼───────┐
       ▼       ▼       ▼
  bug_node  security  coverage
   _node      _node
       │       │       │
       └───────┴───────┘
               │ (all three converge)
               ▼
      ┌─────────────────┐
      │  synthesize_node │
      │  dedup + score   │
      │  render report   │
      └────────┬────────┘
               │
       ┌───────┴────────┐
       ▼                ▼
   SQLite DB       Report files
   (findings)    (JSON + Markdown)
```

---

## LangGraph State Machine

The graph is compiled once at startup (`build_graph()`) and reused across all reviews.

### State schema (`ReviewState`)

```python
class ReviewState(TypedDict):
    # Input
    run_id: str
    git_url: str
    openai_api_key: str
    openai_model: str

    # Ingestion outputs
    repo_path: str
    repo_metadata: dict
    chunks: list[dict]
    files_analyzed: int

    # Agent outputs — Annotated with operator.add for parallel fan-in
    bug_findings: Annotated[list, operator.add]
    security_findings: Annotated[list, operator.add]
    coverage_findings: Annotated[list, operator.add]

    # Synthesizer outputs
    all_findings: list[dict]
    production_score: float
    production_verdict: str
    report_markdown: str
    report_json: dict

    # Runtime
    progress_messages: Annotated[list[str], operator.add]
    error: str | None
```

`Annotated[list, operator.add]` means LangGraph merges findings from parallel branches by concatenation rather than overwriting.

### Nodes

| Node | Purpose |
|---|---|
| `ingest_node` | Clone repo, walk files, chunk with LlamaIndex, embed to Pinecone |
| `bug_node` | Run BugAgent, write to `bug_findings` |
| `security_node` | Run SecurityAgent (with bug peer context), write to `security_findings` |
| `coverage_node` | Run CoverageAgent (with bug + security peer context), write to `coverage_findings` |
| `synthesize_node` | Merge, dedup, promote severity, score, render Markdown + JSON |

### Parallel fan-out

After `ingest_node`, a conditional edge calls `route_to_agents()` which returns three `Send` objects — one per agent node. LangGraph schedules all three concurrently. The synthesizer node runs only after all three complete (implicit barrier via `operator.add` merge).

```python
def route_to_agents(state: ReviewState) -> list[Send]:
    if state.get("error"):
        return [Send("synthesize_node", state)]   # skip agents on ingest failure
    return [
        Send("bug_node", state),
        Send("security_node", state),
        Send("coverage_node", state),
    ]
```

---

## Agent Design

Each agent is a `BaseReviewAgent` subclass that wraps `create_react_agent` from `langgraph.prebuilt`. Agents follow the ReAct pattern: reason about what to check → call a tool → observe → repeat → return findings as a JSON array.

### Tools available to agents

| Tool | Agents that use it |
|---|---|
| `read_file_contents` | All |
| `grep_in_repo` | All |
| `list_files` | All |
| `get_file_stats` | Bug, Security |
| `get_git_log` | Security |
| `run_pip_audit` | Security |
| `run_npm_audit` | Security |

All tools are implemented in `backend/tools/` and exposed via a FastMCP server.

### Agent output schema

Every agent returns an `AgentResult` containing a list of `AgentFinding` objects:

```python
class AgentFinding(BaseModel):
    title: str
    description: str
    severity: str           # critical | high | medium | low | info
    file_path: str | None
    line_start: int | None
    line_end: int | None
    code_snippet: str | None
    suggestion: str | None
    cwe_id: str | None      # security agent only
```

### Agent-to-agent context (A2A)

Agents share findings via the LangGraph state. The security agent receives bug findings as `peer_findings` to help promote severity when the same code region has both a bug and a vulnerability. Coverage agent receives both bug and security findings. This is done through the state rather than direct agent communication — all three still execute in parallel; peer context is read from state values populated before the fan-out.

---

## Ingestion Pipeline

1. **GitLoader** — clones the repo to a temp directory using GitPython, walks the file tree, filters by supported extensions, skips files over 500KB and directories like `node_modules`, `__pycache__`, `.git`
2. **CodeChunker** — uses LlamaIndex `CodeSplitter` to split files at function/class boundaries (50-line chunks with 5-line overlap), preserving semantic context
3. **ChunkEmbedder** — batches chunks through `text-embedding-3-small` and upserts to Pinecone (optional — analysis works without it, Pinecone just enables semantic similarity search)

---

## Storage

### SQLite (via SQLModel + aiosqlite)

Three tables:

- **ReviewRun** — one row per review: git URL, status, score, verdict, counts
- **Finding** — one row per finding: agent, severity, file, line, description, suggestion
- **Report** — one row per completed run: paths to the markdown and JSON report files

### Pinecone

Each code chunk is stored as a vector with metadata `{run_id, file_path, start_line, end_line, language}`. Used by agents for semantic similarity queries (e.g. "find all authentication-related code").

### Report files

Saved to `data/reports/`:
- `{run_id}.md` — human-readable Markdown report
- `{run_id}.json` — structured JSON with full finding details

---

## API and WebSocket

The FastAPI backend exposes:

- REST routes for CRUD operations on runs, findings, and reports
- `POST /api/review` — creates a `ReviewRun` record, starts `_run_review` as a `BackgroundTask`
- WebSocket at `/ws/progress/{run_id}` — the background task pushes progress messages as each node completes; the frontend subscribes and shows a live log

---

## Frontend

Three pages:

| Page | Route | Purpose |
|---|---|---|
| Review | `/` | Git URL form, live WebSocket progress feed |
| Results | `/results/:runId` | Score gauge, severity charts, findings table, report viewer, downloads |
| History | `/history` | Table of all past runs |

The Results page polls `GET /api/runs/:runId` every 3 seconds while the run is active, then fetches the summary and Markdown report once completed.
