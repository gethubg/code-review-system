import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink, Loader2, RefreshCw, Clock } from 'lucide-react'
import { api } from '../lib/api.ts'
import { StatusBadge } from '../components/StatusBadge.tsx'
import type { ReviewRun } from '../lib/api.ts'

const LIMIT = 20

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function repoShortName(gitUrl: string): string {
  try {
    return new URL(gitUrl).pathname.replace(/^\//, '').replace(/\.git$/, '')
  } catch {
    return gitUrl
  }
}

type VerdictMeta = { label: string; bg: string; color: string }

function verdictFromRun(run: ReviewRun): VerdictMeta | null {
  if (run.status !== 'completed' || run.findings_count === null) return null
  // Simple heuristic — a proper score would require the full summary.
  // Colour is enough to communicate rough state.
  if (run.findings_count === 0) {
    return { label: 'PRODUCTION READY', bg: 'color-mix(in srgb, var(--color-completed) 15%, transparent)', color: 'var(--color-completed)' }
  }
  if (run.findings_count <= 5) {
    return { label: 'NEEDS IMPROVEMENT', bg: 'color-mix(in srgb, var(--color-medium) 15%, transparent)', color: 'var(--color-medium)' }
  }
  return { label: 'NOT PRODUCTION READY', bg: 'color-mix(in srgb, var(--color-critical) 15%, transparent)', color: 'var(--color-critical)' }
}

export function HistoryPage() {
  const [runs, setRuns] = useState<ReviewRun[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchRuns = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await api.listRuns(page * LIMIT, LIMIT)
      setRuns(data.items)
      setTotal(data.total)
    } catch {
      setError('Failed to load run history.')
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    fetchRuns()
  }, [fetchRuns])

  return (
    <main className="history-page">
      <div className="history-page__header">
        <h1 className="history-page__heading">Review History</h1>
        <button
          className="btn btn--ghost"
          onClick={fetchRuns}
          disabled={loading}
          aria-label="Refresh history"
        >
          <RefreshCw size={15} className={loading ? 'spin' : undefined} aria-hidden="true" />
          Refresh
        </button>
      </div>

      {error && (
        <p className="error-banner" role="alert">{error}</p>
      )}

      {loading && runs.length === 0 ? (
        <div className="history-page__loading" aria-busy="true">
          <Loader2 size={28} className="spin" aria-label="Loading history" />
        </div>
      ) : runs.length === 0 ? (
        <div className="history-page__empty">
          <Clock size={48} style={{ color: 'var(--color-border)' }} aria-hidden="true" />
          <p>No reviews yet.</p>
          <Link to="/" className="btn btn--primary">
            Start your first review
          </Link>
        </div>
      ) : (
        <>
          <div className="run-table" role="table" aria-label="Review runs">
            {/* Header */}
            <div
              className="run-table__head"
              role="row"
              style={{ gridTemplateColumns: '2fr 1fr 160px 100px 80px' }}
            >
              <span role="columnheader">Repository</span>
              <span role="columnheader">Verdict</span>
              <span role="columnheader">Date</span>
              <span role="columnheader">Status</span>
              <span role="columnheader" aria-label="Actions" />
            </div>

            {runs.map(run => {
              const verdict = verdictFromRun(run)
              return (
                <div
                  key={run.id}
                  className="run-table__row"
                  role="row"
                  style={{ gridTemplateColumns: '2fr 1fr 160px 100px 80px' }}
                >
                  {/* Repo */}
                  <span className="run-table__repo" role="cell">
                    <span className="run-table__url" title={run.git_url}>
                      {repoShortName(run.git_url)}
                    </span>
                    <code className="run-table__id">{run.id.slice(0, 8)}</code>
                  </span>

                  {/* Verdict badge */}
                  <span role="cell">
                    {verdict ? (
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          padding: '2px 8px',
                          borderRadius: 4,
                          fontSize: 'var(--text-xs)',
                          fontWeight: 700,
                          letterSpacing: '0.04em',
                          background: verdict.bg,
                          color: verdict.color,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {verdict.label}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>—</span>
                    )}
                  </span>

                  {/* Date */}
                  <span role="cell" className="run-table__date">
                    {formatDate(run.created_at)}
                  </span>

                  {/* Status */}
                  <span role="cell">
                    <StatusBadge status={run.status} />
                  </span>

                  {/* Actions */}
                  <span role="cell" className="run-table__actions">
                    <Link
                      to={`/results/${run.id}`}
                      className="btn btn--ghost btn--sm"
                      aria-label={`View results for ${repoShortName(run.git_url)}`}
                    >
                      <ExternalLink size={14} aria-hidden="true" />
                      View
                    </Link>
                  </span>
                </div>
              )
            })}
          </div>

          {total > LIMIT && (
            <nav className="pagination" aria-label="History pagination">
              <button
                className="btn btn--ghost"
                disabled={page === 0}
                onClick={() => setPage(p => p - 1)}
              >
                Previous
              </button>
              <span className="pagination__info">
                Page {page + 1} of {Math.ceil(total / LIMIT)}
              </span>
              <button
                className="btn btn--ghost"
                disabled={(page + 1) * LIMIT >= total}
                onClick={() => setPage(p => p + 1)}
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </main>
  )
}
