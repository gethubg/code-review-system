import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  TooltipProps,
} from 'recharts'
import type { Severity } from '../lib/api.ts'

interface SeverityChartProps {
  findingsBySeverity: Partial<Record<Severity, number>>
}

const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'info']

const SEVERITY_COLORS: Record<Severity, string> = {
  critical: '#ef4444',
  high:     '#f97316',
  medium:   '#f59e0b',
  low:      '#22c55e',
  info:     '#64748b',
}

interface ChartDatum {
  name: string
  count: number
  sev: Severity
  pct: string
}

function CustomTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload as ChartDatum
  return (
    <div
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius)',
        padding: '8px 12px',
        fontSize: 'var(--text-sm)',
        color: 'var(--color-text)',
      }}
    >
      <strong style={{ color: SEVERITY_COLORS[d.sev] }}>{d.name}</strong>
      <div style={{ color: 'var(--color-text-muted)', marginTop: 4 }}>
        {d.count} finding{d.count !== 1 ? 's' : ''} ({d.pct}%)
      </div>
    </div>
  )
}

export function SeverityChart({ findingsBySeverity }: SeverityChartProps) {
  const total = Object.values(findingsBySeverity).reduce((s, n) => s + (n ?? 0), 0)

  const data: ChartDatum[] = SEVERITIES.map(sev => {
    const count = findingsBySeverity[sev] ?? 0
    return {
      name: sev.charAt(0).toUpperCase() + sev.slice(1),
      count,
      sev,
      pct: total > 0 ? ((count / total) * 100).toFixed(1) : '0.0',
    }
  })

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
        <XAxis
          dataKey="name"
          tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          allowDecimals={false}
          tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
        <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={48}>
          {data.map(d => (
            <Cell key={d.sev} fill={SEVERITY_COLORS[d.sev]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
