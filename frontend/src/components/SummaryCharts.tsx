import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
  Legend,
} from 'recharts'
import type { ReportSummary, Severity } from '../lib/api.ts'

interface SummaryChartsProps {
  summary: ReportSummary
}

const SEVERITY_COLORS: Record<Severity, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#3b82f6',
  info: '#6b7280',
}

export function SummaryCharts({ summary }: SummaryChartsProps) {
  const severityData = (Object.entries(summary.findings_by_severity) as [Severity, number][])
    .filter(([, count]) => count > 0)
    .map(([sev, count]) => ({ name: sev.charAt(0).toUpperCase() + sev.slice(1), value: count, sev }))

  const categoryData = Object.entries(summary.findings_by_category)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 8)
    .map(([name, count]) => ({ name, count }))

  return (
    <div className="charts">
      <section className="charts__panel" aria-label="Findings by severity">
        <h3 className="charts__heading">By Severity</h3>
        <ResponsiveContainer width="100%" height={200}>
          <PieChart>
            <Pie
              data={severityData}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius={70}
              label={({ name, value }: { name: string; value: number }) => `${name}: ${value}`}
            >
              {severityData.map((entry) => (
                <Cell key={entry.sev} fill={SEVERITY_COLORS[entry.sev as Severity]} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
              labelStyle={{ color: '#f8fafc' }}
            />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </section>

      <section className="charts__panel" aria-label="Findings by category">
        <h3 className="charts__heading">By Category</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={categoryData} layout="vertical" margin={{ left: 16, right: 16 }}>
            <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 11 }} />
            <YAxis
              type="category"
              dataKey="name"
              width={120}
              tick={{ fill: '#94a3b8', fontSize: 11 }}
            />
            <Tooltip
              contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
              labelStyle={{ color: '#f8fafc' }}
            />
            <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </section>
    </div>
  )
}
