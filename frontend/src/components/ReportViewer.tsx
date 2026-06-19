import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { ChevronDown, ChevronRight, FileText } from 'lucide-react'
import type { Components } from 'react-markdown'

interface ReportViewerProps {
  markdown: string
}

const mdComponents: Components = {
  code({ node: _node, className, children, ...props }) {
    const match = /language-(\w+)/.exec(className ?? '')
    const inline = !match

    if (inline) {
      return (
        <code
          {...props}
          style={{
            background: 'var(--color-surface-2)',
            borderRadius: 3,
            padding: '1px 5px',
            fontSize: '0.88em',
            color: 'var(--color-accent)',
          }}
        >
          {children}
        </code>
      )
    }

    return (
      <SyntaxHighlighter
        style={vscDarkPlus}
        language={match[1]}
        PreTag="div"
        customStyle={{
          borderRadius: 'var(--radius)',
          fontSize: '0.85rem',
          margin: '0.75rem 0',
          border: '1px solid var(--color-border)',
        }}
      >
        {String(children).replace(/\n$/, '')}
      </SyntaxHighlighter>
    )
  },
  h1: ({ children }) => (
    <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, margin: '1.5rem 0 0.75rem', letterSpacing: '-0.01em' }}>
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, margin: '1.25rem 0 0.5rem', color: 'var(--color-text)' }}>
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, margin: '1rem 0 0.5rem', color: 'var(--color-text)' }}>
      {children}
    </h3>
  ),
  p: ({ children }) => (
    <p style={{ margin: '0.5rem 0', color: 'var(--color-text-muted)', lineHeight: 1.7, fontSize: 'var(--text-sm)' }}>
      {children}
    </p>
  ),
  ul: ({ children }) => (
    <ul style={{ margin: '0.5rem 0 0.5rem 1.25rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', lineHeight: 1.7 }}>
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol style={{ margin: '0.5rem 0 0.5rem 1.25rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', lineHeight: 1.7 }}>
      {children}
    </ol>
  ),
  blockquote: ({ children }) => (
    <blockquote
      style={{
        borderLeft: '3px solid var(--color-accent)',
        paddingLeft: 'var(--space-4)',
        margin: '0.75rem 0',
        color: 'var(--color-text-muted)',
      }}
    >
      {children}
    </blockquote>
  ),
  hr: () => (
    <hr style={{ border: 'none', borderTop: '1px solid var(--color-border)', margin: '1rem 0' }} />
  ),
  strong: ({ children }) => (
    <strong style={{ fontWeight: 700, color: 'var(--color-text)' }}>{children}</strong>
  ),
  a: ({ href, children }) => (
    <a href={href} style={{ color: 'var(--color-accent)' }} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
}

export function ReportViewer({ markdown }: ReportViewerProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
      }}
    >
      {/* Header / toggle */}
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-3)',
          padding: 'var(--space-4)',
          background: 'var(--color-surface-2)',
          border: 'none',
          borderBottom: expanded ? '1px solid var(--color-border)' : 'none',
          color: 'var(--color-text)',
          cursor: 'pointer',
          textAlign: 'left',
          transition: 'background var(--duration-fast)',
        }}
      >
        <FileText size={16} style={{ color: 'var(--color-accent)', flexShrink: 0 }} aria-hidden="true" />
        <span style={{ flex: 1, fontWeight: 600, fontSize: 'var(--text-sm)' }}>
          Full Markdown Report
        </span>
        {expanded
          ? <ChevronDown size={16} style={{ color: 'var(--color-text-muted)', flexShrink: 0 }} aria-hidden="true" />
          : <ChevronRight size={16} style={{ color: 'var(--color-text-muted)', flexShrink: 0 }} aria-hidden="true" />}
      </button>

      {/* Body */}
      {expanded && (
        <div
          style={{
            padding: 'var(--space-6)',
            overflowX: 'auto',
          }}
        >
          <ReactMarkdown components={mdComponents}>
            {markdown}
          </ReactMarkdown>
        </div>
      )}
    </div>
  )
}
