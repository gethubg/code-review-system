# Code Review System

An autonomous multi-agent AI pipeline that clones any public Git repository, runs three specialist agents in parallel, and produces a scored production-readiness report with severity-mapped findings, interactive charts, and downloadable reports.

---

## What It Does

1. Paste a GitHub URL into the UI
2. The system clones the repo and chunks every source file (AST-aware, function/class level)
3. Three AI agents run **in parallel**, each with a different focus:
   - **Bug Agent** — logic errors, anti-patterns, dead code, resource leaks
   - **Security Agent** — OWASP Top 10, hardcoded secrets, injection vulnerabilities, CVEs
   - **Coverage Agent** — missing tests, untested public APIs, edge case gaps
4. A **Synthesizer** merges all findings, deduplicates, promotes severity where agents agree, scores the repo 0–100, and renders a report
5. The UI shows live WebSocket progress, severity charts, a filterable findings table, and the full Markdown report — all downloadable

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Orchestration** | LangGraph 0.2 — StateGraph with parallel `Send` fan-out |
| **Agents** | LangChain + LangGraph `create_react_agent`, GPT-4o |
| **Code chunking** | LlamaIndex `CodeSplitter` — AST-aware, function/class level |
| **Vector store** | Pinecone — semantic code chunk search |
| **Backend** | FastAPI + uvicorn, async SQLite via SQLModel + aiosqlite |
| **Real-time** | WebSocket progress streaming |
| **Frontend** | React 19 + Vite, Recharts, react-markdown |
| **Tools** | FastMCP tool server — git, file system, dep-audit |
| **Language** | Python 3.12 + TypeScript 5.6 |

---

## Quick Start

### Prerequisites

- Python 3.12
- Node.js 20+
- OpenAI API key
- Pinecone API key (free tier works)

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in OPENAI_API_KEY and PINECONE_API_KEY
```

### 2. Backend

```bash
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
uvicorn backend.main:app --port 8080 --reload
```

### 3. Frontend (new terminal)

```bash
cd frontend
npm install
npm run dev -- --port 5174
```

### 4. Open the UI

```
http://localhost:5174
```

Paste any public GitHub URL and click **Submit Review**.

---

## Project Structure

```
code-review-system/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── agents/
│   │   ├── base_agent.py        # Abstract ReAct agent, AgentFinding schema
│   │   ├── bug_agent.py         # Bug & anti-pattern detection
│   │   ├── security_agent.py    # OWASP / CVE / secrets detection
│   │   └── coverage_agent.py    # Test gap analysis + stub suggestions
│   ├── orchestrator/
│   │   ├── graph.py             # LangGraph StateGraph + parallel Send fan-out
│   │   ├── state.py             # ReviewState TypedDict
│   │   └── synthesizer.py       # Merge, dedup, promote, score, render
│   ├── ingestion/
│   │   ├── git_loader.py        # Clone repo, walk files
│   │   ├── code_chunker.py      # LlamaIndex AST-aware chunking
│   │   └── embedder.py          # OpenAI embeddings → Pinecone
│   ├── tools/
│   │   ├── mcp_server.py        # FastMCP server exposing all tools
│   │   ├── git_tools.py         # git log / blame / diff
│   │   ├── dep_audit.py         # pip-audit / npm audit
│   │   └── file_tools.py        # file read, grep, stats
│   ├── storage/
│   │   ├── database.py          # Async SQLite CRUD
│   │   ├── models.py            # SQLModel: ReviewRun, Finding, Report
│   │   └── vector_store.py      # Pinecone index management
│   ├── report/
│   │   ├── formatter.py         # Markdown + JSON serializer
│   │   └── scorer.py            # Production-grade scoring (0–100)
│   ├── routes/
│   │   ├── review.py            # POST /review, GET /runs
│   │   ├── findings.py          # GET /findings (filterable)
│   │   └── reports.py           # GET /reports + download
│   └── ws/
│       └── progress.py          # WebSocket /ws/progress/{run_id}
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── ReviewPage.tsx   # Git URL form + live progress feed
│       │   ├── ResultsPage.tsx  # Score gauge, charts, findings, report
│       │   └── HistoryPage.tsx  # Past runs table
│       ├── components/
│       │   ├── ProductionScore.tsx   # SVG score gauge
│       │   ├── SeverityChart.tsx     # Recharts bar chart by severity
│       │   ├── SeverityPie.tsx       # Donut chart by agent
│       │   ├── FindingsTable.tsx     # Filterable, expandable findings
│       │   ├── ReportViewer.tsx      # Collapsible Markdown renderer
│       │   ├── DownloadPanel.tsx     # JSON / Markdown / PDF download
│       │   └── ProgressFeed.tsx      # Live WebSocket log
│       └── lib/
│           ├── api.ts           # Typed axios wrappers
│           └── ws.ts            # WebSocket hook
├── docs/
│   ├── architecture.md          # System design and data flow
│   ├── agents.md                # Per-agent spec and prompts
│   ├── api.md                   # REST + WebSocket reference
│   ├── scoring.md               # Scoring rubric
│   └── setup.md                 # Detailed setup and Docker guide
├── tests/
│   ├── unit/                    # Scorer and synthesizer unit tests
│   └── integration/             # API integration tests
├── pyproject.toml
├── docker-compose.yml
└── .env.example
```

---

## API Overview

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/review` | Submit a Git URL — starts review in background |
| `GET` | `/api/runs` | List all review runs (paginated) |
| `GET` | `/api/runs/{run_id}` | Get run status and metadata |
| `GET` | `/api/findings` | Query findings — filter by `severity`, `agent`, `run_id` |
| `GET` | `/api/reports/{run_id}/summary` | Score, verdict, finding counts by severity and agent |
| `GET` | `/api/reports/{run_id}/download?format=markdown` | Download Markdown report |
| `GET` | `/api/reports/{run_id}/download?format=json` | Download JSON report |
| `WS`  | `/ws/progress/{run_id}` | Live progress stream (JSON messages) |

Interactive Swagger UI: `http://localhost:8080/docs`

---

## Production Score

| Score | Verdict |
|---|---|
| 75 – 100 | ✅ PRODUCTION READY |
| 50 – 74 | ⚠️ NEEDS IMPROVEMENT |
| 0 – 49 | ❌ NOT PRODUCTION READY |

Any **critical security finding** caps the score at 30 regardless of other findings.  
See [docs/scoring.md](docs/scoring.md) for the full rubric.

---

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

55 unit tests cover the scorer, synthesizer dedup logic, and severity promotion.

---

## Docker

```bash
docker compose up --build
# UI → http://localhost:5174
# API → http://localhost:8080
```

---

## Documentation

| File | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | System design, LangGraph topology, data flow |
| [docs/agents.md](docs/agents.md) | Per-agent capabilities, tools, output schema |
| [docs/api.md](docs/api.md) | Full REST + WebSocket reference with examples |
| [docs/scoring.md](docs/scoring.md) | Scoring weights, verdict thresholds, examples |
| [docs/setup.md](docs/setup.md) | Local setup, Docker, env vars, troubleshooting |

---

## License

MIT
