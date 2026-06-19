import axios from 'axios'

// ── Types ────────────────────────────────────────────────────────────────────

export type RunStatus = 'pending' | 'running' | 'completed' | 'failed'

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'

export interface ReviewRun {
  id: string
  git_url: string
  status: RunStatus
  created_at: string
  completed_at: string | null
  error: string | null
  findings_count: number | null
}

export interface Finding {
  id: string
  run_id: string
  file_path: string
  line_start: number | null
  line_end: number | null
  severity: Severity
  category: string
  title: string
  description: string
  suggestion: string | null
  agent: string
}

export interface ReportSummary {
  score: number
  verdict: string
  finding_counts_by_severity: Record<Severity, number>
  finding_counts_by_agent: Record<string, number>
}

export interface PaginatedRuns {
  items: ReviewRun[]
  total: number
  skip: number
  limit: number
}

export interface PaginatedFindings {
  items: Finding[]
  total: number
  skip: number
  limit: number
}

export interface FindingsParams {
  severity?: Severity
  category?: string
  file_path?: string
  skip?: number
  limit?: number
}

export interface SubmitReviewResponse {
  run_id: string
  status: RunStatus
  message: string
}

// ── Axios instance ───────────────────────────────────────────────────────────

const client = axios.create({
  baseURL: '/',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
})

// ── API surface ──────────────────────────────────────────────────────────────

export const api = {
  /** Submit a new repository for review. */
  submitReview: (gitUrl: string) =>
    client.post<SubmitReviewResponse>('/api/review', { git_url: gitUrl }),

  /** Fetch a single run by ID. */
  getRun: (runId: string) =>
    client.get<ReviewRun>(`/api/runs/${runId}`),

  /** List all runs with pagination. */
  listRuns: (skip = 0, limit = 20) =>
    client.get<PaginatedRuns>('/api/runs', { params: { skip, limit } }),

  /** Fetch findings for a run, optionally filtered. */
  getFindings: (runId: string, params?: FindingsParams) =>
    client.get<PaginatedFindings>('/api/findings', {
      params: { run_id: runId, ...params },
    }),

  /** Fetch the high-level summary for a completed run. */
  getReportSummary: (runId: string) =>
    client.get<ReportSummary>(`/api/reports/${runId}/summary`),

  /** Download the full report in the requested format. */
  downloadReport: (runId: string, format: 'json' | 'markdown') =>
    client.get<Blob>(`/api/reports/${runId}/download`, {
      params: { format },
      responseType: 'blob',
    }),
}
