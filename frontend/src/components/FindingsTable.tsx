import { useState, useEffect, useCallback, useId } from 'react'
import { ChevronDown, ChevronRight, Filter, Search } from 'lucide-react'
import { api } from '../lib/api.ts'
import type { Finding, Severity } from '../lib/api.ts'

const PAGE_SIZE = 25

const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'info']

const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
}

function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`badge badge--${severity}`}>
      {severity.charAt(0).toUpperCase() + severity.slice(1)}
    </span>
  )
}

function FileLine({ filePath, lineStart }: { filePath: string; lineStart: number | null }) {
  const short = filePath.split('/').slice(-2).join('/')
  return (
    <code
      style={{ fontSize: 'var(--text-xs)', color: 'var(--color-accent)', wordBreak: 'break-all' }}
      title={filePath}
    >
      {short}{lineStart != null ? `:${lineStart}` : ''}
    </code>
  )
}

function ExpandedRow({ finding }: { finding: Finding }) {
  return (
    <tr aria-live="polite">
      <td colSpan={5} style={{ padding: 0 }}>
        <div
          style={{
            background: 'var(--color-surface-2)',
            borderTop: '1px solid var(--color-border)',
            padding: 'var(--space-4)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-4)',
          }}
        >
          {/* Location */}
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
            <span>File:</span>
            <FileLine filePath={finding.file_path} lineStart={finding.line_start} />
            {finding.line_end && finding.line_end !== finding.line_start && (
              <span>→ :{finding.line_end}</span>
            )}
          </div>

          {/* Description */}
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', lineHeight: 1.6 }}>
            {finding.description}
          </p>

          {/* Suggestion */}
          {finding.suggestion && (
            <div
              style={{
                background: 'var(--color-surface)',
                borderLeft: '3px solid var(--color-accent)',
                borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
                padding: 'var(--space-3) var(--space-4)',
              }}
            >
              <div
                style={{
                  fontSize: 'var(--text-xs)',
                  color: 'var(--color-accent)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  fontWeight: 700,
                  marginBottom: 'var(--space-2)',
                }}
              >
                Suggestion
              </div>
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                {finding.suggestion}
              </p>
            </div>
          )}
        </div>
      </td>
    </tr>
  )
}

interface FindingsTableProps {
  runId: string
}

export function FindingsTable({ runId }: FindingsTableProps) {
  const searchId = useId()
  const severityId = useId()
  const agentId = useId()

  const [findings, setFindings] = useState<Finding[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(false)

  const [filterSeverity, setFilterSeverity] = useState<Severity | ''>('')
  const [filterAgent, setFilterAgent] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const fetchFindings = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.getFindings(runId, {
        severity: filterSeverity || undefined,
        category: filterAgent || undefined,
        file_path: searchQuery || undefined,
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
      })
      // Sort client-side by severity order
      const sorted = [...data.items].sort(
        (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
      )
      setFindings(sorted)
      setTotal(data.total)
    } catch {
      // Non-fatal — table stays empty
    } finally {
      setLoading(false)
    }
  }, [runId, filterSeverity, filterAgent, searchQuery, page])

  useEffect(() => {
    fetchFindings()
  }, [fetchFindings])

  // Reset page when filters change
  useEffect(() => {
    setPage(0)
  }, [filterSeverity, filterAgent, searchQuery])

  function toggleRow(id: string) {
    setExpandedId(prev => (prev === id ? null : id))
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      {/* Toolbar */}
      <div
        style={{
          display: 'flex',
          gap: 'var(--space-3)',
          flexWrap: 'wrap',
          alignItems: 'center',
        }}
      >
        {/* Search */}
        <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
          <Search
            size={14}
            style={{
              position: 'absolute',
              left: 10,
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--color-text-muted)',
              pointerEvents: 'none',
            }}
            aria-hidden="true"
          />
          <input
            id={searchId}
            type="search"
            placeholder="Search by file or title…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            aria-label="Search findings"
            style={{
              width: '100%',
              background: 'var(--color-surface-2)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius)',
              color: 'var(--color-text)',
              font: 'inherit',
              fontSize: 'var(--text-sm)',
              padding: 'var(--space-2) var(--space-3) var(--space-2) 30px',
            }}
          />
        </div>

        {/* Severity filter */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <Filter size={14} style={{ color: 'var(--color-text-muted)' }} aria-hidden="true" />
          <label htmlFor={severityId} style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600 }}>
            Severity
          </label>
          <select
            id={severityId}
            className="select"
            value={filterSeverity}
            onChange={e => setFilterSeverity(e.target.value as Severity | '')}
          >
            <option value="">All</option>
            {SEVERITIES.map(s => (
              <option key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
        </div>

        {/* Agent filter */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <label htmlFor={agentId} style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600 }}>
            Agent
          </label>
          <select
            id={agentId}
            className="select"
            value={filterAgent}
            onChange={e => setFilterAgent(e.target.value)}
          >
            <option value="">All</option>
            <option value="bug">Bug</option>
            <option value="security">Security</option>
            <option value="coverage">Coverage</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden',
        }}
      >
        {loading ? (
          <div
            style={{
              display: 'flex',
              justifyContent: 'center',
              padding: 'var(--space-12)',
              color: 'var(--color-text-muted)',
            }}
            aria-busy="true"
            aria-label="Loading findings"
          >
            <span
              className="spin"
              style={{
                display: 'inline-block',
                width: 24,
                height: 24,
                border: '2px solid var(--color-border)',
                borderTopColor: 'var(--color-accent)',
                borderRadius: '50%',
              }}
              aria-hidden="true"
            />
          </div>
        ) : findings.length === 0 ? (
          <p
            style={{
              textAlign: 'center',
              padding: 'var(--space-12)',
              color: 'var(--color-text-muted)',
            }}
          >
            No findings match the current filters.
          </p>
        ) : (
          <table
            style={{ width: '100%', borderCollapse: 'collapse' }}
            aria-label="Findings"
          >
            <thead>
              <tr
                style={{
                  background: 'var(--color-surface-2)',
                  borderBottom: '1px solid var(--color-border)',
                }}
              >
                {['', 'Severity', 'Agent', 'Title', 'File : Line'].map(col => (
                  <th
                    key={col}
                    scope="col"
                    style={{
                      padding: 'var(--space-2) var(--space-3)',
                      fontSize: 'var(--text-xs)',
                      fontWeight: 600,
                      color: 'var(--color-text-muted)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      textAlign: 'left',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {findings.map(finding => {
                const isExpanded = expandedId === finding.id
                return (
                  <>
                    <tr
                      key={finding.id}
                      onClick={() => toggleRow(finding.id)}
                      aria-expanded={isExpanded}
                      style={{
                        borderBottom: '1px solid var(--color-border)',
                        cursor: 'pointer',
                        transition: 'background var(--duration-fast)',
                        background: isExpanded ? 'var(--color-surface-2)' : 'transparent',
                      }}
                      onMouseEnter={e => { if (!isExpanded) (e.currentTarget as HTMLTableRowElement).style.background = 'color-mix(in srgb, var(--color-surface-2) 60%, transparent)' }}
                      onMouseLeave={e => { if (!isExpanded) (e.currentTarget as HTMLTableRowElement).style.background = 'transparent' }}
                    >
                      {/* Expand toggle */}
                      <td style={{ padding: 'var(--space-2) var(--space-3)', width: 24 }}>
                        {isExpanded
                          ? <ChevronDown size={14} style={{ color: 'var(--color-text-muted)' }} aria-hidden="true" />
                          : <ChevronRight size={14} style={{ color: 'var(--color-text-muted)' }} aria-hidden="true" />}
                      </td>

                      {/* Severity */}
                      <td style={{ padding: 'var(--space-2) var(--space-3)', whiteSpace: 'nowrap' }}>
                        <SeverityBadge severity={finding.severity} />
                      </td>

                      {/* Agent */}
                      <td style={{ padding: 'var(--space-2) var(--space-3)' }}>
                        <span
                          style={{
                            fontSize: 'var(--text-xs)',
                            background: 'var(--color-surface-2)',
                            color: 'var(--color-text-muted)',
                            padding: '2px 6px',
                            borderRadius: 'var(--radius-sm)',
                            textTransform: 'capitalize',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {finding.agent}
                        </span>
                      </td>

                      {/* Title */}
                      <td style={{ padding: 'var(--space-2) var(--space-3)', fontSize: 'var(--text-sm)', fontWeight: 500, maxWidth: 360 }}>
                        <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {finding.title}
                        </div>
                        {finding.suggestion && (
                          <div
                            style={{
                              fontSize: 'var(--text-xs)',
                              color: 'var(--color-text-muted)',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              marginTop: 2,
                            }}
                          >
                            {finding.suggestion.slice(0, 80)}{finding.suggestion.length > 80 ? '…' : ''}
                          </div>
                        )}
                      </td>

                      {/* File:line */}
                      <td style={{ padding: 'var(--space-2) var(--space-3)', maxWidth: 200 }}>
                        <FileLine filePath={finding.file_path} lineStart={finding.line_start} />
                      </td>
                    </tr>
                    {isExpanded && <ExpandedRow key={`${finding.id}-exp`} finding={finding} />}
                  </>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <nav className="pagination" aria-label="Findings pagination">
          <button
            className="btn btn--ghost"
            disabled={page === 0}
            onClick={() => setPage(p => p - 1)}
          >
            Previous
          </button>
          <span className="pagination__info">
            Page {page + 1} of {totalPages}
            <span style={{ marginLeft: 'var(--space-4)', color: 'var(--color-text-muted)' }}>
              ({total} total)
            </span>
          </span>
          <button
            className="btn btn--ghost"
            disabled={(page + 1) * PAGE_SIZE >= total}
            onClick={() => setPage(p => p + 1)}
          >
            Next
          </button>
        </nav>
      )}
    </div>
  )
}
