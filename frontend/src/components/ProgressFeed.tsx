import { useEffect, useRef } from 'react'
import { CheckCircle, AlertCircle, Activity, Bot, Zap } from 'lucide-react'
import { useProgressFeed } from '../lib/ws.ts'
import type { ProgressMessage, ProgressEventType } from '../lib/ws.ts'

// ── Icon map ─────────────────────────────────────────────────────────────────

const TYPE_ICONS: Record<ProgressEventType, React.ReactNode> = {
  agent_start:    <Bot     size={13} aria-hidden="true" />,
  agent_complete: <CheckCircle size={13} aria-hidden="true" />,
  finding:        <Zap     size={13} aria-hidden="true" />,
  progress:       <Activity size={13} aria-hidden="true" />,
  error:          <AlertCircle size={13} aria-hidden="true" />,
  complete:       <CheckCircle size={13} aria-hidden="true" />,
}

const TYPE_MSG_COLORS: Record<ProgressEventType, string> = {
  agent_start:    '#a78bfa',
  agent_complete: 'var(--color-completed)',
  finding:        'var(--color-high)',
  progress:       'var(--color-text)',
  error:          'var(--color-critical)',
  complete:       'var(--color-completed)',
}

const TYPE_ICON_COLORS: Record<ProgressEventType, string> = {
  agent_start:    '#a78bfa',
  agent_complete: 'var(--color-completed)',
  finding:        'var(--color-high)',
  progress:       'var(--color-text-muted)',
  error:          'var(--color-critical)',
  complete:       'var(--color-completed)',
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return iso
  }
}

// ── Props ────────────────────────────────────────────────────────────────────

// Two usage modes:
//   1. Pass `runId` — the component manages its own WebSocket connection.
//   2. Pass `messages` + `isConnected` — caller owns the connection (ResultsPage).
type ProgressFeedProps =
  | { runId: string; messages?: never; isConnected?: never }
  | { runId?: never; messages: ProgressMessage[]; isConnected: boolean }

// ── Component ────────────────────────────────────────────────────────────────

export function ProgressFeed(props: ProgressFeedProps) {
  // When runId is provided we manage the hook here; otherwise we use props.
  const ownFeed = useProgressFeed(props.runId ?? null)

  const messages   = props.runId !== undefined ? ownFeed.messages   : (props.messages ?? [])
  const isConnected = props.runId !== undefined ? ownFeed.isConnected : (props.isConnected ?? false)

  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const isDone = messages.some(m => m.type === 'complete' || m.type === 'error')

  return (
    <section
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
      }}
      aria-label="Live progress feed"
    >
      {/* Header */}
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: 'var(--space-3) var(--space-4)',
          borderBottom: '1px solid var(--color-border)',
          background: 'var(--color-surface-2)',
        }}
      >
        <span style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>Live Progress</span>
        <span
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            fontSize: 'var(--text-xs)',
            fontWeight: 600,
            color: isDone
              ? 'var(--color-completed)'
              : isConnected
              ? 'var(--color-completed)'
              : 'var(--color-text-muted)',
          }}
          aria-live="polite"
        >
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: '50%',
              background: 'currentColor',
              animation: isConnected && !isDone ? 'pulse-dot 1.2s ease-in-out infinite' : 'none',
            }}
            aria-hidden="true"
          />
          {isDone ? 'Review complete' : isConnected ? 'Connected' : 'Connecting…'}
        </span>
      </header>

      {/* Body */}
      <div
        role="log"
        aria-live="polite"
        aria-atomic="false"
        aria-label="Progress messages"
        style={{
          fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
          fontSize: 'var(--text-xs)',
          padding: 'var(--space-3) var(--space-4)',
          maxHeight: 320,
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
        }}
      >
        {messages.length === 0 ? (
          <p style={{ color: 'var(--color-text-muted)', fontStyle: 'italic', fontFamily: 'inherit' }}>
            Connecting…
          </p>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                gap: 'var(--space-2)',
                alignItems: 'baseline',
                lineHeight: 1.5,
              }}
            >
              {/* Timestamp */}
              <time
                dateTime={msg.timestamp}
                style={{ color: 'var(--color-text-muted)', flexShrink: 0 }}
              >
                {formatTime(msg.timestamp)}
              </time>

              {/* Icon */}
              <span
                style={{
                  flexShrink: 0,
                  color: TYPE_ICON_COLORS[msg.type],
                  display: 'inline-flex',
                  alignItems: 'center',
                  position: 'relative',
                  top: 1,
                }}
              >
                {TYPE_ICONS[msg.type]}
              </span>

              {/* Agent tag */}
              {msg.agent && (
                <span style={{ color: 'var(--color-accent)', flexShrink: 0 }}>
                  [{msg.agent}]
                </span>
              )}

              {/* Message */}
              <span style={{ color: TYPE_MSG_COLORS[msg.type], wordBreak: 'break-word' }}>
                {msg.message}
              </span>
            </div>
          ))
        )}
        <div ref={bottomRef} aria-hidden="true" />
      </div>
    </section>
  )
}
