import clsx from 'clsx'
import type { RunStatus, Severity } from '../lib/api.ts'

// ── Run status badge ──────────────────────────────────────────────────────────

interface StatusBadgeProps {
  status: RunStatus
}

const STATUS_STYLES: Record<RunStatus, string> = {
  pending: 'badge--pending',
  running: 'badge--running',
  completed: 'badge--completed',
  failed: 'badge--failed',
}

const STATUS_LABELS: Record<RunStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
}

export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span className={clsx('badge', STATUS_STYLES[status])}>
      {status === 'running' && <span className="badge__dot" aria-hidden="true" />}
      {STATUS_LABELS[status]}
    </span>
  )
}

// ── Severity badge ────────────────────────────────────────────────────────────

interface SeverityBadgeProps {
  severity: Severity
}

const SEVERITY_STYLES: Record<Severity, string> = {
  critical: 'badge--critical',
  high: 'badge--high',
  medium: 'badge--medium',
  low: 'badge--low',
  info: 'badge--info',
}

export function SeverityBadge({ severity }: SeverityBadgeProps) {
  return (
    <span className={clsx('badge', SEVERITY_STYLES[severity])}>
      {severity.charAt(0).toUpperCase() + severity.slice(1)}
    </span>
  )
}
