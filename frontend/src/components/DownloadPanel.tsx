import { useState } from 'react'
import { Download, FileJson, FileText, Printer } from 'lucide-react'
import { api } from '../lib/api.ts'

interface DownloadPanelProps {
  runId: string
}

type DownloadFormat = 'json' | 'markdown'

async function triggerDownload(runId: string, format: DownloadFormat) {
  const { data } = await api.downloadReport(runId, format)
  const blob = data as Blob
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `code-review-${runId.slice(0, 8)}.${format === 'json' ? 'json' : 'md'}`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function DownloadPanel({ runId }: DownloadPanelProps) {
  const [downloading, setDownloading] = useState<DownloadFormat | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleDownload(format: DownloadFormat) {
    setDownloading(format)
    setError(null)
    try {
      await triggerDownload(runId, format)
    } catch {
      setError(`Failed to download ${format} report.`)
    } finally {
      setDownloading(null)
    }
  }

  return (
    <div
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-lg)',
        padding: 'var(--space-6)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-4)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
        <Download size={16} style={{ color: 'var(--color-accent)' }} aria-hidden="true" />
        <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}>Export Report</h2>
      </div>

      <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
        {/* JSON */}
        <button
          type="button"
          className="btn btn--secondary"
          onClick={() => handleDownload('json')}
          disabled={downloading !== null}
          aria-label="Download report as JSON"
          style={{ flex: 1, minWidth: 140, justifyContent: 'center', padding: 'var(--space-3) var(--space-4)' }}
        >
          {downloading === 'json' ? (
            <span
              className="spin"
              style={{
                display: 'inline-block',
                width: 14,
                height: 14,
                border: '2px solid var(--color-border)',
                borderTopColor: 'var(--color-text)',
                borderRadius: '50%',
              }}
              aria-hidden="true"
            />
          ) : (
            <FileJson size={16} aria-hidden="true" />
          )}
          Download JSON
        </button>

        {/* Markdown */}
        <button
          type="button"
          className="btn btn--secondary"
          onClick={() => handleDownload('markdown')}
          disabled={downloading !== null}
          aria-label="Download report as Markdown"
          style={{ flex: 1, minWidth: 140, justifyContent: 'center', padding: 'var(--space-3) var(--space-4)' }}
        >
          {downloading === 'markdown' ? (
            <span
              className="spin"
              style={{
                display: 'inline-block',
                width: 14,
                height: 14,
                border: '2px solid var(--color-border)',
                borderTopColor: 'var(--color-text)',
                borderRadius: '50%',
              }}
              aria-hidden="true"
            />
          ) : (
            <FileText size={16} aria-hidden="true" />
          )}
          Download Markdown
        </button>

        {/* Print */}
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() => window.print()}
          aria-label="Print report"
          style={{ flex: 1, minWidth: 140, justifyContent: 'center', padding: 'var(--space-3) var(--space-4)' }}
        >
          <Printer size={16} aria-hidden="true" />
          Print / PDF
        </button>
      </div>

      {error && (
        <p role="alert" style={{ fontSize: 'var(--text-sm)', color: 'var(--color-critical)' }}>
          {error}
        </p>
      )}

      {/* Print-only styles */}
      <style>{`
        @media print {
          .navbar,
          [aria-label="Live review progress"],
          [aria-label="Export report"],
          .btn {
            display: none !important;
          }
          body {
            background: #fff !important;
            color: #000 !important;
          }
        }
      `}</style>
    </div>
  )
}
