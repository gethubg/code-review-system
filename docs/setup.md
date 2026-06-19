# Setup Guide

## Prerequisites

| Tool | Minimum version | Notes |
|---|---|---|
| Python | 3.12 | Use `pyenv` or `uv` |
| Node.js | 20 LTS | |
| npm / pnpm | 9+ | Either works |
| git | any | Must be on PATH for cloning repos |

API keys required:
- **OpenAI** — for GPT-4o agent calls
- **Pinecone** — for code chunk vector storage (optional; system falls back gracefully)

---

## 1. Clone the repo

```bash
git clone <your-repo-url>
cd code-review-system
```

---

## 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in:

```dotenv
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# Pinecone (optional — leave blank to skip vector storage)
PINECONE_API_KEY=pcsk_...
PINECONE_INDEX_NAME=code-review-chunks
PINECONE_ENVIRONMENT=gcp-starter

# App
DATABASE_URL=sqlite+aiosqlite:///./data/reviews.db
REPORTS_DIR=./data/reports
CLONE_DIR=./data/repos
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:5173,http://localhost:3000,http://localhost:5174
```

---

## 3. Backend setup

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Create data directories
mkdir -p data/reports data/repos

# Run database migrations (creates tables on first start)
# Migrations happen automatically on app startup via SQLModel
```

Start the backend:

```bash
.venv/bin/uvicorn backend.main:app --port 8080 --reload
```

The backend starts at `http://localhost:8080`. Visit `http://localhost:8080/docs` for the auto-generated Swagger UI.

---

## 4. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

The dev server starts at `http://localhost:5174`.

---

## 5. Verify the setup

```bash
# Check the backend health endpoint
curl http://localhost:8080/

# Submit a small test repo
curl -X POST http://localhost:8080/api/review \
  -H "Content-Type: application/json" \
  -d '{"git_url": "https://github.com/mitsuhiko/flask"}'
```

Open `http://localhost:5174` in a browser, paste a git URL, and click **Start Review**.

---

## Docker

The project ships a `docker-compose.yml` that runs the backend and frontend together.

```bash
# Build and start
docker compose up --build

# Stop
docker compose down
```

Services:
- `backend` — FastAPI on port 8080
- `frontend` — Nginx serving the Vite build on port 5174

Environment variables are read from `.env` at the project root (same file as the local setup).

---

## Environment variable reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4o` | Model used for agents |
| `OPENAI_EMBEDDING_MODEL` | No | `text-embedding-3-small` | Model for code embeddings |
| `PINECONE_API_KEY` | No | — | Leave blank to skip Pinecone |
| `PINECONE_INDEX_NAME` | No | `code-review-chunks` | Pinecone index name |
| `PINECONE_ENVIRONMENT` | No | `gcp-starter` | Pinecone environment |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./data/reviews.db` | SQLite connection string |
| `REPORTS_DIR` | No | `./data/reports` | Where report files are saved |
| `CLONE_DIR` | No | `./data/repos` | Where repos are cloned to |
| `LOG_LEVEL` | No | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `CORS_ORIGINS` | No | `http://localhost:5174` | Comma-separated allowed origins |
| `MCP_SERVER_HOST` | No | `localhost` | FastMCP server host |
| `MCP_SERVER_PORT` | No | `8001` | FastMCP server port |

---

## Running tests

```bash
# All tests
pytest

# With coverage
pytest --cov=backend --cov-report=term-missing

# Watch mode
pytest-watch
```

The test suite uses `pytest-asyncio` for async tests and `httpx.AsyncClient` for FastAPI route tests.

---

## Troubleshooting

### `Address already in use` on port 8080

Another process is holding port 8080. Find and kill it:

```bash
lsof -ti :8080 | xargs kill -9
```

Then restart uvicorn.

### `KeyError: 'openai_api_key'` in graph.py

The `.env` file is not loaded or `OPENAI_API_KEY` is missing. Verify:

```bash
grep OPENAI_API_KEY .env
```

If the key is present but the error persists, make sure the backend process was restarted after editing `.env`.

### 0 findings on every review

- Check that the review status is `completed` (not `failed`).
- Confirm the backend logs show all three agents finishing (`Bug agent complete`, `Security agent complete`, `Coverage agent complete`).
- If the LLM returns non-JSON text, the base agent logs a warning and returns an empty list. Set `LOG_LEVEL=DEBUG` to see the raw LLM output.

### Frontend shows black screen / blank page

Open browser DevTools → Console. A runtime crash (usually a missing field on a TypeScript interface) causes a white/black screen. The most common cause is a stale `ReportSummary` shape — confirm the API response matches the interface in `frontend/src/lib/api.ts`.

### Pinecone errors on startup

If you don't have a Pinecone account, leave `PINECONE_API_KEY` blank. The ingestion pipeline skips vector storage and runs analysis directly from the cloned repo.

### Docker build fails

```bash
# Clean and rebuild
docker compose down --volumes --remove-orphans
docker compose build --no-cache
docker compose up
```

### Frontend CORS errors

Add your frontend's origin to `CORS_ORIGINS` in `.env`:

```dotenv
CORS_ORIGINS=http://localhost:5174,http://localhost:3000
```

Restart the backend after editing `.env`.
