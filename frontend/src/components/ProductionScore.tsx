interface ProductionScoreProps {
  score: number
  verdict: string
  verdictColor: string
  totalFindings: number
}

const SIZE = 200
const STROKE = 16
const RADIUS = (SIZE - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

function scoreArcColor(score: number): string {
  if (score >= 75) return '#22c55e'
  if (score >= 50) return '#eab308'
  return '#ef4444'
}

export function ProductionScore({
  score,
  verdict,
  verdictColor,
  totalFindings,
}: ProductionScoreProps) {
  // Arc goes from top (270deg) clockwise. We draw the filled portion.
  const clamped = Math.max(0, Math.min(100, score))
  const filled = (clamped / 100) * CIRCUMFERENCE
  const gap = CIRCUMFERENCE - filled
  const arcColor = scoreArcColor(score)

  return (
    <figure
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 'var(--space-3)',
        padding: 'var(--space-8)',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-xl)',
        minWidth: 260,
      }}
      aria-label={`Production score: ${score} — ${verdict}`}
    >
      {/* SVG gauge */}
      <div style={{ position: 'relative', width: SIZE, height: SIZE }}>
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          aria-hidden="true"
          style={{ transform: 'rotate(-90deg)' }}
        >
          {/* Track */}
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke="var(--color-border)"
            strokeWidth={STROKE}
          />
          {/* Filled arc */}
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke={arcColor}
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={`${filled} ${gap}`}
            style={{ transition: 'stroke-dasharray 0.6s var(--ease-out)' }}
          />
        </svg>

        {/* Center label */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 2,
          }}
        >
          <span
            style={{
              fontSize: 52,
              fontWeight: 800,
              letterSpacing: '-0.03em',
              lineHeight: 1,
              color: arcColor,
            }}
          >
            {score}
          </span>
          <span
            style={{
              fontSize: 'var(--text-xs)',
              fontWeight: 600,
              color: 'var(--color-text-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
            }}
          >
            / 100
          </span>
        </div>
      </div>

      {/* Verdict */}
      <figcaption style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-2)' }}>
        <span
          style={{
            fontSize: 'var(--text-sm)',
            fontWeight: 800,
            letterSpacing: '0.06em',
            color: verdictColor,
            textTransform: 'uppercase',
            padding: '4px 12px',
            background: `color-mix(in srgb, ${verdictColor} 15%, transparent)`,
            borderRadius: 'var(--radius-sm)',
          }}
        >
          {verdict}
        </span>
        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
          {totalFindings} {totalFindings === 1 ? 'finding' : 'findings'} total
        </span>
      </figcaption>
    </figure>
  )
}
