import { useState } from 'react'
import { ChevronDown, ChevronRight, FileCode, MapPin } from 'lucide-react'
import { SeverityBadge } from './StatusBadge.tsx'
import type { Finding } from '../lib/api.ts'

interface FindingCardProps {
  finding: Finding
}

export function FindingCard({ finding }: FindingCardProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <article className="finding-card">
      <button
        className="finding-card__header"
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
      >
        <span className="finding-card__toggle" aria-hidden="true">
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </span>

        <SeverityBadge severity={finding.severity} />

        <span className="finding-card__title">{finding.title}</span>

        <span className="finding-card__meta">
          <span className="finding-card__category">{finding.category}</span>
          <span className="finding-card__agent">{finding.agent}</span>
        </span>
      </button>

      {expanded && (
        <div className="finding-card__body">
          <div className="finding-card__location">
            <FileCode size={14} aria-hidden="true" />
            <code>{finding.file_path}</code>
            {finding.line_start != null && (
              <>
                <MapPin size={14} aria-hidden="true" />
                <span>
                  Line {finding.line_start}
                  {finding.line_end != null && finding.line_end !== finding.line_start
                    ? `–${finding.line_end}`
                    : ''}
                </span>
              </>
            )}
          </div>

          <p className="finding-card__desc">{finding.description}</p>

          {finding.suggestion && (
            <div className="finding-card__suggestion">
              <strong>Suggestion</strong>
              <p>{finding.suggestion}</p>
            </div>
          )}
        </div>
      )}
    </article>
  )
}
