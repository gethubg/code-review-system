import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { api } from '../lib/api.ts'
import { useProgressFeed } from '../lib/ws.ts'
import { ProgressFeed } from '../components/ProgressFeed.tsx'
import { ProductionScore } from '../components/ProductionScore.tsx'
import { SeverityChart } from '../components/SeverityChart.tsx'
import { SeverityPie } from '../components/SeverityPie.tsx'
import { FindingsTable } from '../components/FindingsTable.tsx'
import { ReportViewer } from '../components/ReportViewer.tsx'
import { DownloadPanel } from '../components/DownloadPanel.tsx'
import { StatusBadge } from '../components/StatusBadge.tsx'
import type { ReviewRun, ReportSummary } from '../lib/api.ts'

const POLL_INTERVAL_MS = 3_000

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function repoName(gitUrl: string): string {
  try {
    return new URL(gitUrl).pathname.replace(/^\//, '').replace(/\.git$/, '')
  } catch {
    return gitUrl
  }
}

function verdictColor(verdict: string): string {
  if (verdict === 'PRODUCTION READY') return 'var(--color-completed)'
  if (verdict === 'NEEDS IMPROVEMENT') return 'var(--color-medium)'
  return 'var(--color-critical)'
}

function agentBreakdown(summary: ReportSummary): Array<{ name: string; count: number; color: string }> {
  const cats = summary.finding_counts_by_agent
  return [
    { name: 'Bug Agent',      count: cats['bug'] ?? 0,      color: '#f59e0b' },
    { name: 'Security Agent', count: cats['security'] ?? 0, color: '#ef4444' },
    { name: 'Coverage Agent', count: cats['coverage'] ?? 0, color: '#22c55e' },
  ]
}

function totalFindings(summary: ReportSummary): number {
  return Object.values(summary.finding_counts_by_severity).reduce((a, b) => a + b, 0)
}

export function ResultsPage() {
  const { runId } = useParams<{ runId: string }>()

  const [run, setRun] = useState<ReviewRun | null>(null)
  const [summary, setSummary] = useState<ReportSummary | null>(null)
  const [markdownReport, setMarkdownReport] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const isActive = run?.status === 'pending' || run?.status === 'running'

  const { messages, isConnected } = useProgressFeed(isActive ? (runId ?? null) : null)

  // ── data fetching ────────────────────────────────────────────────────────────

  const fetchRun = useCallback(async () => {
    if (!runId) return null
    try {
      const { data } = await api.getRun(runId)
      setRun(data)
      return data
    } catch {
      setLoadError('Could not load run details.')
      return null
    }
  }, [runId])

  const fetchSummary = useCallback(async () => {
    if (!runId) return
    try {
      const { data } = await api.getReportSummary(runId)
      setSummary(data)
    } catch {
      // Non-fatal — summary may not be ready immediately.
    }
  }, [runId])

  const fetchMarkdownReport = useCallback(async () => {
    if (!runId) return
    try {
      const { data } = await api.downloadReport(runId, 'markdown')
      const text = await (data as Blob).text()
      setMarkdownReport(text)
    } catch {
      // Non-fatal.
    }
  }, [runId])

  // Polling loop while run is active
  useEffect(() => {
    if (!runId) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    async function poll() {
      const latest = await fetchRun()
      if (cancelled) return
      if (latest?.status === 'completed') {
        fetchSummary()
        fetchMarkdownReport()
        return
      }
      if (latest?.status === 'failed') return
      timer = setTimeout(poll, POLL_INTERVAL_MS)
    }

    poll()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [runId, fetchRun, fetchSummary, fetchMarkdownReport])

  // ── render states ────────────────────────────────────────────────────────────

  if (loadError) {
    return (
      <main className="results-page">
        <p className="error-banner" role="alert">{loadError}</p>
        <Link to="/" className="btn btn--secondary" style={{ marginTop: '1rem', alignSelf: 'flex-start' }}>
          <ArrowLeft size={16} aria-hidden="true" /> Back
        </Link>
      </main>
    )
  }

  if (!run) {
    return (
      <main className="results-page results-page--loading" aria-busy="true">
        <Loader2 size={32} className="spin" aria-label="Loading run details" />
      </main>
    )
  }

  const score = summary?.score ?? null
  const verdict = summary ? { label: summary.verdict, color: verdictColor(summary.verdict) } : null
  const agents = summary ? agentBreakdown(summary) : []
  const total = summary ? totalFindings(summary) : 0

  return (
    <main className="results-page">
      {/* Top bar */}
      <header className="results-page__topbar">
        <Link to="/" className="btn btn--ghost" style={{ alignSelf: 'flex-start' }}>
          <ArrowLeft size={16} aria-hidden="true" /> Back
        </Link>
        <div className="results-page__title-row">
          <h1 className="results-page__heading">{repoName(run.git_url)}</h1>
          <StatusBadge status={run.status} />
        </div>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
          {run.git_url} &mdash; started {formatDate(run.created_at)}
          {run.completed_at && `, completed ${formatDate(run.completed_at)}`}
        </p>
      </header>

      {/* Live feed while running */}
      {isActive && (
        <section aria-label="Live review progress">
          <ProgressFeed messages={messages} isConnected={isConnected} />
        </section>
      )}

      {/* Failed state */}
      {run.status === 'failed' && (
        <div className="error-banner" role="alert">
          <strong>Review failed.</strong>{' '}
          {run.error ?? 'An unexpected error occurred.'}
        </div>
      )}

      {/* Completed — main dashboard */}
      {run.status === 'completed' && summary && score !== null && verdict !== null && (
        <>
          {/* Production score (centered, prominent) */}
          <section aria-label="Production score" style={{ display: 'flex', justifyContent: 'center' }}>
            <ProductionScore
              score={score}
              verdict={verdict.label}
              verdictColor={verdict.color}
              totalFindings={total}
            />
          </section>

          {/* Charts row */}
          <section className="charts" aria-label="Findings breakdown">
            <div className="charts__panel">
              <h2 className="charts__heading">By Severity</h2>
              <SeverityChart findingsBySeverity={summary.finding_counts_by_severity} />
            </div>
            <div className="charts__panel">
              <h2 className="charts__heading">By Agent</h2>
              <SeverityPie agents={agents} totalFindings={total} />
            </div>
          </section>

          {/* Agent breakdown cards */}
          <section
            aria-label="Agent breakdown"
            style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-4)' }}
          >
            {agents.map(agent => (
              <article
                key={agent.name}
                style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-lg)',
                  padding: 'var(--space-6)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 'var(--space-2)',
                }}
              >
                <span
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: '50%',
                    background: agent.color,
                    display: 'inline-block',
                  }}
                  aria-hidden="true"
                />
                <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>{agent.name}</span>
                <span
                  style={{
                    fontSize: 'var(--text-3xl)',
                    fontWeight: 800,
                    letterSpacing: '-0.02em',
                    color: agent.count > 0 ? agent.color : 'var(--color-text-muted)',
                  }}
                >
                  {agent.count}
                </span>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {agent.count === 1 ? 'finding' : 'findings'}
                </span>
              </article>
            ))}
          </section>

          {/* Findings table */}
          <section aria-label="All findings">
            <h2
              style={{
                fontSize: 'var(--text-xl)',
                fontWeight: 700,
                marginBottom: 'var(--space-4)',
              }}
            >
              Findings
              <span style={{ marginLeft: 'var(--space-2)', fontWeight: 400, color: 'var(--color-text-muted)', fontSize: 'var(--text-base)' }}>
                ({total})
              </span>
            </h2>
            {runId && <FindingsTable runId={runId} />}
          </section>

          {/* Markdown report */}
          {markdownReport && (
            <section aria-label="Full report">
              <ReportViewer markdown={markdownReport} />
            </section>
          )}

          {/* Download panel */}
          {runId && (
            <section aria-label="Download report">
              <DownloadPanel runId={runId} />
            </section>
          )}
        </>
      )}
    </main>
  )
}
