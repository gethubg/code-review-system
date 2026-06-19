# API Reference

Base URL: `http://localhost:8080`

All endpoints are prefixed with `/api`.

---

## Review Runs

### POST /api/review

Submit a repository for review. Returns immediately with status `202 Accepted`. The review runs in the background.

**Request**

```json
{
  "git_url": "https://github.com/owner/repo"
}
```

**Response** `202`

```json
{
  "run_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "id":     "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "pending",
  "git_url": "https://github.com/owner/repo",
  "repo_name": "repo",
  "created_at": "2026-06-19T10:00:00Z",
  "completed_at": null,
  "production_score": null,
  "production_verdict": null,
  "total_findings": 0,
  "critical_count": 0,
  "high_count": 0,
  "medium_count": 0,
  "low_count": 0,
  "error_message": null
}
```

---

### GET /api/runs

List all review runs, newest first.

**Query params**

| Param | Type | Default | Description |
|---|---|---|---|
| `skip` | int | `0` | Pagination offset |
| `limit` | int | `20` | Page size (max 100) |

**Response** `200`

```json
{
  "items": [{ /* ReviewRun */ }],
  "total": 42,
  "skip": 0,
  "limit": 20
}
```

---

### GET /api/runs/{run_id}

Fetch a single run by ID.

**Response** `200`

```json
{
  "run_id": "f47ac10b-...",
  "status": "completed",
  "git_url": "https://github.com/owner/repo",
  "repo_name": "repo",
  "created_at": "2026-06-19T10:00:00Z",
  "completed_at": "2026-06-19T10:04:32Z",
  "production_score": 73.5,
  "production_verdict": "NEEDS IMPROVEMENT",
  "total_findings": 18,
  "critical_count": 0,
  "high_count": 3,
  "medium_count": 9,
  "low_count": 6,
  "error_message": null
}
```

**Statuses**

| Value | Meaning |
|---|---|
| `pending` | Queued, not started |
| `running` | In progress |
| `completed` | Finished successfully |
| `failed` | Finished with error |

**Error** `404` — run not found.

---

## Findings

### GET /api/findings

List findings for a run, with optional filters.

**Query params**

| Param | Type | Description |
|---|---|---|
| `run_id` | string | **Required.** The run to fetch findings for |
| `severity` | string | Filter: `critical` / `high` / `medium` / `low` / `info` |
| `category` | string | Filter by agent: `bug` / `security` / `coverage` |
| `file_path` | string | Filter by file path substring |
| `skip` | int | Pagination offset (default 0) |
| `limit` | int | Page size (default 50, max 500) |

**Response** `200`

```json
{
  "items": [
    {
      "id": "a1b2c3d4-...",
      "run_id": "f47ac10b-...",
      "agent": "security",
      "severity": "high",
      "title": "SQL injection via unsanitized user input",
      "description": "The `query` parameter is concatenated directly into the SQL string on line 47 of db/queries.py.",
      "file_path": "db/queries.py",
      "line_start": 47,
      "line_end": 49,
      "code_snippet": "sql = f\"SELECT * FROM users WHERE id = {user_id}\"",
      "suggestion": "Use parameterized queries: `cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))`",
      "cwe_id": "CWE-89",
      "created_at": "2026-06-19T10:04:20Z"
    }
  ],
  "total": 18,
  "skip": 0,
  "limit": 50
}
```

---

## Reports

### GET /api/reports/{run_id}/summary

High-level summary stats for a completed run. Used to render the dashboard charts and score panel.

**Response** `200`

```json
{
  "score": 73.5,
  "verdict": "NEEDS IMPROVEMENT",
  "finding_counts_by_severity": {
    "critical": 0,
    "high": 3,
    "medium": 9,
    "low": 6,
    "info": 0
  },
  "finding_counts_by_agent": {
    "bug": 7,
    "security": 5,
    "coverage": 6
  }
}
```

**Error** `404` — run not found.  
**Error** `409` — run not yet completed.

---

### GET /api/reports/{run_id}/download

Download the full report file.

**Query params**

| Param | Values | Default |
|---|---|---|
| `format` | `json` \| `markdown` | `markdown` |

**Response** `200` — `Content-Disposition: attachment; filename=code-review-{run_id}.md`  
Content-Type: `text/markdown` or `application/json` depending on `format`.

**Aliases** (same behaviour, no query param needed):
- `GET /api/reports/{run_id}/download/markdown`
- `GET /api/reports/{run_id}/download/json`

**Error** `404` — report or report file not found.

---

### GET /api/reports/{run_id}

Report metadata (file paths, creation time).

**Response** `200`

```json
{
  "id": "c3d4e5f6-...",
  "run_id": "f47ac10b-...",
  "markdown_path": "./data/reports/f47ac10b-.../report.md",
  "json_path": "./data/reports/f47ac10b-.../report.json",
  "created_at": "2026-06-19T10:04:33Z"
}
```

---

## WebSocket: Progress Feed

Connect to receive live progress events while a review is running.

**URL**

```
ws://localhost:8080/ws/progress/{run_id}
```

**Message format** (JSON, server → client)

```json
{
  "type": "progress",
  "message": "Security agent complete — 5 finding(s)",
  "timestamp": "2026-06-19T10:01:45Z"
}
```

**`type` values**

| Value | Meaning |
|---|---|
| `progress` | Informational step update |
| `complete` | Review finished; safe to close the socket |
| `error` | Review failed; `message` contains the error text |

**Lifecycle**

1. Client connects immediately after `POST /api/review` returns.
2. Server buffers up to 100 messages per run in an `asyncio.Queue`.
3. When the review ends (complete or error), the server sends a final message and closes the connection.
4. If the client connects after the review is already done, it receives any buffered messages and then the final message.

**Example (JavaScript)**

```js
const ws = new WebSocket(`ws://localhost:8080/ws/progress/${runId}`)
ws.onmessage = (e) => {
  const { type, message } = JSON.parse(e.data)
  if (type === 'complete' || type === 'error') ws.close()
  console.log(message)
}
```

---

## Error Envelope

All errors return standard FastAPI JSON:

```json
{
  "detail": "Run 'abc' not found"
}
```

HTTP status codes follow REST conventions: `400` bad request, `404` not found, `409` conflict (review still running), `422` validation error, `500` internal error.
