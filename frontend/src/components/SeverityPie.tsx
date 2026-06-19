import {
  PieChart,
  Pie,
  Cell,
  Legend,
  Tooltip,
  ResponsiveContainer,
  TooltipProps,
} from 'recharts'

interface AgentSlice {
  name: string
  count: number
  color: string
}

interface SeverityPieProps {
  agents: AgentSlice[]
  totalFindings: number
}

function CustomTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload as AgentSlice
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
      <strong style={{ color: d.color }}>{d.name}</strong>
      <div style={{ color: 'var(--color-text-muted)', marginTop: 4 }}>
        {d.count} finding{d.count !== 1 ? 's' : ''}
      </div>
    </div>
  )
}

function renderInnerLabel(total: number) {
  return function InnerLabel({ cx, cy }: { cx: number; cy: number }) {
    return (
      <>
        <text
          x={cx}
          y={cy - 6}
          textAnchor="middle"
          dominantBaseline="middle"
          style={{ fontSize: 28, fontWeight: 800, fill: 'var(--color-text)' }}
        >
          {total}
        </text>
        <text
          x={cx}
          y={cy + 18}
          textAnchor="middle"
          dominantBaseline="middle"
          style={{ fontSize: 11, fill: '#94a3b8', letterSpacing: '0.05em' }}
        >
          TOTAL
        </text>
      </>
    )
  }
}

export function SeverityPie({ agents, totalFindings }: SeverityPieProps) {
  // Filter out zero-count slices so the donut doesn't show phantom wedges.
  const data = agents.filter(a => a.count > 0)

  // If no findings at all, show a placeholder ring.
  if (data.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: 220,
          color: 'var(--color-text-muted)',
          fontSize: 'var(--text-sm)',
        }}
      >
        No findings
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie
          data={data}
          dataKey="count"
          nameKey="name"
          cx="50%"
          cy="50%"
          innerRadius={55}
          outerRadius={80}
          paddingAngle={3}
          label={renderInnerLabel(totalFindings)}
          labelLine={false}
        >
          {data.map(entry => (
            <Cell key={entry.name} fill={entry.color} />
          ))}
        </Pie>
        <Tooltip content={<CustomTooltip />} />
        <Legend
          formatter={(value: string) => (
            <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)' }}>
              {value}
            </span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}
